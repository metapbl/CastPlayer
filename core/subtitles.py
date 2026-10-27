"""자막: 후보 찾기, 문자 인코딩 판별, WebVTT 변환, 캐시.

- 외부 자막: 영상과 같은 폴더, 이름이 같은 파일 (영화.srt, 영화.ko.smi, 영화.kor.ass ...)
- SMI: 클래스(KRCC, ENCC 등)마다 트랙을 나눈다
- 내장 텍스트 자막: ffmpeg -c:s webvtt로 한 번에 모두 추출, cache/subtitles/에 저장
- 시간 기준: 영상 파일 시작 0초 (HLS tfdt, keyframes.py와 같은 기준)
  내장 추출은 -copyts를 쓰지 않으므로 ffmpeg가 파일 시작 시각을 빼서 0초 기준이 된다
- 싱크 조절: 트랙별 지연값을 요청 시점에 반영해 VTT를 만든다
"""
from __future__ import annotations

import codecs
import hashlib
import html
import json
import logging
import re
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .paths import cache_dir, ffmpeg_path
from .probe import MediaInfo, SubtitleStream
from .proc import NO_WINDOW, bind_to_job

_LOGGER = logging.getLogger(__name__)
_CACHE_VERSION = 1
VTT_MIME = "text/vtt"
SUB_OFF = "off"                      # PlaylistItem.subtitle_key: 자막 끔
SUB_EXTS = (".srt", ".smi", ".sami", ".ass", ".ssa", ".vtt")
TEXT_SUB_CODECS = {"subrip", "ass", "ssa", "mov_text", "webvtt", "text"}
SCALE_MIN, SCALE_MAX = 0.5, 2.0
LAST_CUE_LEN = 5.0                   # SMI 마지막 자막의 끝 시각이 없을 때 표시 시간(초)
ProgressFn = Callable[[int], None]

_LANG = {
    "ko": "ko", "kor": "ko", "korean": "ko", "kr": "ko",
    "en": "en", "eng": "en", "english": "en",
    "ja": "ja", "jpn": "ja", "jp": "ja", "japanese": "ja",
    "zh": "zh", "chi": "zh", "zho": "zh", "chs": "zh", "cht": "zh",
    "fr": "fr", "fre": "fr", "fra": "fr", "de": "de", "ger": "de", "deu": "de",
    "es": "es", "spa": "es",
}
_SMI_CLASS_LANG = {"KRCC": "ko", "KOCC": "ko", "KOKRCC": "ko", "ENCC": "en",
                   "EGCC": "en", "ENUSCC": "en", "JPCC": "ja", "JACC": "ja"}


class SubtitleError(RuntimeError):
    pass


def norm_lang(code: str | None) -> str:
    """'kor', 'ko-KR', 'korean' → 'ko'. 모르면 2글자 코드 그대로, 아니면 'und'."""
    c = (code or "").strip().lower().replace("_", "-")
    if c in _LANG:
        return _LANG[c]
    head = c.split("-")[0]
    return _LANG.get(head, head if len(head) == 2 and head.isalpha() else "und")


# ================= 자막 데이터 =================
@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str        # WebVTT 본문 (이스케이프 완료, <i><b><u>만 허용)


@dataclass
class SubtitleTrack:
    key: str                     # "ext:영화.smi:KRCC" / "emb:3"
    label: str
    language: str                # Cast language (ko, en, und ...)
    supported: bool
    cues: tuple[Cue, ...] = ()
    track_id: int = 0            # Cast trackId (지원 트랙만 1부터)
    external: bool = False
    note: str = ""               # 지원 안 함 / 읽기 실패 / 추출 실패 / 비어 있음

    @property
    def display(self) -> str:
        parts = [self.label, f"({self.language})"]
        parts.append(f"({self.note})" if self.note else f"{len(self.cues)}개")
        return " ".join(parts)


# ================= 문자 인코딩 =================
def read_text(path: Path) -> str:
    """UTF-16 BOM → UTF-8(BOM 포함) → CP949 → charset-normalizer 순으로 판별."""
    raw = path.read_bytes()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16", "replace")
    if raw.startswith(codecs.BOM_UTF8):
        return raw[3:].decode("utf-8", "replace")
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            _LOGGER.debug("자막 인코딩 판별: %s → %s", path.name, best.encoding)
            return str(best)
    except ImportError:
        _LOGGER.debug("charset-normalizer 없음, CP949로 읽음")
    return raw.decode("cp949", "replace")


