"""MediaInfo + 선택 음성 → DIRECT / REMUX / TRANSCODE 결정."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from .probe import AudioStream, MediaInfo, VideoStream

COPY_AUDIO = {"aac", "mp3"}
H264_PROFILES = {"Baseline", "Constrained Baseline", "Main", "High"}
HEVC_PROFILES = {"Main", "Main 10"}
H264_MAX_LEVEL = 51    # 5.1
HEVC_MAX_LEVEL = 153   # 5.1 (ffprobe는 level*30 표기)
FULLHD_PIXELS = 1920 * 1088


class PlanError(RuntimeError):
    pass


class Mode(str, Enum):
    DIRECT = "DIRECT"
    REMUX = "REMUX"
    TRANSCODE = "TRANSCODE"


@dataclass(frozen=True)
class Plan:
    mode: Mode
    video_copy: bool
    audio: AudioStream | None
    audio_copy: bool
    fps_cap: Fraction | None
    reasons: tuple[str, ...]

    @property
    def summary(self) -> str:
        v = "영상 복사" if self.video_copy else "영상 재인코딩"
        if self.audio is None:
            a = "음성 없음"
        else:
            a = f"음성 {self.audio.label} " + ("복사" if self.audio_copy else "→ AAC 2ch")
        why = f" [{'; '.join(self.reasons)}]" if self.reasons else ""
        return f"{self.mode.value} · {v} · {a}{why}"


def _video_ok(v: VideoStream) -> tuple[bool, str]:
    # 표시 시각 정보가 없으면 복사해도 수신기에서 끊김 (x265 mp4 실측)
    if v.pts_broken:
        return False, "표시 시각 정보 없음(ctts 누락)"
    if v.codec == "h264":
        if v.high_bit_depth or v.profile not in H264_PROFILES:
            return False, f"H.264 {v.profile or v.pix_fmt} 미지원"
        if v.level > H264_MAX_LEVEL:
            return False, f"H.264 레벨 {v.level / 10:.1f} 초과"
        return True, ""
    if v.codec == "hevc":
        if v.profile not in HEVC_PROFILES:
            return False, f"HEVC {v.profile} 미지원"
        if v.level > HEVC_MAX_LEVEL:
            return False, f"HEVC 레벨 {v.level / 30:.1f} 초과"
        return True, ""
    return False, f"{v.codec} 코덱 미지원"


def pick_audio(info: MediaInfo, order: int | None) -> AudioStream | None:
    if not info.audio:
        return None
    if order is None:
        return next((a for a in info.audio if a.default), info.audio[0])
    if not 0 <= order < len(info.audio):
        raise PlanError(f"음성 트랙 #{order + 1}이 없습니다.")
    return info.audio[order]


def make_plan(info: MediaInfo, audio_order: int | None = None) -> Plan:
    v = info.video
    if v is None:
        raise PlanError("영상 트랙이 없습니다.")
    audio = pick_audio(info, audio_order)
    audio_copy = audio is None or audio.codec in COPY_AUDIO
    reasons: list[str] = []

    ok, why = _video_ok(v)
    if not ok:
        reasons.append(why)
        fps_cap = None
        if v.width * v.height > FULLHD_PIXELS and v.fps > 31:
            fps_cap = v.fps / 2
            reasons.append(f"4K H.264 한계로 {float(fps_cap):.2f}fps")
        return Plan(Mode.TRANSCODE, False, audio, audio_copy, fps_cap, tuple(reasons))

    is_mp4 = ("mp4" in info.format_name.split(",")
              and info.path.suffix.lower() in (".mp4", ".m4v"))
    if not is_mp4:
        reasons.append("컨테이너 변환")
    if v.codec == "hevc" and v.tag != "hvc1":
        reasons.append(f"HEVC 태그 {v.tag or '?'}→hvc1")
    if not audio_copy:
        reasons.append(f"{audio.codec} → AAC")
    if audio is not None and audio.order != 0:
        reasons.append("기본 외 음성 트랙 선택")

    mode = Mode.REMUX if reasons else Mode.DIRECT
    return Plan(mode, True, audio, audio_copy, None, tuple(reasons))
