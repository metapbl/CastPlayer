"""영상 키프레임 시각 목록 (REMUX HLS 조각 경계용) + 디스크 캐시.

시각은 파일 시작 시각(format start_time) 기준 상대값(초).
ffmpeg -ss, -copyts -start_at_zero 출력도 같은 기준이므로 그대로 조각 시작점으로 쓴다.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from .i18n import tr
from .paths import cache_dir, ffprobe_path
from .proc import NO_WINDOW, bind_to_job

_LOGGER = logging.getLogger(__name__)
_CACHE_VERSION = 1
# ffprobe가 오류로 끝나도 전체 길이의 이 비율 이상 읽었으면 결과 사용 (TS 끝 손상 등)
COMPLETE_RATIO = 0.98


class KeyframeError(RuntimeError):
    pass


def _cache_file(path: Path) -> Path:
    st = path.stat()
    key = f"{_CACHE_VERSION}|{path.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    name = hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json"
    return cache_dir() / "keyframes" / name


def _num(s: str | None) -> float | None:
    try:
        return float(s) if s else None
    except ValueError:
        return None   # "N/A"


def _fields(line: str) -> dict[str, str]:
    """compact 출력 'pts_time=1.2|dts_time=1.1|flags=K__|' → dict.
    TS 등은 줄 끝에 빈 칸이 붙으므로 위치가 아닌 이름으로 찾는다 (실측)."""
    return dict(kv.split("=", 1) for kv in line.split("|") if "=" in kv)


def _start_time(path: Path) -> float:
    cmd = [str(ffprobe_path()), "-v", "error", "-show_entries", "format=start_time",
           "-of", "default=nw=1:nk=1", str(path)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30,
                           creationflags=NO_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    return _num(r.stdout.decode("ascii", "replace").strip()) or 0.0


def _drain(stream, tail: deque[str]) -> None:
    """stderr를 계속 읽어 마지막 줄만 보관 (파이프가 차서 멈추는 것 방지)."""
    for raw in iter(stream.readline, b""):
        line = raw.decode("utf-8", "replace").rstrip()
        if line:
            tail.append(line)


def keyframes(path: Path, duration: float,
              on_progress: Callable[[int], None] | None = None) -> list[float]:
    """키프레임 시각 목록. 캐시가 있으면 즉시, MKV·MP4는 파일 안 목차만 읽고(D098),
    목차가 없거나 못 믿으면 파일 전체를 읽어 분석."""
    cf = _cache_file(path)
    try:
        cached = json.loads(cf.read_text(encoding="utf-8"))
        if isinstance(cached, list) and cached:
            _LOGGER.debug("키프레임 캐시 사용: %s (%d개)", cf.name, len(cached))
            return [float(x) for x in cached]
    except (OSError, ValueError):
        pass

    base = _start_time(path)
    out = index_keyframes(path, base, duration)
    how = "목차"   # 로그 전용
    if out is None:
        out, how = _scan_keyframes(path, base, duration, on_progress), "전체 읽기"   # 로그 전용
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        _LOGGER.warning("키프레임 캐시 저장 실패", exc_info=True)
    if on_progress:
        on_progress(100)
    _LOGGER.info("키프레임 %d개, %s (시작 시각 보정 %.3f초)", len(out), how, base)
    return out


def _scan_keyframes(path: Path, base: float, duration: float,
                    on_progress: Callable[[int], None] | None) -> list[float]:
    """ffprobe로 영상 패킷을 처음부터 끝까지 읽어 K 표시가 있는 시각을 모은다 (느림)."""
    # csv → compact (이름으로 파싱)
    cmd = [str(ffprobe_path()), "-v", "error", "-select_streams", "v:0",
           "-show_entries", "packet=pts_time,dts_time,flags", "-of", "compact=p=0",
           str(path)]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    except OSError as err:
        raise KeyframeError(tr("ffprobe 실행 실패: {err}", err=err)) from err
    bind_to_job(proc)
    assert proc.stdout is not None   # PIPE로 열었음
    tail: deque[str] = deque(maxlen=5)
    drain = threading.Thread(target=_drain, args=(proc.stderr, tail),
                             name="kf-stderr", daemon=True)
    drain.start()

    out: list[float] = []
    samples: list[str] = []      # 실패 시 진단용 앞 몇 줄
    last_pct = -1
    reached = 0.0
    try:
        for raw in proc.stdout:
            line = raw.decode("ascii", "replace").strip()
            if len(samples) < 5 and line:
                samples.append(line)
            f = _fields(line)
            if "flags" not in f:
                continue
            t = _num(f.get("pts_time"))
            if t is None:
                t = _num(f.get("dts_time"))
            if t is None:
                continue
            rel = t - base
            reached = max(reached, rel)
            if f["flags"].startswith("K"):
                out.append(round(max(0.0, rel), 6))
            if on_progress and duration > 0:
                pct = int(min(99, max(0, rel * 100 / duration)))
                if pct != last_pct:
                    last_pct = pct
                    on_progress(pct)
    finally:
        proc.stdout.close()
        rc = proc.wait()
        drain.join(2)

    err = tail[-1] if tail else tr("종료 코드 {rc}", rc=rc)
    if not out:
        _LOGGER.error("키프레임 0개. ffprobe 출력 앞부분:\n%s\nstderr:\n%s",
                      "\n".join(samples), "\n".join(tail))
        raise KeyframeError(tr("키프레임 분석 실패: {err}", err=err))
    if rc != 0:
        if duration > 0 and reached < duration * COMPLETE_RATIO:
            _LOGGER.error("ffprobe 오류:\n%s", "\n".join(tail))
            raise KeyframeError(
                tr("키프레임 분석 실패 ({reached}/{duration}초에서 중단): {err}",
                   reached=f"{reached:.0f}", duration=f"{duration:.0f}", err=err))
        _LOGGER.warning("ffprobe 종료 코드 %d, %.0f/%.0f초까지 읽어 결과 사용: %s",
                        rc, reached, duration, err)

    return sorted(set(out))


# ================= 파일 안 목차 (D098) =================
SPARSE_GAP = 10.0     # MKV 목차의 키프레임 평균 간격이 이보다 길면 일부만 적힌 것으로 보고 안 믿음 (D101)


def index_keyframes(path: Path, base: float, duration: float) -> list[float] | None:
    """MKV Cues·MP4 stss로 키프레임 시각. 못 읽거나 못 믿으면 None (호출한 쪽이 전체 읽기)."""
    try:
        with path.open("rb") as f:
            head = f.read(12)
            f.seek(0)
            if head[:4] == b"\x1a\x45\xdf\xa3":
                times, kind = _mkv_cues(f), "MKV Cues"
                if times and duration > 0 and duration / len(times) > SPARSE_GAP:
                    _LOGGER.info("MKV 목차가 듬성듬성함 (%d개 / %.0f초) → 전체 읽기",
                                 len(times), duration)
                    return None
            elif head[4:8] == b"ftyp":
                times, kind = _mp4_sync(f), "MP4 stss"
            else:
                return None
    except (OSError, ValueError, IndexError) as err:
        _LOGGER.info("키프레임 목차를 못 읽음 → 전체 읽기: %s", err)
        return None
    if not times:
        _LOGGER.info("키프레임 목차 없음 → 전체 읽기")
        return None
    _LOGGER.info("키프레임 목차 사용: %s", kind)
    return sorted({round(max(0.0, t - base), 6) for t in times})


# ---- MKV (EBML) ----
_EBML, _SEGMENT, _SEEKHEAD, _SEEK, _SEEK_ID, _SEEK_POS = (
    0x1A45DFA3, 0x18538067, 0x114D9B74, 0x4DBB, 0x53AB, 0x53AC)
_INFO, _SCALE, _TRACKS, _TRACK, _TRACK_NO, _TRACK_TYPE = (
    0x1549A966, 0x2AD7B1, 0x1654AE6B, 0xAE, 0xD7, 0x83)
_CUES, _CUE_POINT, _CUE_TIME, _CUE_POS, _CUE_TRACK, _CLUSTER = (
    0x1C53BB6B, 0xBB, 0xB3, 0xB7, 0xF7, 0x1F43B675)


def _vint(f, keep_marker: bool) -> tuple[int, int]:
    """EBML 가변 길이 정수 → (값, 바이트 수). 크기가 "모름"(모든 비트 1)이면 값 -1."""
    b = f.read(1)
    if not b:
        raise ValueError("EBML: 파일 끝")   # 로그 전용
    first = b[0]
    n = 1
    while n <= 8 and not first & (0x80 >> (n - 1)):
        n += 1
    if n > 8:
        raise ValueError("EBML: 잘못된 길이")   # 로그 전용
    rest = f.read(n - 1)
    if len(rest) != n - 1:
        raise ValueError("EBML: 파일 끝")   # 로그 전용
    value = first if keep_marker else first & (0xFF >> n)
    for x in rest:
        value = value << 8 | x
    if not keep_marker and value == (1 << (7 * n)) - 1:
        return -1, n
    return value, n


def _header(f) -> tuple[int, int]:
    """요소 머리 → (ID, 내용 크기). 크기 -1 = 모름."""
    eid, _ = _vint(f, True)
    size, _ = _vint(f, False)
    return eid, size


def _children(data: bytes) -> list[tuple[int, bytes]]:
    """메모리에 읽은 마스터 요소 내용 → [(ID, 내용)]."""
    f, out = io.BytesIO(data), []
    while f.tell() < len(data):
        eid, size = _header(f)
        if size < 0:
            raise ValueError("EBML: 크기 모름")   # 로그 전용
        out.append((eid, f.read(size)))
    return out


def _uint(data: bytes) -> int:
    return int.from_bytes(data, "big")


def _mkv_cues(f) -> list[float]:
    """Segment의 Info·Tracks·Cues만 찾아 읽는다 (Cluster는 건너뜀). 첫 영상 트랙의 CueTime(초)."""
    eid, size = _header(f)
    if eid != _EBML:
        return []
    f.seek(size, 1)
    eid, size = _header(f)
    if eid != _SEGMENT:
        return []
    seg = f.tell()
    end = seg + size if size >= 0 else f.seek(0, 2)
    f.seek(seg)
    seek: dict[int, int] = {}
    scale, vtrack, cues = 1_000_000, None, None
    while f.tell() < end and cues is None:
        eid, size = _header(f)
        start = f.tell()
        if eid == _CLUSTER and _CUES in seek:          # 영상 데이터는 건너뛰고 목차로 바로
            f.seek(seg + seek[_CUES])
            continue
        if size < 0:
            return []                                  # 크기를 모르는 요소 (실시간 녹화 등)
        if eid == _SEEKHEAD:
            for cid, body in _children(f.read(size)):
                if cid == _SEEK:
                    kv = dict(_children(body))
                    seek[_uint(kv.get(_SEEK_ID, b""))] = _uint(kv.get(_SEEK_POS, b""))
        elif eid == _INFO:
            for cid, body in _children(f.read(size)):
                if cid == _SCALE:
                    scale = _uint(body)
        elif eid == _TRACKS:
            for cid, body in _children(f.read(size)):
                kv = dict(_children(body)) if cid == _TRACK else {}
                if vtrack is None and _uint(kv.get(_TRACK_TYPE, b"")) == 1:
                    vtrack = _uint(kv.get(_TRACK_NO, b""))
        elif eid == _CUES:
            cues = f.read(size)
        f.seek(start + size)
    if cues is None or vtrack is None:
        return []
    times = []
    for cid, point in _children(cues):
        if cid != _CUE_POINT:
            continue
        kids = _children(point)
        t = next((_uint(b) for k, b in kids if k == _CUE_TIME), None)
        tracks = {_uint(dict(_children(b)).get(_CUE_TRACK, b"")) for k, b in kids if k == _CUE_POS}
        if t is not None and vtrack in tracks:
            times.append(t * scale / 1e9)
    return times


# ---- MP4 (ISO BMFF) ----
def _boxes(data: bytes, pos: int = 0, end: int | None = None):
    """메모리 안 상자들 → (종류, 내용 시작, 내용 끝)."""
    end = len(data) if end is None else end
    while pos + 8 <= end:
        size, kind = int.from_bytes(data[pos:pos + 4], "big"), data[pos + 4:pos + 8]
        head = 8
        if size == 1:
            size, head = int.from_bytes(data[pos + 8:pos + 16], "big"), 16
        elif size == 0:
            size = end - pos
        if size < head:
            raise ValueError("MP4: 잘못된 상자 크기")   # 로그 전용
        yield kind, pos + head, pos + size
        pos += size


def _find(data: bytes, start: int, end: int, *path: bytes) -> tuple[int, int] | None:
    for kind, s, e in _boxes(data, start, end):
        if kind == path[0]:
            return (s, e) if len(path) == 1 else _find(data, s, e, *path[1:])
    return None


def _moov(f) -> bytes:
    """파일 맨 위 상자를 크기로 건너뛰며 moov만 읽는다 (mdat는 읽지 않음)."""
    f.seek(0, 2)
    total = f.tell()
    pos = 0
    while pos + 8 <= total:
        f.seek(pos)
        h = f.read(16)
        size, kind = int.from_bytes(h[:4], "big"), h[4:8]
        head = 8
        if size == 1:
            size, head = int.from_bytes(h[8:16], "big"), 16
        elif size == 0:
            size = total - pos
        if size < head:
            raise ValueError("MP4: 잘못된 상자 크기")   # 로그 전용
        if kind == b"moov":
            f.seek(pos)
            data = f.read(size)
            return data[head:]
        pos += size
    return b""


def _u(d: bytes, i: int, n: int, signed: bool = False) -> int:
    return int.from_bytes(d[i:i + n], "big", signed=signed)


def _mp4_sync(f) -> list[float]:
    """첫 영상 트랙의 동기 표본(stss) 시각(초). 표시 시각 = (DTS + ctts − elst 시작)/timescale + 빈 편집."""
    moov = _moov(f)
    if not moov:
        return []
    mvhd = _find(moov, 0, len(moov), b"mvhd")
    movie_scale = _u(moov, mvhd[0] + (20 if moov[mvhd[0]] == 1 else 12), 4) if mvhd else 1000
    for kind, s, e in _boxes(moov):
        if kind != b"trak":
            continue
        hdlr = _find(moov, s, e, b"mdia", b"hdlr")
        if not hdlr or moov[hdlr[0] + 8:hdlr[0] + 12] != b"vide":
            continue
        mdhd = _find(moov, s, e, b"mdia", b"mdhd")
        stbl = _find(moov, s, e, b"mdia", b"minf", b"stbl")
        if not mdhd or not stbl:
            return []
        scale = _u(moov, mdhd[0] + (20 if moov[mdhd[0]] == 1 else 12), 4)
        dts: list[int] = []
        stts = _find(moov, *stbl, b"stts")
        if stts:
            t = 0
            for k in range(_u(moov, stts[0] + 4, 4)):
                count, delta = _u(moov, stts[0] + 8 + k * 8, 4), _u(moov, stts[0] + 12 + k * 8, 4)
                for _ in range(count):
                    dts.append(t)
                    t += delta
        if not dts:
            return []                                  # 조각 MP4 (표본이 moof에 있음)
        cts = [0] * len(dts)
        ctts = _find(moov, *stbl, b"ctts")
        if ctts:
            n = 0
            for k in range(_u(moov, ctts[0] + 4, 4)):
                count = _u(moov, ctts[0] + 8 + k * 8, 4)
                off = _u(moov, ctts[0] + 12 + k * 8, 4, signed=True)
                for _ in range(count):
                    if n < len(cts):
                        cts[n] = off
                    n += 1
        stss = _find(moov, *stbl, b"stss")
        sync = ([_u(moov, stss[0] + 8 + k * 4, 4) - 1 for k in range(_u(moov, stss[0] + 4, 4))]
                if stss else range(len(dts)))          # stss가 없으면 모든 표본이 키프레임
        media_start, empty = 0, 0.0
        elst = _find(moov, s, e, b"edts", b"elst")
        if elst:
            v1 = moov[elst[0]] == 1
            step = 20 if v1 else 12
            for k in range(_u(moov, elst[0] + 4, 4)):
                at = elst[0] + 8 + k * step
                seg_dur = _u(moov, at, 8 if v1 else 4)
                mtime = _u(moov, at + (8 if v1 else 4), 8 if v1 else 4, signed=True)
                if mtime == -1:
                    empty += seg_dur / movie_scale     # 빈 편집 = 시작 지연
                else:
                    media_start = mtime
                    break
        return [(dts[i] + cts[i] - media_start) / scale + empty
                for i in sync if 0 <= i < len(dts)]
    return []
