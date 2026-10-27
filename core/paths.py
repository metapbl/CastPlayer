"""실행 위치 기준 경로 (개발 실행 / PyInstaller exe 공통)."""
import shutil
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):          # PyInstaller exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent  # 소스 실행: castplayer/


def bin_dir() -> Path:
    return app_dir() / "bin"


def _find_tool(name: str) -> Path:
    """프로그램 옆 bin/ → PATH 순서 (D042). 못 찾으면 bin/ 경로를 돌려주고 호출 쪽이 is_file()로 판정."""
    local = bin_dir() / f"{name}.exe"
    if local.is_file():
        return local
    found = shutil.which(name)
    return Path(found) if found else local


def ffmpeg_path() -> Path:
    return _find_tool("ffmpeg")


def ffprobe_path() -> Path:
    return _find_tool("ffprobe")


def config_path() -> Path:
    return app_dir() / "config.json"


# 키프레임 분석 캐시 등
def cache_dir() -> Path:
    return app_dir() / "cache"


def asset_path(name: str) -> Path:
    """함께 배포하는 파일(아이콘 등). exe에서는 _internal(sys._MEIPASS) 아래에 있다."""
    return Path(getattr(sys, "_MEIPASS", app_dir())) / "assets" / name
