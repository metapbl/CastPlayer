"""MediaInfo + 선택 음성 → DIRECT / REMUX / TRANSCODE 결정."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from .i18n import N_, tr
from .probe import AudioStream, MediaInfo, VideoStream

COPY_AUDIO = {"aac", "mp3"}
AAC_MAX_RATE = 48000   # 넘으면 변환 (D075)
AAC_MAX_CHANNELS = 6
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
    reasons: tuple[tuple[str, dict], ...]   # (번역 키, 채울 값): 보여 줄 때 번역 (D085)

    @property
    def summary(self) -> str:
        v = tr("영상 복사") if self.video_copy else tr("영상 재인코딩")
        if self.audio is None:
            a = tr("음성 없음")
        else:
            a = (tr("음성 {label} 복사", label=self.audio.label) if self.audio_copy
                 else tr("음성 {label} → AAC 2ch", label=self.audio.label))
        why = f" [{'; '.join(tr(k, **kw) for k, kw in self.reasons)}]" if self.reasons else ""
        return f"{self.mode.value} · {v} · {a}{why}"


def _video_ok(v: VideoStream) -> tuple[bool, tuple[str, dict]]:
    # 표시 시각 정보가 없으면 복사해도 수신기에서 끊김 (x265 mp4 실측)
    if v.pts_broken:
        return False, (N_("표시 시각 정보 없음(ctts 누락)"), {})
    if v.codec == "h264":
        if v.high_bit_depth or v.profile not in H264_PROFILES:
            return False, (N_("H.264 {profile} 미지원"), {"profile": v.profile or v.pix_fmt})
        if v.level > H264_MAX_LEVEL:
            return False, (N_("H.264 레벨 {level} 초과"), {"level": f"{v.level / 10:.1f}"})
        return True, ("", {})
    if v.codec == "hevc":
        if v.profile not in HEVC_PROFILES:
            return False, (N_("HEVC {profile} 미지원"), {"profile": v.profile})
        if v.level > HEVC_MAX_LEVEL:
            return False, (N_("HEVC 레벨 {level} 초과"), {"level": f"{v.level / 30:.1f}"})
        return True, ("", {})
    return False, (N_("{codec} 코덱 미지원"), {"codec": v.codec})


def pick_audio(info: MediaInfo, order: int | None) -> AudioStream | None:
    if not info.audio:
        return None
    if order is None:
        return next((a for a in info.audio if a.default), info.audio[0])
    if not 0 <= order < len(info.audio):
        raise PlanError(tr("음성 트랙 #{n}이 없습니다.", n=order + 1))
    return info.audio[order]


def _audio_copy_ok(a: AudioStream) -> bool:
    if a.codec != "aac":
        return a.codec in COPY_AUDIO
    return (not a.profile.startswith("HE-") and a.sample_rate <= AAC_MAX_RATE
            and a.channels <= AAC_MAX_CHANNELS)


def make_plan(info: MediaInfo, audio_order: int | None = None) -> Plan:
    v = info.video
    if v is None:
        raise PlanError(tr("영상 트랙이 없습니다."))
    audio = pick_audio(info, audio_order)
    audio_copy = audio is None or _audio_copy_ok(audio)
    reasons: list[tuple[str, dict]] = []

    ok, why = _video_ok(v)
    if not ok:
        reasons.append(why)
        fps_cap = None
        if v.width * v.height > FULLHD_PIXELS and v.fps > 31:
            fps_cap = v.fps / 2
            reasons.append((N_("4K H.264 한계로 {fps}fps"), {"fps": f"{float(fps_cap):.2f}"}))
        return Plan(Mode.TRANSCODE, False, audio, audio_copy, fps_cap, tuple(reasons))

    is_mp4 = ("mp4" in info.format_name.split(",")
              and info.path.suffix.lower() in (".mp4", ".m4v"))
    if not is_mp4:
        reasons.append((N_("컨테이너 변환"), {}))
    if v.codec == "hevc" and v.tag != "hvc1":
        reasons.append((N_("HEVC 태그 {tag}→hvc1"), {"tag": v.tag or "?"}))
    if audio is not None and not audio_copy:
        reasons.append((f"{audio.codec} {audio.profile} {audio.sample_rate}Hz "   # 번역할 말 없음
                        f"{audio.channels}ch → AAC" if audio.codec == "aac"
                        else f"{audio.codec} → AAC", {}))
    if audio is not None and audio.order != 0:
        reasons.append((N_("기본 외 음성 트랙 선택"), {}))

    mode = Mode.REMUX if reasons else Mode.DIRECT
    return Plan(mode, True, audio, audio_copy, None, tuple(reasons))
