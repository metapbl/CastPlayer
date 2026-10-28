"""CastPlayer GUI 실행 진입점.

    python main.py        (castplayer 폴더에서)
    python main.py -v     이번 실행만 DEBUG 로그를 파일에 기록 (옵션 "로그 기록"과 무관)

로그 (D070): 기본 꺼짐. 옵션 "로그 기록"을 켜면 logs/castplayer.log.
실행할 때마다 지난 castplayer*.log를 지우고 새로 씀 (한 실행 안에서는 1MB씩, castplayer.1~3.log).
소스로 실행하면 콘솔에도 출력.
"""
from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

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
LOG_NAME = "castplayer.log"


def _rotated_name(default: str) -> str:
    """'castplayer.log.1' → 'castplayer.1.log' (Windows에서 바로 열리도록)."""
    base, _, num = default.rpartition(".")
    if base.endswith(".log") and num.isdigit():
        return f"{base[:-4]}.{num}.log"
    return default


class FileLog:
    """GUI 로그 파일 켜기·끄기 (D070). 지난 castplayer*.log는 이 실행에서 처음 열 때만 지운다
    (한 실행 안에서 껐다 켜면 이어 씀)."""

    def __init__(self, log_dir: Path) -> None:
        self.dir = log_dir
        self._handler: RotatingFileHandler | None = None
        self._cleared = False

    def set(self, on: bool) -> str | None:
        """파일을 못 열면 알림 문구를 돌려준다."""
        root = logging.getLogger()
        if not on:
            if self._handler:
                root.removeHandler(self._handler)
                self._handler.close()
                self._handler = None
            return None
        if self._handler:
            return None
        path = self.dir / LOG_NAME
        try:
            self.dir.mkdir(exist_ok=True)
            if not self._cleared:
                for old in self.dir.glob("castplayer*.log"):
                    old.unlink()
            fh = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        except OSError as err:
            return f"로그 파일을 만들 수 없습니다: {path} ({err.strerror or err})"
        self._cleared = True
        fh.namer = _rotated_name
        fh.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(fh)
        self._handler = fh
        return None


def setup_logging(verbose: bool, log_on: bool, log_dir: Path,
                  console: bool = True) -> tuple[FileLog, str | None]:
    """verbose(-v): 옵션과 무관하게 이번 실행만 파일 기록 + DEBUG. 반환: (파일 로그, 알림 문구)."""
    root = logging.getLogger()
    file_log = FileLog(log_dir)
    err = file_log.set(verbose or log_on)
    # exe(--windowed)는 콘솔 없음
    if console and not getattr(sys, "frozen", False) and sys.stderr:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(LOG_FORMAT))
        root.addHandler(sh)
    # _StoppedNoiseFilter는 기록 시점의 수준을 본다
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    return file_log, err


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="이번 실행만 DEBUG 로그를 파일에 기록")
    args = ap.parse_args()

    cfg = AppConfig.load()
    file_log, log_error = setup_logging(args.verbose, cfg.log_file, app_dir() / "logs")
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
    win = MainWindow(cfg, cm, ctrl, bridge, set_log=file_log.set, log_error=log_error)
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