# ================= 본문 정리 =================
_KEEP_RE = re.compile(r"<\s*(/?)\s*([ibu])\s*>", re.I)
_TAG_RE = re.compile(r"<[^>]*>")
_ASS_TAG_RE = re.compile(r"\{\\[^}]*\}")


def clean_markup(s: str) -> str:
    """<i><b><u>만 남기고 태그 제거, &<> 이스케이프, 빈 줄 제거."""
    s = _ASS_TAG_RE.sub("", s)
    s = _KEEP_RE.sub(lambda m: f"\x01{m[1]}{m[2].lower()}\x02", s)
    s = _TAG_RE.sub("", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace("\x01", "<").replace("\x02", ">")
    lines = (ln.strip() for ln in s.split("\n"))
    return "\n".join(ln for ln in lines if ln)


# ================= SRT / WebVTT =================
_TS = r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})"
_CUE_RE = re.compile(rf"{_TS}\s*-->\s*{_TS}")


def _secs(h: str | None, m: str, s: str, frac: str) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(frac.ljust(3, "0")) / 1000


def parse_timed_text(text: str) -> list[Cue]:
    """SRT와 WebVTT 공통: '-->' 줄 다음부터 빈 줄 전까지가 자막 1개."""
    out: list[Cue] = []
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i, n = 0, len(lines)
    while i < n:
        m = _CUE_RE.search(lines[i])
        i += 1
        if not m:
            continue
        body = []
        while i < n and lines[i].strip() and not _CUE_RE.search(lines[i]):
            body.append(lines[i])
            i += 1
        g = m.groups()
        start, end = _secs(*g[:4]), _secs(*g[4:])
        txt = clean_markup("\n".join(body))
        if txt and end > start:
            out.append(Cue(start, end, txt))
    out.sort(key=lambda c: c.start)
    return out


# ================= SMI =================
_SYNC_RE = re.compile(r"<sync\b([^>]*)>", re.I)
_START_RE = re.compile(r"start\s*=\s*['\"]?(-?\d+)", re.I)
_END_RE = re.compile(r"end\s*=\s*['\"]?(-?\d+)", re.I)
_P_RE = re.compile(r"<p\b([^>]*)>", re.I)
_CLASS_RE = re.compile(r"class\s*=\s*['\"]?([\w-]+)", re.I)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_STYLE_RE = re.compile(r"\.([\w-]+)\s*\{([^}]*)\}", re.S)
_STYLE_LANG_RE = re.compile(r"lang\s*:\s*([\w-]+)", re.I)
_STYLE_NAME_RE = re.compile(r"name\s*:\s*([^;]+)", re.I)


def parse_smi(text: str) -> dict[str, tuple[str, str, list[Cue]]]:
    """{클래스: (언어, 이름, 자막)}. &nbsp;만 있는 SYNC는 그 클래스의 자막 지우기."""
    body_at = re.search(r"<body", text, re.I)
    head = text[:body_at.start()] if body_at else ""
    styles: dict[str, tuple[str, str]] = {}
    for m in _STYLE_RE.finditer(head):
        lm, nm = _STYLE_LANG_RE.search(m[2]), _STYLE_NAME_RE.search(m[2])
        styles[m[1].upper()] = (norm_lang(lm[1]) if lm else "und",
                                nm[1].strip() if nm else "")

    events: dict[str, list[tuple[float, float | None, str]]] = {}
    syncs = list(_SYNC_RE.finditer(text))
    for k, m in enumerate(syncs):
        sm = _START_RE.search(m[1])
        if not sm:
            continue
        start = int(sm[1]) / 1000
        em = _END_RE.search(m[1])
        end = int(em[1]) / 1000 if em else None
        stop = syncs[k + 1].start() if k + 1 < len(syncs) else len(text)
        block = re.split(r"</body", text[m.end():stop], flags=re.I)[0]
        ps = list(_P_RE.finditer(block))
        parts = [("", block)] if not ps else []
        for j, pm in enumerate(ps):
            cm = _CLASS_RE.search(pm[1])
            pe = ps[j + 1].start() if j + 1 < len(ps) else len(block)
            parts.append((cm[1].upper() if cm else "", block[pm.end():pe]))
        for cls, raw in parts:
            raw = re.sub(r"\s*\n\s*", " ", raw)          # 원본 줄바꿈은 공백
            txt = clean_markup(_BR_RE.sub("\n", raw))      # <br>만 줄바꿈
            events.setdefault(cls, []).append((start, end, txt))

    result: dict[str, tuple[str, str, list[Cue]]] = {}
    for cls, evs in events.items():
        evs.sort(key=lambda e: e[0])
        cues = []
        for idx, (s, e, txt) in enumerate(evs):
            if not txt:
                continue
            nxt = evs[idx + 1][0] if idx + 1 < len(evs) else None
            end = e if e is not None else (nxt if nxt is not None else s + LAST_CUE_LEN)
            if end > s:
                cues.append(Cue(s, end, txt))
        if not cues:
            continue
        lang, name = styles.get(cls, ("und", ""))
        if lang == "und":
            lang = _SMI_CLASS_LANG.get(cls, "und")
        result[cls] = (lang, name, cues)
    return result


