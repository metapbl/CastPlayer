"""영상 키프레임 시각 목록 (REMUX HLS 조각 경계용) + 디스크 캐시.

시각은 파일 시작 시각(format start_time) 기준 상대값(초).
ffmpeg -ss, -copyts -start_at_zero 출력도 같은 기준이므로 그대로 조각 시작점으로 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

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
    """키프레임 시각 목록. 캐시가 있으면 즉시 반환, 없으면 파일 전체를 읽어 분석."""
    cf = _cache_file(path)
    try:
        cached = json.loads(cf.read_text(encoding="utf-8"))
        if isinstance(cached, list) and cached:
            _LOGGER.debug("키프레임 캐시 사용: %s (%d개)", cf.name, len(cached))
            return [float(x) for x in cached]
    except (OSError, ValueError):
        pass

    base = _start_time(path)
    # csv → compact (이름으로 파싱)
    cmd = [str(ffprobe_path()), "-v", "error", "-select_streams", "v:0",
           "-show_entries", "packet=pts_time,dts_time,flags", "-of", "compact=p=0",
           str(path)]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, creationflags=NO_WINDOW)
    except OSError as err:
        raise KeyframeError(f"ffprobe 실행 실패: {err}") from err
    bind_to_job(proc)
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

    err = tail[-1] if tail else f"종료 코드 {rc}"
    if not out:
        _LOGGER.error("키프레임 0개. ffprobe 출력 앞부분:\n%s\nstderr:\n%s",
                      "\n".join(samples), "\n".join(tail))
        raise KeyframeError(f"키프레임 분석 실패: {err}")
    if rc != 0:
        if duration > 0 and reached < duration * COMPLETE_RATIO:
            _LOGGER.error("ffprobe 오류:\n%s", "\n".join(tail))
            raise KeyframeError(
                f"키프레임 분석 실패 ({reached:.0f}/{duration:.0f}초에서 중단): {err}")
        _LOGGER.warning("ffprobe 종료 코드 %d, %.0f/%.0f초까지 읽어 결과 사용: %s",
                        rc, reached, duration, err)

    out = sorted(set(out))
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(out), encoding="utf-8")
    except OSError:
        _LOGGER.warning("키프레임 캐시 저장 실패", exc_info=True)
    if on_progress:
        on_progress(100)
    _LOGGER.info("키프레임 %d개 (시작 시각 보정 %.3f초)", len(out), base)
    return out
