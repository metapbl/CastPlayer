"""썸네일 (F9-12, D097, D101): 표지가 있으면 표지, 없으면 영상 길이 10% 지점 한 장면.
가로 320px JPEG로 cache/thumbs/에 둔다. 실패하면 None (화면은 글자만)."""
from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

from .paths import cache_dir, ffmpeg_path
from .probe import MediaInfo
from .proc import NO_WINDOW

_LOGGER = logging.getLogger(__name__)
_CACHE_VERSION = 1
THUMB_W = 320
SCENE_AT = 0.10       # 처음 몇 초는 검은 화면·로고인 경우가 많음


def _cache_file(path: Path) -> Path:
    st = path.stat()
    key = f"{_CACHE_VERSION}|{path.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    return cache_dir() / "thumbs" / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".jpg")


def thumbnail(info: MediaInfo, timeout: float = 30.0) -> Path | None:
    """썸네일 파일 경로. 캐시가 있으면 바로, 없으면 ffmpeg로 한 장 만든다 (느리면 수 초)."""
    try:
        out = _cache_file(info.path)
    except OSError:
        return None
    if out.is_file():
        return out
    cmd = [str(ffmpeg_path()), "-v", "error", "-y"]
    if info.cover is not None:
        cmd += ["-i", str(info.path), "-map", f"0:{info.cover}"]
    elif info.video is not None:
        cmd += ["-ss", f"{info.duration * SCENE_AT:.3f}", "-i", str(info.path),
                "-map", f"0:{info.video.index}"]
    else:
        return None
    tmp = out.with_suffix(".tmp.jpg")
    cmd += ["-frames:v", "1", "-vf", f"scale={THUMB_W}:-2", "-q:v", "4", str(tmp)]
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW, check=False)
        if r.returncode != 0 or not tmp.is_file():
            _LOGGER.warning("썸네일 만들기 실패: %s",
                            r.stderr.decode("utf-8", "replace").strip()[-300:])
            return None
        tmp.replace(out)
    except (OSError, subprocess.TimeoutExpired) as err:
        _LOGGER.warning("썸네일 만들기 실패: %s", err)
        return None
    _LOGGER.info("썸네일: %s", "표지" if info.cover is not None else f"{SCENE_AT:.0%} 지점")
    return out