# ================= ASS / SSA =================
def _ass_time(s: str) -> float:
    h, m, rest = s.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def parse_ass(text: str) -> list[Cue]:
    """[Events]의 Dialogue만 읽음. 스타일은 버리고 글자만 살림."""
    out: list[Cue] = []
    fmt: list[str] | None = None
    in_events = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            in_events = s.lower() == "[events]"
            continue
        if not in_events:
            continue
        low = s.lower()
        if low.startswith("format:"):
            fmt = [f.strip().lower() for f in s[7:].split(",")]
        elif low.startswith("dialogue:") and fmt:
            vals = s[9:].split(",", len(fmt) - 1)
            if len(vals) < len(fmt):
                continue
            row = dict(zip(fmt, vals))
            try:
                start, end = _ass_time(row["start"]), _ass_time(row["end"])
            except (KeyError, ValueError):
                continue
            raw = re.sub(r"\{[^}]*\}", "", row.get("text", ""))
            raw = raw.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
            txt = clean_markup(raw)
            if txt and end > start:
                out.append(Cue(start, end, txt))
    out.sort(key=lambda c: c.start)
    return out


# ================= WebVTT 출력 =================
def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def render_vtt(cues: tuple[Cue, ...], delay: float = 0.0) -> bytes:
    """delay > 0: 자막을 늦춤, < 0: 당김. 0초 이전으로 밀린 자막은 잘라냄."""
    out = ["WEBVTT", ""]
    for c in cues:
        s, e = c.start + delay, c.end + delay
        if e <= 0:
            continue
        out += [f"{_ts(max(0.0, s))} --> {_ts(e)}", c.text, ""]
    return "\n".join(out).encode("utf-8")


def clamp_scale(v: float) -> float:
    return round(min(SCALE_MAX, max(SCALE_MIN, v)), 2)


def text_style(scale: float = 1.0) -> dict:
    """투명 배경 + 검은 테두리 (pychromecast 기본 스타일과 같음) + 글자 크기."""
    return {"backgroundColor": "#FFFFFF00", "foregroundColor": "#FFFFFFFF",
            "edgeType": "OUTLINE", "edgeColor": "#000000FF",
            "fontScale": clamp_scale(scale)}


# ================= 외부 자막 =================
def find_external(video: Path) -> list[Path]:
    stem = video.stem.lower()
    try:
        entries = list(video.parent.iterdir())
    except OSError:
        return []
    out = [p for p in entries
           if p.suffix.lower() in SUB_EXTS and p.is_file()
           and (p.stem.lower() == stem or p.stem.lower().startswith(stem + "."))]
    return sorted(out, key=lambda p: p.name.lower())


def _file_lang(video: Path, path: Path) -> str:
    """'영화.kor.srt' → ko. 이름 뒤쪽 조각부터 언어 코드를 찾음."""
    for part in reversed(path.stem[len(video.stem):].strip(".").split(".")):
        lang = norm_lang(part)
        if lang != "und":
            return lang
    return "und"


