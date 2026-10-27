"""HLS VOD (fMP4) 송출.

구조: ffmpeg 1개가 fMP4를 연속 출력 → moof/mdat 단위로 읽어 Timeline의 조각
경계에 맞춰 묶음 → 메모리에 보관 → 수신기 요청에 응답.
요청 조각이 생산 위치에서 멀면 ffmpeg를 그 조각 시작점부터 다시 시작한다.
"""
from __future__ import annotations

import bisect
import logging
import math
import re
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .encoders import EncoderProfile
from .planner import Plan
from .probe import MediaInfo, VideoStream
from .transcoder import FFmpegProcess, build_args, maxrate_k

_LOGGER = logging.getLogger(__name__)

HLS_MIME = "application/x-mpegurl"
HLS_MEDIA_INFO = {"hlsSegmentFormat": "fmp4", "hlsVideoSegmentFormat": "fmp4"}
SEG_LEN = 6.0
ASSIGN_TOL = 0.5          # 조각 배정 허용 오차(초): 디코딩/표시 시각 차이 흡수
REBASE_LIMIT = 1.0        # 영상 첫 시각이 기대값과 이만큼 다르면 로그 (보정은 제거됨)
WAIT_AHEAD = 3            # 생산 위치에서 이만큼 앞 조각은 재시작 없이 기다림
MAX_AHEAD = 10            # 마지막 요청보다 이만큼 앞서면 읽기 일시정지
MEMORY_LIMIT = 512 * 1024 * 1024
WAIT_TIMEOUT = 30.0
MAX_FAILURES = 3
_SEG_RE = re.compile(r"seg_(\d+)\.m4s")


# ================= 조각 경계 =================
@dataclass(frozen=True)
class Timeline:
    bounds: tuple[float, ...]   # 조각 경계(초). 길이 = 조각 수 + 1

    @property
    def count(self) -> int:
        return len(self.bounds) - 1

    def start(self, i: int) -> float:
        return self.bounds[i]

    def length(self, i: int) -> float:
        return self.bounds[i + 1] - self.bounds[i]

    def index_at(self, t: float) -> int:
        i = bisect.bisect_right(self.bounds, t) - 1
        return min(self.count - 1, max(0, i))


def fixed_timeline(duration: float, seg: float = SEG_LEN) -> Timeline:
    """TRANSCODE: seg 배수 경계 (키프레임 강제). 1초 미만 꼬리는 앞 조각에 합침."""
    b = [0.0]
    while duration - (len(b) * seg) >= 1.0:
        b.append(len(b) * seg)
    b.append(max(duration, b[-1] + 0.1))
    return Timeline(tuple(b))


def keyframe_timeline(keyframes: list[float], duration: float,
                      seg: float = SEG_LEN) -> Timeline:
    """REMUX: 이전 경계에서 seg초 이상 지난 첫 키프레임을 다음 경계로."""
    b = [0.0]
    for t in keyframes:
        if t - b[-1] >= seg and duration - t >= 1.0:
            b.append(t)
    b.append(max(duration, b[-1] + 0.1))
    return Timeline(tuple(b))


# ================= 재생 목록 =================
def _copy_codec(v: VideoStream) -> str:
    if v.codec == "h264":
        prof = {"Baseline": "4200", "Constrained Baseline": "42E0",
                "Main": "4D00", "High": "6400"}.get(v.profile, "6400")
        return f"avc1.{prof}{(v.level if v.level > 0 else 51):02X}"
    lvl = v.level if v.level > 0 else 153
    if v.profile == "Main 10":
        return f"hvc1.2.4.L{lvl}.B0"
    return f"hvc1.1.6.L{lvl}.B0"


def codecs_string(info: MediaInfo, plan: Plan) -> str:
    assert info.video is not None
    vc = _copy_codec(info.video) if plan.video_copy else "avc1.640033"
    return f"{vc},mp4a.40.2" if plan.audio is not None else vc


def _bandwidth(info: MediaInfo, plan: Plan) -> int:
    if not plan.video_copy:
        return maxrate_k(info) * 1000 + 192_000
    try:
        size = info.path.stat().st_size
    except OSError:
        size = 0
    return max(1_000_000, int(size * 8 / info.duration)) if info.duration > 0 else 10_000_000


def master_playlist(info: MediaInfo, plan: Plan) -> str:
    attrs = [f"BANDWIDTH={_bandwidth(info, plan)}",
             f'CODECS="{codecs_string(info, plan)}"']
    v = info.video
    if v and v.width and v.height:
        attrs.append(f"RESOLUTION={v.width}x{v.height}")
    return ("#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-INDEPENDENT-SEGMENTS\n"
            f"#EXT-X-STREAM-INF:{','.join(attrs)}\nmedia.m3u8\n")


