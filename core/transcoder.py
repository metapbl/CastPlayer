"""ffmpeg 명령 생성 + 1회 실행 관리 (HLS 생산자용)."""
from __future__ import annotations

import logging
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from .encoders import EncoderProfile
from .planner import FULLHD_PIXELS, Plan
from .proc import NO_WINDOW, bind_to_job
from .probe import MediaInfo

_LOGGER = logging.getLogger(__name__)
MAXRATE_4K_K = 25_000
MAXRATE_HD_K = 10_000
# 영상 복사 시 조각 경계 키프레임 바로 뒤로 찾아감.
#   0.02초로는 부족했음(실측: 한 키프레임 앞에서 시작). B프레임 영상은 ffmpeg가
#   탐색 지점을 약 0.13초 앞당기는 것으로 추정 → 그보다 크고 키프레임 간격보다 작은 값
SEEK_EPSILON = 0.25
# frag_discont: 트랙별 tfdt를 0부터 세지 않고 실제 시각으로 기록
# delay_moov: moov를 첫 fragment가 준비된 뒤에 씀.
#   empty_moov만 쓰면 TS의 ADTS AAC는 aac_adtstoasc가 첫 패킷을 처리하기 전에
#   moov가 써져서 AudioSpecificConfig가 빠짐 → 수신기 LOAD_FAILED (실측 확인)
MOVFLAGS = "frag_keyframe+empty_moov+default_base_moof+frag_discont+delay_moov"


def maxrate_k(info: MediaInfo) -> int:
    v = info.video
    return MAXRATE_4K_K if v and v.width * v.height > FULLHD_PIXELS else MAXRATE_HD_K


def audio_copy_ok(plan: Plan) -> bool:
    """HLS fMP4 경로는 AAC만 복사 (MP3는 AAC로 변환)."""
    return plan.audio is not None and plan.audio_copy and plan.audio.codec == "aac"


def build_args(info: MediaInfo, plan: Plan, start: float,
               encoder: EncoderProfile | None, keyint: float) -> list[str]:
    """start초(조각 경계)부터 fMP4 연속 출력.

    출력 시각 = 원본 시간축(파일 시작 0초, keyframes.py와 같은 기준).
      -copyts -start_at_zero : -ss 뒤에도 원본 시각 유지
      frag_discont           : 영상(키프레임부터)과 음성(탐색 지점부터)의 실제 시작 차이 보존
      delay_moov             : 코덱 설정 정보가 확정된 뒤 moov 기록 (TS의 ADTS AAC 대응)
      -use_editlist 0        : 시각은 tfdt로만 전달, 재시작해도 init이 같게 유지
    """
    v = info.video
    assert v is not None
    args = ["-hide_banner", "-nostdin", "-loglevel", "warning"]
    if start > 0:
        seek = start + SEEK_EPSILON if plan.video_copy else start
        args += ["-ss", f"{seek:.3f}"]
    args += ["-copyts", "-start_at_zero"]
    args += ["-i", str(info.path), "-map", f"0:{v.index}"]
    if plan.audio is not None:
        args += ["-map", f"0:{plan.audio.index}"]

    if plan.video_copy:
        args += ["-c:v", "copy"]
        if v.codec == "hevc":
            args += ["-tag:v", "hvc1"]
    else:
        if encoder is None:
            raise RuntimeError("재인코딩용 인코더가 없습니다.")
        fps_out = plan.fps_cap or v.fps or 24
        gop = max(1, round(float(fps_out) * 2))
        args += encoder.video_args(maxrate_k(info), gop)
        vf = []
        if plan.fps_cap:
            vf.append(f"fps={plan.fps_cap.numerator}/{plan.fps_cap.denominator}")
        vf.append(f"format={encoder.pix_fmt}")
        args += ["-vf", ",".join(vf)]
        # copyts라 t는 원본 시각, n_forced는 프로세스마다 0부터 → start를 더함
        args += ["-force_key_frames", f"expr:gte(t,{start:.3f}+n_forced*{keyint:g})"]

    if plan.audio is not None:
        if audio_copy_ok(plan):
            args += ["-c:a", "copy", "-bsf:a", "aac_adtstoasc"]
        else:
            args += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]

    args += ["-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
             "-avoid_negative_ts", "make_non_negative",
             "-use_editlist", "0",
             "-f", "mp4", "-movflags", MOVFLAGS, "pipe:1"]
    return args


class FFmpegProcess:
    """ffmpeg 1회 실행. stdout은 호출 측이 읽고, stderr는 감시 스레드가 수집."""

    def __init__(self, ffmpeg: Path, args: list[str],
                 on_error: Callable[[str], None] | None = None) -> None:
        cmd = [str(ffmpeg), *args]
        _LOGGER.debug("ffmpeg 시작: %s", subprocess.list2cmdline(cmd))
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0, creationflags=NO_WINDOW)
        bind_to_job(self._proc)
        self._on_error = on_error
        self._killed = False
        threading.Thread(target=self._watch, name="ffmpeg-watch", daemon=True).start()

    def read_exact(self, n: int) -> bytes:
        parts: list[bytes] = []
        left = n
        assert self._proc.stdout is not None   # PIPE로 열었음
        while left > 0:
            try:
                chunk = self._proc.stdout.read(left)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            parts.append(chunk)
            left -= len(chunk)
        return b"".join(parts)

    def kill(self) -> None:
        """실행 중일 때만 강제 종료하고 '우리가 죽였음'으로 기록 (오류 보고 제외)."""
        if self._proc.poll() is None:
            self._killed = True
            self._proc.kill()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _LOGGER.warning("ffmpeg 종료 대기 시간 초과 (pid %s)", self._proc.pid)

    def wait(self) -> int:
        return self._proc.wait()

    def _watch(self) -> None:
        tail: deque[str] = deque(maxlen=20)
        assert self._proc.stderr is not None
        for raw in iter(self._proc.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                tail.append(line)
                _LOGGER.debug("ffmpeg: %s", line)
        rc = self._proc.wait()
        if rc != 0 and not self._killed:
            msg = tail[-1] if tail else f"종료 코드 {rc}"
            _LOGGER.error("ffmpeg 비정상 종료: %s", "\n".join(tail))
            if self._on_error:
                self._on_error(f"ffmpeg 오류: {msg}")