def _external_tracks(video: Path) -> list[SubtitleTrack]:
    tracks: list[SubtitleTrack] = []
    for path in find_external(video):
        ext, flang = path.suffix.lower(), _file_lang(video, path)
        try:
            text = read_text(path)
            if ext in (".smi", ".sami"):
                classes = parse_smi(text)
                if not classes:
                    raise ValueError("자막 없음")
                for cls, (lang, _name, cues) in classes.items():
                    tracks.append(SubtitleTrack(
                        key=f"ext:{path.name}:{cls}",
                        label=f"{path.name} [{cls}]" if cls else path.name,
                        language=lang if lang != "und" else flang,
                        supported=True, cues=tuple(cues), external=True))
                continue
            cues = parse_ass(text) if ext in (".ass", ".ssa") else parse_timed_text(text)
            if not cues:
                raise ValueError("자막 없음")
            tracks.append(SubtitleTrack(f"ext:{path.name}", path.name, flang, True,
                                        tuple(cues), external=True))
        except (OSError, ValueError) as err:
            _LOGGER.warning("외부 자막 읽기 실패: %s (%s)", path.name, err)
            tracks.append(SubtitleTrack(f"ext:{path.name}", path.name, flang, False,
                                        external=True, note="읽기 실패"))
    return tracks


# ================= 내장 자막 =================
def _cache_file(path: Path) -> Path:
    st = path.stat()
    key = f"{_CACHE_VERSION}|{path.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    return cache_dir() / "subtitles" / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")


def _drain(stream, tail: deque[str]) -> None:
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", "replace").rstrip()
        if line:
            tail.append(line)


def _run_with_progress(cmd: list[str], duration: float,
                       on_progress: ProgressFn | None) -> None:
    _LOGGER.debug("자막 추출: %s", subprocess.list2cmdline(cmd))
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    except OSError as err:
        raise SubtitleError(f"ffmpeg 실행 실패: {err}") from err
    bind_to_job(proc)
    tail: deque[str] = deque(maxlen=5)
    drain = threading.Thread(target=_drain, args=(proc.stderr, tail),
                             name="sub-stderr", daemon=True)
    drain.start()
    last = -1
    try:
        for raw in proc.stdout:
            line = raw.decode("ascii", "replace").strip()
            if not (line.startswith("out_time_us=") and on_progress and duration > 0):
                continue
            try:
                us = int(line.split("=", 1)[1])
            except ValueError:
                continue                       # N/A
            pct = int(min(99, max(0, us / 1e6 * 100 / duration)))
            if pct != last:
                last = pct
                on_progress(pct)
    finally:
        proc.stdout.close()
        rc = proc.wait()
        drain.join(2)
    if rc != 0:
        raise SubtitleError(f"자막 추출 실패: {tail[-1] if tail else f'종료 코드 {rc}'}")
    if on_progress:
        on_progress(100)