def media_playlist(tl: Timeline) -> str:
    target = math.ceil(max(tl.length(i) for i in range(tl.count)))
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", f"#EXT-X-TARGETDURATION:{target}",
             "#EXT-X-MEDIA-SEQUENCE:0", "#EXT-X-PLAYLIST-TYPE:VOD",
             "#EXT-X-INDEPENDENT-SEGMENTS", '#EXT-X-MAP:URI="init.mp4"']
    for i in range(tl.count):
        lines += [f"#EXTINF:{tl.length(i):.6f},", f"seg_{i}.m4s"]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


# ================= MP4 상자 =================
def _children(buf, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """(type, payload 시작, box 끝)."""
    pos = start
    while pos + 8 <= end:
        size, typ = struct.unpack_from(">I4s", buf, pos)
        hdr = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = struct.unpack_from(">Q", buf, pos + 8)[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr or pos + size > end:
            return
        yield typ, pos + hdr, pos + size
        pos += size


def parse_tracks(moov: bytes, hl: int) -> tuple[dict[int, int], int | None]:
    """moov → ({track_id: timescale}, 영상 track_id)."""
    scales: dict[int, int] = {}
    video = None
    for typ, p, e in _children(moov, hl, len(moov)):
        if typ != b"trak":
            continue
        tid = scale = handler = None
        for t2, p2, e2 in _children(moov, p, e):
            if t2 == b"tkhd":
                tid = struct.unpack_from(">I", moov, p2 + (20 if moov[p2] == 1 else 12))[0]
            elif t2 == b"mdia":
                for t3, p3, _e3 in _children(moov, p2, e2):
                    if t3 == b"mdhd":
                        off = 20 if moov[p3] == 1 else 12
                        scale = struct.unpack_from(">I", moov, p3 + off)[0]
                    elif t3 == b"hdlr":
                        handler = bytes(moov[p3 + 8:p3 + 12])
        if tid and scale:
            scales[tid] = scale
            if handler == b"vide" and video is None:
                video = tid
    return scales, video


def _tfdt_entries(moof, hl: int) -> list[tuple[int, int, int]]:
    """[(track_id, tfdt payload 위치, version)]."""
    out = []
    for typ, p, e in _children(moof, hl, len(moof)):
        if typ != b"traf":
            continue
        tid = pos = None
        ver = 0
        for t2, p2, _e2 in _children(moof, p, e):
            if t2 == b"tfhd":
                tid = struct.unpack_from(">I", moof, p2 + 4)[0]
            elif t2 == b"tfdt":
                pos, ver = p2, moof[p2]
        if tid is not None and pos is not None:
            out.append((tid, pos, ver))
    return out


def _read_tfdt(buf, pos: int, ver: int) -> int:
    fmt = ">Q" if ver == 1 else ">I"
    return struct.unpack_from(fmt, buf, pos + 4)[0]


def _read_box(proc: FFmpegProcess) -> tuple[bytes, bytes, int] | None:
    head = proc.read_exact(8)
    if len(head) < 8:
        return None
    size, typ = struct.unpack(">I4s", head)
    hl = 8
    if size == 1:
        ext = proc.read_exact(8)
        if len(ext) < 8:
            return None
        size = struct.unpack(">Q", ext)[0]
        head += ext
        hl = 16
    if size < hl:   # size 0(파일 끝까지)은 파이프 출력에서 쓰지 않음
        return None
    body = proc.read_exact(size - hl)
    if len(body) < size - hl:
        return None
    return typ, head + body, hl


# ================= 세션 =================
class HlsSession:
    """파일 1개 + 음성 1개 조합의 HLS 송출. get(name)으로 HTTP 요청 처리."""

    def __init__(self, ffmpeg: Path, info: MediaInfo, plan: Plan, timeline: Timeline,
                 encoder: EncoderProfile | None, start_hint: float = 0.0,
                 on_error: Callable[[str], None] | None = None) -> None:
        self._ffmpeg = ffmpeg
        self.info, self.plan, self.tl, self.encoder = info, plan, timeline, encoder
        self._on_error = on_error
        self._master = master_playlist(info, plan).encode("utf-8")
        self._media = media_playlist(timeline).encode("utf-8")
        self._cond = threading.Condition()
        self._segs: dict[int, bytes] = {}
        self._mem = 0
        self._init: bytes | None = None
        self._gen = 0
        self._proc: FFmpegProcess | None = None
        self._alive = False
        self._prod_next = -1          # 생산 중인 조각 번호
        self._want = timeline.index_at(start_hint)
        self._failures = 0
        self._closed = False
        self._requests: dict[int, int] = {}   # 조각별 요청 횟수 (재요청 추적)
        _LOGGER.info("HLS 세션: 조각 %d개, CODECS=%s", timeline.count,
                     codecs_string(info, plan))

    # ---- HTTP ----
    def get(self, name: str) -> tuple[bytes, str] | None:
        if name == "master.m3u8":
            return self._master, HLS_MIME
        if name == "media.m3u8":
            return self._media, HLS_MIME
        if name == "init.mp4":
            data = self._wait_init()
            return None if data is None else (data, "video/mp4")
        m = _SEG_RE.fullmatch(name)
        if m and int(m[1]) < self.tl.count:
            data = self._wait_segment(int(m[1]))
            return None if data is None else (data, "video/mp4")
        return None

    def close(self) -> None:
        with self._cond:
            if self._closed:
                return
            self._closed = True
            self._kill_locked()
            self._gen += 1
            self._segs.clear()
            self._mem = 0
            self._cond.notify_all()

    # ---- 요청 대기 ----
    def _wait_init(self) -> bytes | None:
        deadline = time.monotonic() + WAIT_TIMEOUT
        starts = 0
        with self._cond:
            while not self._closed:
                if self._init is not None:
                    return self._init
                if self._failures >= MAX_FAILURES:
                    return None
                if not self._alive:
                    if starts >= 2:
                        return None
                    starts += 1
                    # 수신기는 시작 위치와 관계없이 seg_0을 먼저 요청함(실측)
                    #        → 조각 0부터 만들어 불필요한 재시작을 없앰
                    self._start_locked(0)
                left = deadline - time.monotonic()
                if left <= 0:
                    _LOGGER.warning("init 대기 시간 초과")
                    return None
                self._cond.wait(min(left, 1.0))
        return None

    def _wait_segment(self, i: int) -> bytes | None:
        t0 = time.monotonic()
        deadline = t0 + WAIT_TIMEOUT
        starts = 0
        with self._cond:
            # 같은 조각을 다시 요청 = 수신기가 앞 요청을 포기했다는 뜻 (버퍼링 원인 추적)
            n = self._requests[i] = self._requests.get(i, 0) + 1
            if n > 1:
                _LOGGER.info("조각 %d 재요청 (%d번째, 생산 위치 %d, 보관 %s)", i, n,
                             self._prod_next, "있음" if i in self._segs else "없음")
            self._want = i
            self._cond.notify_all()   # 읽기 일시정지 해제
            while not self._closed:
                data = self._segs.get(i)
                if data is not None:
                    waited = time.monotonic() - t0              # 생산 대기 시간
                    if waited >= 0.5:
                        _LOGGER.log(logging.INFO if waited >= 3 else logging.DEBUG,
                                    "조각 %d: 생산을 %.1f초 기다림", i, waited)
                    return data
                if self._failures >= MAX_FAILURES:
                    return None
                coming = self._alive and self._prod_next <= i <= self._prod_next + WAIT_AHEAD
                if not coming:
                    if starts >= 2:
                        _LOGGER.warning("조각 %d을 만들지 못했습니다.", i)
                        return None
                    starts += 1
                    self._start_locked(i)
                left = deadline - time.monotonic()
                if left <= 0:
                    _LOGGER.warning("조각 %d 대기 시간 초과", i)
                    return None
                self._cond.wait(min(left, 1.0))
        return None

    # ---- 생산자 관리 (lock 보유 상태에서 호출) ----
    def _start_locked(self, i: int) -> None:
        self._kill_locked()
        self._gen += 1
        start = self.tl.start(i)
        try:
            args = build_args(self.info, self.plan, start, self.encoder, SEG_LEN)
            proc = FFmpegProcess(self._ffmpeg, args, on_error=self._proc_error)
        except (OSError, RuntimeError) as err:
            self._failures = MAX_FAILURES
            _LOGGER.error("ffmpeg 실행 실패: %s", err)
            if self._on_error:
                self._on_error(f"ffmpeg 실행 실패: {err}")
            return
        self._proc, self._alive, self._prod_next = proc, True, i
        _LOGGER.info("HLS 생산 시작: 조각 %d/%d (%.3f초)", i, self.tl.count, start)
        threading.Thread(target=self._produce, args=(proc, self._gen, i),
                         name="hls-producer", daemon=True).start()

    def _kill_locked(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc = None
        self._alive = False

    def _proc_error(self, msg: str) -> None:
        with self._cond:
            self._failures += 1
            self._cond.notify_all()
        if self._on_error:
            self._on_error(msg)

    # ---- 생산자 스레드 ----
    def _produce(self, proc: FFmpegProcess, gen: int, first: int) -> None:
        """tfdt는 ffmpeg가 원본 시각으로 기록함 (copyts + frag_discont, 실측 확인).
        ffmpeg가 앞 키프레임에서 시작하면 조각 시작 전 fragment는 버림.
        서버 tfdt 보정 제거 (오보정 위험: 앞 키프레임이 0초 근처일 때)."""
        cur, buf = first, []
        init_parts: list[bytes] = []
        scales: dict[int, int] = {}
        video_id: int | None = None
        seen: set[int] = set()            # 첫 tfdt를 기록한 트랙
        expect = self.tl.start(first)
        started = first == 0              # 조각 시작 시각에 도달했는지
        dropping = False                  # 직전 moof를 버렸는지 (짝 mdat도 버림)
        dropped, first_t = 0, None
        while True:
            box = _read_box(proc)
            if box is None:
                break
            typ, data, hl = box
            if typ in (b"ftyp", b"moov"):
                init_parts.append(data)
                if typ == b"moov":
                    try:
                        scales, video_id = parse_tracks(data, hl)
                    except (struct.error, IndexError):
                        _LOGGER.error("moov 해석 실패")
                    self._set_init(b"".join(init_parts), gen)
                continue
            if typ == b"moof":
                try:
                    entries = _tfdt_entries(data, hl)
                except (struct.error, IndexError):
                    entries = []
                for tid, p, v in entries:
                    if tid not in seen and tid in scales:
                        seen.add(tid)
                        _LOGGER.debug("HLS 조각 %d: %s 첫 tfdt %.3f초 (기대 %.3f초)",
                                      first, "영상" if tid == video_id else "음성",
                                      _read_tfdt(data, p, v) / scales[tid], expect)
                vt = next(((p, v) for tid, p, v in entries if tid == video_id), None)
                keep = not dropping
                if vt is not None and video_id in scales:
                    t = _read_tfdt(data, *vt) / scales[video_id]
                    if first_t is None:
                        first_t = t
                    if not started and t + ASSIGN_TOL < expect:
                        keep = False                      # 조각 시작 전 → 버림
                        dropped += 1
                    else:
                        keep = True
                        if not started:
                            started = True
                            if dropped:
                                _LOGGER.info("HLS 조각 %d: %.3f초 앞 키프레임에서 시작"
                                             " → 앞 fragment %d개 버림",
                                             first, expect - first_t, dropped)
                            elif abs(expect - t) > REBASE_LIMIT:
                                _LOGGER.info("HLS 조각 %d: 영상이 기대보다 %.3f초 뒤에서 시작",
                                             first, t - expect)
                        idx = self.tl.index_at(t + ASSIGN_TOL)
                        if idx > cur:
                            if buf and not self._finish(gen, cur, buf):
                                return
                            if idx > cur + 1:
                                _LOGGER.warning("조각 %d~%d 비어 있음 (키프레임 간격)",
                                                cur + 1, idx - 1)
                            buf, cur = [], idx
                dropping = not keep
                if keep:
                    buf.append(data)
            elif typ == b"mdat":
                if not dropping:
                    buf.append(data)
            if not self._throttle(gen, cur):
                return
        rc = proc.wait()
        if rc == 0 and buf:
            self._finish(gen, cur, buf)   # 마지막 조각
        with self._cond:
            if gen == self._gen:
                self._alive = False
                self._proc = None
            self._cond.notify_all()

    def _set_init(self, data: bytes, gen: int) -> None:
        with self._cond:
            if gen != self._gen:
                return
            if self._init is None:
                self._init = data
                self._cond.notify_all()
            elif data != self._init:
                _LOGGER.debug("재시작 ffmpeg의 init이 처음과 다름 (%d → %d바이트), 처음 것 유지",
                              len(self._init), len(data))

    def _throttle(self, gen: int, cur: int) -> bool:
        with self._cond:
            if gen != self._gen or self._closed:
                return False
            self._prod_next = cur
            while cur > self._want + MAX_AHEAD:
                self._cond.wait(1.0)
                if gen != self._gen or self._closed:
                    return False
            return True

    def _finish(self, gen: int, idx: int, buf: list[bytes]) -> bool:
        data = b"".join(buf)
        with self._cond:
            if gen != self._gen or self._closed:
                return False
            old = self._segs.get(idx)
            if old is not None:
                self._mem -= len(old)
            self._segs[idx] = data
            self._mem += len(data)
            self._failures = 0
            self._prod_next = idx + 1
            self._evict_locked()
            self._cond.notify_all()
        _LOGGER.debug("HLS 조각 %d 완료 (%.1fMB)", idx, len(data) / 1e6)
        return True

    def _evict_locked(self) -> None:
        while self._mem > MEMORY_LIMIT and len(self._segs) > 1:
            want = self._want
            victim = max((k for k in self._segs if not want <= k <= want + MAX_AHEAD),
                         key=lambda k: abs(k - want), default=None)
            if victim is None:
                return
            self._mem -= len(self._segs.pop(victim))
