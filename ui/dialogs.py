"""작은 대화상자: IP 입력, 단축키, 지원 형식, 정보."""
from __future__ import annotations

import ipaddress
import platform
import subprocess
from importlib import metadata

import PySide6
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from core.encoders import EncoderProfile
from core.paths import ffmpeg_path
from core.proc import NO_WINDOW

APP_NAME = "CastPlayer"
APP_VERSION = "1.0.0"

SHORTCUTS = (
    ("Space", "재생 / 일시정지"),
    ("← / →", "5초 뒤로 / 앞으로 (연타하면 모아서 한 번에 이동)"),
    ("↑ / ↓", "볼륨 ±5%"),
    ("M", "음소거 전환"),
    ("S", "정지 (TV 플레이어 종료)"),
    ("Ctrl+O", "파일 열기"),
    ("F5", "기기 다시 찾기"),
    ("Ctrl+Q", "프로그램 종료"),
    ("Shift+클릭", "자막 싱크 버튼을 0.1초 단위로"),
)


def ask_ip(parent: QWidget) -> str | None:
    text = ""
    while True:
        text, ok = QInputDialog.getText(parent, "IP로 기기 추가", "크롬캐스트 IP 주소:",
                                     QLineEdit.EchoMode.Normal, text)
        if not ok:
            return None
        text = text.strip()
        try:
            return str(ipaddress.IPv4Address(text))
        except ValueError:
            QMessageBox.warning(parent, APP_NAME, f"올바른 IP 주소가 아닙니다: {text}")


def confirm(parent: QWidget, text: str) -> bool:
    r = QMessageBox.question(parent, APP_NAME, text,
                             QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                             QMessageBox.StandardButton.Cancel)
    return r == QMessageBox.StandardButton.Ok


def show_shortcuts(parent: QWidget) -> None:
    rows = "".join(f"<tr><td><b>{k}</b></td><td>&nbsp;&nbsp;{v}</td></tr>" for k, v in SHORTCUTS)
    QMessageBox.information(parent, "단축키 목록", f"<table>{rows}</table>")


def show_formats(parent: QWidget) -> None:
    QMessageBox.information(parent, "지원 형식", (
        "<b>DIRECT</b>: mp4 + H.264/HEVC(hvc1) + AAC/MP3, 기본 음성 트랙 → 파일 그대로<br>"
        "<b>REMUX</b>: 영상은 지원되지만 컨테이너(mkv, ts, mov 등)·HEVC 태그·음성 코덱이 "
        "맞지 않거나 기본 외 음성 선택 → HLS, 영상 복사<br>"
        "<b>TRANSCODE</b>: 영상 미지원(XviD, H.264 10bit 등)이나 표시 시각 결함 → "
        "HLS, H.264 재인코딩<br><br>"
        "음성: AAC는 복사, 나머지는 AAC 2ch로 변환<br>"
        "자막: srt, smi(클래스별), ass/ssa, vtt, 내장 텍스트 자막 → WebVTT<br>"
        "이미지 자막(PGS, VobSub)은 지원 안 함"))


def _ffmpeg_version() -> str:
    try:
        r = subprocess.run([str(ffmpeg_path()), "-version"], capture_output=True,
                           timeout=5, creationflags=NO_WINDOW, check=False)
        return r.stdout.decode("utf-8", "replace").splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return "확인 실패"


def show_about(parent: QWidget, encoder: EncoderProfile | None) -> None:
    try:
        pcc = metadata.version("pychromecast")
    except metadata.PackageNotFoundError:
        pcc = "?"
    QMessageBox.about(parent, f"{APP_NAME} 정보", (
        f"<b>{APP_NAME} {APP_VERSION}</b><br>로컬 동영상 → Chromecast 송출<br><br>"
        f"Python {platform.python_version()}<br>PySide6 {PySide6.__version__}<br>"
        f"pychromecast {pcc}<br>{_ffmpeg_version()}<br>"
        f"인코더: {encoder.name if encoder else '감지 중 또는 없음'}"))