def extract_embedded(info: MediaInfo, streams: list[SubtitleStream],
                     on_progress: ProgressFn | None = None) -> dict[int, list[Cue]]:
    """여러 내장 트랙을 ffmpeg 한 번으로 추출. {스트림 index: 자막}."""
    try:
        cf = _cache_file(info.path)
    except OSError as err:
        raise SubtitleError(f"파일 정보 읽기 실패: {err}") from err
    cached: dict[int, list[Cue]] = {}
    try:
        data = json.loads(cf.read_text(encoding="utf-8"))
        cached = {int(k): [Cue(*c) for c in v] for k, v in data.items()}
    except (OSError, ValueError, TypeError):
        cached = {}
    need = [s for s in streams if s.index not in cached]
    if not need:
        _LOGGER.debug("자막 캐시 사용: %s", cf.name)
        return cached

    tmp = cf.parent / (cf.stem + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        cmd = [str(ffmpeg_path()), "-hide_banner", "-nostdin", "-loglevel", "error",
               "-nostats", "-progress", "pipe:1", "-y", "-i", str(info.path)]
        for s in need:
            cmd += ["-map", f"0:{s.index}", "-c:s", "webvtt", "-f", "webvtt",
                    str(tmp / f"{s.index}.vtt")]
        _run_with_progress(cmd, info.duration, on_progress)
        for s in need:
            p = tmp / f"{s.index}.vtt"
            cached[s.index] = parse_timed_text(read_text(p)) if p.exists() else []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    try:
        cf.write_text(json.dumps({str(k): [[c.start, c.end, c.text] for c in v]
                                  for k, v in cached.items()}, ensure_ascii=False),
                      encoding="utf-8")
    except OSError:
        _LOGGER.warning("자막 캐시 저장 실패", exc_info=True)
    _LOGGER.info("내장 자막 추출: %s", ", ".join(f"#{k} {len(v)}개" for k, v in cached.items()))
    return cached


# ================= 묶음 =================
class SubtitleSet:
    """파일 1개의 자막 트랙 전체. get(name)으로 /sub/<token>/<trackId>.vtt 요청 처리."""

    def __init__(self, tracks: list[SubtitleTrack]) -> None:
        self.tracks = tracks
        self._by_id = {t.track_id: t for t in tracks if t.supported}
        self._delay: dict[int, float] = {}
        self._lock = threading.Lock()

    @property
    def supported(self) -> list[SubtitleTrack]:
        return [t for t in self.tracks if t.supported]

    def track(self, track_id: int | None) -> SubtitleTrack | None:
        return self._by_id.get(track_id) if track_id else None

    def find(self, key: str | None) -> SubtitleTrack | None:
        return next((t for t in self.tracks if t.supported and t.key == key), None)

    def auto_select(self) -> SubtitleTrack | None:
        """외부 한국어 → 내장 한국어 → 첫 외부 자막 → 끄기."""
        ok = self.supported
        for pred in (lambda t: t.external and t.language == "ko",
                     lambda t: not t.external and t.language == "ko",
                     lambda t: t.external):
            found = next((t for t in ok if pred(t)), None)
            if found:
                return found
        return None

    def delay(self, track_id: int) -> float:
        with self._lock:
            return self._delay.get(track_id, 0.0)

    def set_delay(self, track_id: int, sec: float) -> None:
        with self._lock:
            self._delay[track_id] = round(sec, 3)

    def get(self, name: str) -> tuple[bytes, str] | None:
        m = re.fullmatch(r"(\d+)\.vtt", name)
        t = self.track(int(m[1])) if m else None
        if t is None:
            return None
        d = self.delay(t.track_id)
        _LOGGER.debug("자막 요청: 트랙 %d (지연 %+.2f초)", t.track_id, d)
        return render_vtt(t.cues, d), VTT_MIME

    def cast_tracks(self, base_url: str) -> list[dict]:
        """MediaInformation.tracks."""
        return [{"trackId": t.track_id, "type": "TEXT", "subtype": "SUBTITLES",
                 "trackContentId": f"{base_url}/{t.track_id}.vtt",
                 "trackContentType": VTT_MIME, "name": t.label, "language": t.language}
                for t in self.supported]


def load_subtitles(info: MediaInfo, on_progress: ProgressFn | None = None) -> SubtitleSet:
    tracks = _external_tracks(info.path)
    text_streams = [s for s in info.subtitles if s.codec in TEXT_SUB_CODECS]
    cues_by_index: dict[int, list[Cue]] = {}
    if text_streams:
        try:
            cues_by_index = extract_embedded(info, text_streams, on_progress)
        except SubtitleError as err:
            _LOGGER.warning("%s", err)
    for s in info.subtitles:
        label = f"내장#{s.order + 1} {s.language or 'und'} {s.codec}"
        if s.title:
            label += f" '{s.title}'"
        lang, key = norm_lang(s.language), f"emb:{s.index}"
        if s.codec not in TEXT_SUB_CODECS:
            tracks.append(SubtitleTrack(key, label, lang, False, note="지원 안 함"))
        elif s.index not in cues_by_index:
            tracks.append(SubtitleTrack(key, label, lang, False, note="추출 실패"))
        elif not cues_by_index[s.index]:
            tracks.append(SubtitleTrack(key, label, lang, False, note="비어 있음"))
        else:
            tracks.append(SubtitleTrack(key, label, lang, True, tuple(cues_by_index[s.index])))
    next_id = 1
    for t in tracks:
        if t.supported:
            t.track_id = next_id
            next_id += 1
    return SubtitleSet(tracks)
