"""ffprobe → MediaInfo."""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from .paths import ffprobe_path
from .proc import NO_WINDOW

_LOGGER = logging.getLogger(__name__)
IMAGE_SUB_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}
# 표시 시각(pts) 검사: B프레임을 쓰는 코덱만, 앞부분 몇 초만 읽음
PTS_CHECK_CODECS = {"h264", "hevc"}
PTS_CHECK_SECONDS = 5
PTS_CHECK_MIN = 24          # 읽은 패킷이 이보다 적으면 판단하지 않음


class ProbeError(RuntimeError):
    pass


def _frac(s: str | None) -> Fraction:
    try:
        return Fraction(s) if s else Fraction(0)
    except (ValueError, ZeroDivisionError):
        return Fraction(0)


@dataclass(frozen=True)
class VideoStream:
    index: int
    codec: str
    profile: str
    level: int
    width: int
    height: int
    pix_fmt: str
    fps: Fraction
    tag: str
    has_b_frames: int = 0       # ffprobe has_b_frames (B프레임 재정렬 깊이)
    pts_broken: bool = False    # 표시 시각 정보 없음 (mp4 ctts 누락 등)

    @property
    def high_bit_depth(self) -> bool:
        return any(x in self.pix_fmt for x in ("10", "12"))


@dataclass(frozen=True)
class AudioStream:
    index: int     # ffprobe 절대 인덱스 (-map 0:index)
    order: int     # 음성 트랙 중 순번 (0부터)
    codec: str
    channels: int
    language: str
    title: str
    default: bool

    @property
    def label(self) -> str:
        ch = {1: "mono", 2: "2ch", 6: "5.1", 8: "7.1"}.get(
            self.channels, f"{self.channels}ch")
        parts = [f"#{self.order + 1}", self.language or "und", self.codec.upper(), ch]
        if self.title:
            parts.append(f"'{self.title}'")
        if self.default:
            parts.append("(기본)")
        return " ".join(parts)


@dataclass(frozen=True)
class SubtitleStream:
    index: int
    order: int
    codec: str
    language: str
    title: str
    default: bool
    forced: bool

    @property
    def is_image(self) -> bool:
        return self.codec in IMAGE_SUB_CODECS

    @property
    def label(self) -> str:
        parts = [f"내장#{self.order + 1}", self.language or "und", self.codec]
        if self.title:
            parts.append(f"'{self.title}'")
        if self.is_image:
            parts.append("(지원 안 함)")
        return " ".join(parts)


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    format_name: str
    duration: float
    video: VideoStream | None
    audio: tuple[AudioStream, ...]
    subtitles: tuple[SubtitleStream, ...]


def check_pts_order(path: Path, timeout: float = 15.0) -> bool:
    """B프레임 영상인데 패킷 pts가 저장(디코딩) 순서대로만 증가하면 True.

    정상: B프레임 때문에 pts 순서가 뒤섞임 (.ts 파일 실측)
    결함: 표시 시각 정보(mp4 ctts)가 빠져 pts=dts로 차례대로 증가 (x265 mp4 실측)
    → 수신기는 프레임을 저장 순서대로 보여줘 화면이 떨리듯 끊김.
    검사 실패 시 False (정상으로 간주)."""
    cmd = [str(ffprobe_path()), "-v", "error", "-select_streams", "v:0",
           "-read_intervals", f"%+{PTS_CHECK_SECONDS}",
           "-show_entries", "packet=pts_time", "-of", "compact=p=0", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired):
        _LOGGER.debug("표시 시각 검사 실패(무시)", exc_info=True)
        return False
    pts: list[float] = []
    for line in r.stdout.decode("ascii", "replace").splitlines():
        for kv in line.split("|"):
            if kv.startswith("pts_time="):
                try:
                    pts.append(float(kv[9:]))
                except ValueError:
                    pass                      # N/A
    if len(pts) < PTS_CHECK_MIN:
        _LOGGER.debug("표시 시각 검사: 패킷 %d개뿐이라 판단하지 않음", len(pts))
        return False
    broken = all(b > a for a, b in zip(pts, pts[1:]))
    if broken:
        _LOGGER.info("표시 시각 검사: B프레임 영상인데 pts가 순서대로만 증가 "
                     "(패킷 %d개) → 표시 시각 정보 없음", len(pts))
    else:
        _LOGGER.debug("표시 시각 검사: 정상 (패킷 %d개)", len(pts))
    return broken


def probe(path: Path, timeout: float = 30.0) -> MediaInfo:
    cmd = [str(ffprobe_path()), "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired) as err:
        raise ProbeError(f"ffprobe 실행 실패: {err}") from err
    if r.returncode != 0:
        raise ProbeError(r.stderr.decode("utf-8", "replace").strip() or "ffprobe 오류")
    try:
        data = json.loads(r.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as err:
        raise ProbeError("ffprobe 출력 해석 실패") from err

    fmt = data.get("format", {})
    video = None
    audio: list[AudioStream] = []
    subs: list[SubtitleStream] = []
    for s in data.get("streams", []):
        kind = s.get("codec_type")
        tags = s.get("tags", {}) or {}
        disp = s.get("disposition", {}) or {}
        if kind == "video" and video is None and not disp.get("attached_pic"):
            fps = _frac(s.get("avg_frame_rate")) or _frac(s.get("r_frame_rate"))
            video = VideoStream(
                index=s["index"], codec=s.get("codec_name", ""),
                profile=s.get("profile", ""), level=int(s.get("level", -99) or -99),
                width=int(s.get("width", 0)), height=int(s.get("height", 0)),
                pix_fmt=s.get("pix_fmt", ""), fps=fps,
                tag=s.get("codec_tag_string", ""),
                has_b_frames=int(s.get("has_b_frames", 0) or 0))
        elif kind == "audio":
            audio.append(AudioStream(
                index=s["index"], order=len(audio), codec=s.get("codec_name", ""),
                channels=int(s.get("channels", 0) or 0),
                language=tags.get("language", ""), title=tags.get("title", ""),
                default=bool(disp.get("default"))))
        elif kind == "subtitle":
            subs.append(SubtitleStream(
                index=s["index"], order=len(subs), codec=s.get("codec_name", ""),
                language=tags.get("language", ""), title=tags.get("title", ""),
                default=bool(disp.get("default")), forced=bool(disp.get("forced"))))

    # B프레임 영상만 표시 시각 검사
    if (video is not None and video.has_b_frames > 0
            and video.codec in PTS_CHECK_CODECS):
        video = replace(video, pts_broken=check_pts_order(path))

    try:
        duration = float(fmt.get("duration") or 0.0)
    except ValueError:
        duration = 0.0
    return MediaInfo(path=path, format_name=fmt.get("format_name", ""),
                     duration=duration, video=video,
                     audio=tuple(audio), subtitles=tuple(subs))
