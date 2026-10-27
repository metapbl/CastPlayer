"""CastPlayer GUI 실행 진입점.

    python main.py        (castplayer 폴더에서)
    python main.py -v     이번 실행만 DEBUG 로그 (config.json의 debug_log는 바꾸지 않음)

로그: logs/castplayer.txt (1MB씩, 지난 것은 castplayer.1~3.txt). 소스로 실행하면 콘솔에도 출력.
"""
from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from core.cast_manager import CastManager
from core.config import AppConfig
from core.encoders import EncoderDetector
from core.media_server import MediaServer
from core.paths import app_dir, asset_path, bin_dir, ffmpeg_path, ffprobe_path
from core.player import PlaybackController
from ui.bridge import CastBridge
from ui.dialogs import APP_NAME
from ui.main_window import MainWindow

_LOGGER = logging.getLogger("castplayer")
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_NAME = "castplayer.txt"   # 붙여넣기 편하도록 .txt


def _rotated_name(default: str) -> str:
    """'castplayer.txt.1' → 'castplayer.1.txt' (Windows에서 바로 열리도록)."""
    base, _, num = default.rpartition(".")
    if base.endswith(".txt") and num.isdigit():
        return f"{base[:-4]}.{num}.txt"
    return default


def set_debug(on: bool) -> None:
    """실행 중에도 바로 적용 (_StoppedNoiseFilter도 기록 시점의 수준을 봄)."""
    logging.getLogger().setLevel(logging.DEBUG if on else logging.INFO)


def setup_logging(debug: bool) -> None:
    root = logging.getLogger()
    fmt = logging.Formatter(LOG_FORMAT)
    try:
        log_dir = app_dir() / "logs"
        log_dir.mkdir(exist_ok=True)
        fh = RotatingFileHandler(log_dir / LOG_NAME, maxBytes=1_000_000,
                                 backupCount=3, encoding="utf-8")
        fh.namer = _rotated_name
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    if not getattr(sys, "frozen", False) and sys.stderr:   # exe(--windowed)는 콘솔 없음
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    set_debug(debug)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true", help="이번 실행만 DEBUG 로그")
    args = ap.parse_args()

    cfg = AppConfig.load()
    debug = args.verbose or cfg.debug_log
    setup_logging(debug)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(asset_path("cast.ico"))))   # 창·작업표시줄 (exe 파일 아이콘은 spec)

    missing = [p.name for p in (ffmpeg_path(), ffprobe_path()) if not p.is_file()]
    if missing:
        box = QMessageBox(QMessageBox.Icon.Critical, APP_NAME,
                          f"{', '.join(missing)}을(를) 찾지 못했습니다.\n\n"
                          f"찾아본 곳:\n- {bin_dir()}\n- PATH 환경 변수\n\n"
                          "PowerShell이나 명령 프롬프트에서 설치할 수 있습니다:\n"
                          "winget install Gyan.FFmpeg\n\n"
                          "설치한 뒤 CastPlayer를 다시 실행해 주세요.")
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)  # 명령 복사용
        box.exec()
        return 2

    detector = EncoderDetector(ffmpeg_path())
    detector.start()
    server = MediaServer(port=cfg.server_port)
    try:
        server.start()
    except RuntimeError as err:
        QMessageBox.critical(None, APP_NAME,
                             f"{err}\n\nCastPlayer가 이미 실행 중이거나 다른 프로그램이 "
                             f"포트 {cfg.server_port}를 쓰고 있습니다.\n"
                             "config.json의 server_port로 포트를 바꿀 수 있습니다.")
        return 2

    bridge = CastBridge()
    cm = CastManager(bridge.callbacks, known_hosts=cfg.known_hosts)
    ctrl = PlaybackController(cm, server, detector, bridge.callbacks,
                              subtitle_scale=cfg.subtitle_scale)
    win = MainWindow(cfg, cm, ctrl, bridge, set_debug=set_debug, debug_on=debug)
    win.show()
    try:
        return app.exec()
    finally:
        _LOGGER.info("종료 처리 중... (정지 → 수신 앱 종료 → ffmpeg 정리 → 연결 해제)")
        cm.shutdown()
        ctrl.shutdown()
        server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
