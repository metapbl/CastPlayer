"""음성·자막 목록 글자 (F9-11, D092, D096). 겹치는 정보 없이 사람이 읽는 형태로, 트랙 제목은 풍선 도움말."""
from __future__ import annotations

from PySide6.QtCore import QLocale

from core.i18n import N_, tr
from core.probe import AudioStream
from core.subtitles import PENDING, SubtitleTrack

# 자주 쓰는 15개 언어만 화면 언어로 번역 (D096). ISO 639-1·639-2 코드 모두
_LANG_NAMES = {
    ("ko", "kor"): N_("한국어"), ("en", "eng"): N_("영어"), ("ja", "jpn"): N_("일본어"),
    ("zh", "zho", "chi"): N_("중국어"), ("es", "spa"): N_("스페인어"),
    ("fr", "fra", "fre"): N_("프랑스어"), ("de", "deu", "ger"): N_("독일어"),
    ("ru", "rus"): N_("러시아어"), ("it", "ita"): N_("이탈리아어"), ("pt", "por"): N_("포르투갈어"),
    ("th", "tha"): N_("태국어"), ("vi", "vie"): N_("베트남어"), ("id", "ind"): N_("인도네시아어"),
    ("ar", "ara"): N_("아랍어"), ("hi", "hin"): N_("힌디어"),
}
LANG_NAMES = {code: name for codes, name in _LANG_NAMES.items() for code in codes}
AUDIO_CODECS = {"eac3": "Dolby Digital Plus", "ac3": "Dolby Digital", "truehd": "Dolby TrueHD",
                "dts": "DTS", "aac": "AAC"}
SUB_CODECS = {"subrip": "SRT", "ass": "ASS", "ssa": "SSA", "webvtt": "WebVTT", "mov_text": "TX3G",
              "hdmv_pgs_subtitle": "PGS", "dvd_subtitle": "VobSub", "dvb_subtitle": "DVB"}
CHANNELS = {1: "mono", 2: "stereo", 6: "5.1", 8: "7.1"}


def language_name(code: str) -> str:
    c = (code or "").lower().replace("_", "-").split("-")[0]
    if c in ("", "und"):
        return tr("언어 정보 없음")
    if c in LANG_NAMES:
        return tr(LANG_NAMES[c])
    loc = QLocale(c)                               # 그 밖은 그 언어 자체 이름 (D113)
    return loc.nativeLanguageName() if loc.language() != QLocale.Language.C else c.upper()


def audio_text(a: AudioStream) -> str:
    """예: "한국어 · Dolby Digital Plus 5.1 · 기본"."""
    codec = AUDIO_CODECS.get(a.codec, a.codec.upper())
    parts = [language_name(a.language),
             f"{codec} {CHANNELS.get(a.channels, f'{a.channels}ch')}"]
    if a.default:
        parts.append(tr("기본"))
    return " · ".join(parts)


def subtitle_text(t: SubtitleTrack, pct: int = 0) -> str:
    """예: "한국어 · 내장 SRT · 2352줄", "English · 영화.en.srt · 1342줄"."""
    where = (t.label if t.external
             else tr("내장 {fmt}", fmt=SUB_CODECS.get(t.codec, t.codec.upper())) if t.codec
             else tr("내장").strip())                     # 형식 정보가 없을 때
    tail = (tr("추출 중 {n}%", n=pct) if t.note == PENDING          # 뒤에서 추출 중 (D109)
            else tr(t.note) if t.note else tr("{n}줄", n=len(t.cues)))
    return " · ".join((language_name(t.language), where, tail))
