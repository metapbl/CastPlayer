"""작은 대화상자: IP 입력, 단축키, 지원 형식, 정보."""
from __future__ import annotations

import ipaddress
import platform
import subprocess
from importlib import metadata

import PySide6
from PySide6.QtWidgets import QInputDialog, QLineEdit, QMessageBox, QWidget

from core.encoders import EncoderProfile
from core.i18n import N_, tr
from core.paths import ffmpeg_path
from core.proc import NO_WINDOW

APP_NAME = "CastPlayer"
APP_VERSION = "1.2.0"

SHORTCUTS = (   # 설명은 보여 줄 때 tr() (D085)
    ("Space", N_("재생 / 일시정지")),
    ("← / →", N_("5초 뒤로 / 앞으로 (연타하면 모아서 한 번에 이동)")),
    ("↑ / ↓", N_("볼륨 ±5%")),
    ("M", N_("음소거 전환")),
    ("S", N_("정지 (TV 플레이어 종료)")),
    ("Ctrl+O", N_("파일 열기")),
    ("F5", N_("기기 다시 찾기")),
    ("Ctrl+Q", N_("프로그램 종료")),
    (N_("Shift+클릭"), N_("자막 싱크 버튼을 0.1초 단위로")),
)


def ask_ip(parent: QWidget) -> str | None:
    text = ""
    while True:
        text, ok = QInputDialog.getText(parent, tr("IP로 기기 추가"), tr("크롬캐스트 IP 주소:"),
                                     QLineEdit.EchoMode.Normal, text)
        if not ok:
            return None
        text = text.strip()
        try:
            return str(ipaddress.IPv4Address(text))
        except ValueError:
            QMessageBox.warning(parent, APP_NAME, tr("올바른 IP 주소가 아닙니다: {ip}", ip=text))


def confirm(parent: QWidget, text: str) -> bool:
    r = QMessageBox.question(parent, APP_NAME, text,
                             QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                             QMessageBox.StandardButton.Cancel)
    return r == QMessageBox.StandardButton.Ok


def show_shortcuts(parent: QWidget) -> None:
    rows = "".join(f"<tr><td><b>{tr(k)}</b></td><td>&nbsp;&nbsp;{tr(v)}</td></tr>"
                   for k, v in SHORTCUTS)
    QMessageBox.information(parent, tr("단축키 목록"), f"<table>{rows}</table>")


FORMATS = (   # 송출 방식 이름은 재생 카드와 같은 말 (D123). 보여 줄 때 tr() (D085)
    (N_("그대로 보냄"), N_("mp4 파일 (H.264·HEVC 영상, AAC·MP3 음성)"), N_("바로 재생, PC 부담 없음")),
    (N_("HLS 변환"), N_("mkv·ts·mov·avi 등 다른 파일, 또는 다른 음성 트랙을 고를 때"),
     N_("화질 그대로, PC 부담 적음")),
    (N_("HLS 재인코딩"), N_("TV가 읽지 못하는 영상 (XviD, 10비트 H.264 등)"),
     N_("PC 부담 큼, 화질이 조금 떨어질 수 있음")),
)


def show_formats(parent: QWidget) -> None:
    cell = "<td style='padding:4px 10px 4px 0'>"
    head = "".join(f"{cell}<b>{tr(h)}</b></td>" for h in (N_("송출 방식"), N_("이런 파일"), N_("특징")))
    rows = "".join(f"<tr>{cell}<b>{tr(m)}</b></td>{cell}{tr(f)}</td>{cell}{tr(n)}</td></tr>"
                   for m, f, n in FORMATS)
    QMessageBox.information(parent, tr("지원 형식"), (
        f"<table><tr>{head}</tr>{rows}</table><br>"
        + tr("<b>음성</b>: AAC는 대부분 그대로, Dolby·DTS 등 다른 음성은 AAC 스테레오로 바꿈") + "<br>"
        + tr("<b>자막</b>: srt·smi·ass/ssa·vtt 파일과 영상 안의 글자 자막. "
             "블루레이·DVD의 그림 자막(PGS, VobSub)은 안 됨")))


def _ffmpeg_version() -> str:
    try:
        r = subprocess.run([str(ffmpeg_path()), "-version"], capture_output=True,
                           timeout=5, creationflags=NO_WINDOW, check=False)
        return r.stdout.decode("utf-8", "replace").splitlines()[0]
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return tr("확인 실패")


def show_about(parent: QWidget, encoder: EncoderProfile | None) -> None:
    try:
        pcc = metadata.version("pychromecast")
    except metadata.PackageNotFoundError:
        pcc = "?"
    QMessageBox.about(parent, tr("{app} 정보", app=APP_NAME), (
        f"<b>{APP_NAME} {APP_VERSION}</b><br>{tr('로컬 동영상 → Chromecast 송출')}<br><br>"
        f"Python {platform.python_version()}<br>PySide6 {PySide6.__version__}<br>"
        f"pychromecast {pcc}<br>{_ffmpeg_version()}<br>"
        + tr("인코더: {name}", name=encoder.name if encoder else tr("감지 중 또는 없음"))))
