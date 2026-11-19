"""썸네일 (F9-12, D097, D101, D102): 표지가 있으면 표지, 없으면 영상 길이 10% 지점 한 장면.
가로 320px JPEG 바이트. 임시 폴더에 만들어 읽은 뒤 바로 지워 캐시에 남기지 않는다.
실패하면 None (화면은 글자만)."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from .paths import ffmpeg_path
from .probe import MediaInfo
from .proc import NO_WINDOW

_LOGGER = logging.getLogger(__name__)
THUMB_W = 320
SCENE_AT = 0.10       # 처음 몇 초는 검은 화면·로고인 경우가 많음


def thumbnail(info: MediaInfo, timeout: float = 30.0) -> bytes | None:
    """썸네일 JPEG 바이트. ffmpeg로 한 장 만든다 (보통 1초 안팎)."""
    cmd = [str(ffmpeg_path()), "-v", "error", "-y"]
    if info.cover is not None:
        cmd += ["-i", str(info.path), "-map", f"0:{info.cover}"]
    elif info.video is not None:
        cmd += ["-ss", f"{info.duration * SCENE_AT:.3f}", "-i", str(info.path),
                "-map", f"0:{info.video.index}"]
    else:
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="castplayer-thumb-") as tmp:
            out = Path(tmp) / "thumb.jpg"
            r = subprocess.run(cmd + ["-frames:v", "1", "-vf", f"scale={THUMB_W}:-2",
                                      "-q:v", "4", str(out)],
                               capture_output=True, timeout=timeout,
                               creationflags=NO_WINDOW, check=False)
            if r.returncode != 0 or not out.is_file():
                _LOGGER.warning("썸네일 만들기 실패: %s",
                                r.stderr.decode("utf-8", "replace").strip()[-300:])
                return None
            data = out.read_bytes()
    except (OSError, subprocess.TimeoutExpired) as err:
        _LOGGER.warning("썸네일 만들기 실패: %s", err)
        return None
    _LOGGER.info("썸네일: %s", "표지" if info.cover is not None else f"{SCENE_AT:.0%} 지점")
    return data
