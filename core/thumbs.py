"""썸네일 (F9-12, D097, D101, D102, D119): 표지가 있으면 표지, 없으면 영상 길이 10% 지점 한 장면.
장면은 위아래 검은 띠를 잘라 냄. 가로 최대 1920px(원본이 작으면 원본) JPEG 바이트. 임시 폴더에 만들어 읽은 뒤 바로 지워 캐시에 남기지 않는다.
실패하면 None (화면은 글자만)."""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from .paths import ffmpeg_path
from .probe import MediaInfo
from .proc import NO_WINDOW

_LOGGER = logging.getLogger(__name__)
THUMB_W = 1920   # 큰 모니터에서도 선명하게 (D119)
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
    crop = _bars(cmd, info, timeout) if info.cover is None else ""
    try:
        with tempfile.TemporaryDirectory(prefix="castplayer-thumb-") as tmp:
            out = Path(tmp) / "thumb.jpg"
            r = subprocess.run(cmd + ["-frames:v", "1", "-vf", f"{crop}scale='min({THUMB_W},iw)':-2",
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
    _LOGGER.info("썸네일: %s%s", "표지" if info.cover is not None else f"{SCENE_AT:.0%} 지점",
                 " (검은 띠 자름)" if crop else "")
    return data


def _bars(cmd: list[str], info: MediaInfo, timeout: float) -> str:
    """위아래 검은 띠를 자르는 필터 앞부분("crop=…,"), 없으면 "" (D119).
    가로 전체 너비이고 남는 높이가 절반 이상일 때만 — 어두운 장면을 지나치게 자르지 않음."""
    v = info.video
    if v is None or not v.width or not v.height:
        return ""
    try:
        r = subprocess.run(cmd[:1] + ["-v", "info"] + cmd[3:] + [
            "-frames:v", "5", "-vf", "cropdetect=limit=24:round=2:reset=0", "-f", "null", "-"],
            capture_output=True, timeout=timeout, creationflags=NO_WINDOW, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr.decode("utf-8", "replace"))
    if not found:
        return ""
    w, h, x, y = map(int, found[-1])
    if x > 8 or w < v.width - 16 or not v.height // 2 <= h < v.height:
        return ""
    return f"crop=iw:{h}:0:{y},"
