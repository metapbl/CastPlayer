"""작은 대화상자: IP 입력, 도움말(단축키·지원 형식), 정보."""
from __future__ import annotations

import ipaddress
import platform
import subprocess
from importlib import metadata

import PySide6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from core.encoders import EncoderProfile
from core.i18n import N_, tr
from core.paths import ffmpeg_path
from core.proc import NO_WINDOW
from ui import theme

APP_NAME = "CastPlayer"
APP_VERSION = "1.3.0"

SHORTCUTS = (   # 설명은 보여 줄 때 tr() (D085)
    ("Space", N_("재생 / 일시정지")),
    ("← / →", N_("5초 뒤로 / 앞으로")),
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


MODES = (   # 이름은 재생 카드와 같은 말. 설명은 두 줄. 보여 줄 때 tr() (D085, D126)
    (N_("그대로 보냄"), (N_("mp4"), N_("H.264·HEVC 영상 + AAC·MP3 음성")), ()),
    (N_("HLS 변환"), (N_("mkv·avi·mov·ts 등"), N_("mp4에서 다른 음성 트랙을 고를 때")), ()),
    (N_("HLS 재인코딩"), (N_("10비트 H.264"), N_("XviD 등 TV가 못 읽는 영상")),
     ((N_("PC 자원 사용"), "chip"), (N_("화질 조금 낮아짐"), "warnchip"))),
)
SUB_EXTS = ("srt", "smi", "ass", "ssa", "vtt")
HELP_QSS = """
QDialog { background: @base; }
QFrame#card { background: @surface; border: 1px solid @line2; border-radius: 10px; }
QFrame#sep { background: @line; border: none; }
QLabel#h { font-size: 15px; font-weight: bold; color: @text; }
QLabel#key { background: @raised; border: 1px solid @line2; border-bottom-width: 2px;
             border-radius: 4px; padding: 1px 7px; color: @text; font-weight: 600; }
QLabel#chip { background: @raised; border: 1px solid @line2; border-radius: 9px; padding: 1px 8px; color: @text; }
QLabel#nochip { border: 1px solid @danger; border-radius: 9px; padding: 1px 8px; color: @danger; }
QLabel#warnchip { border: 1px solid @warn; border-radius: 9px; padding: 1px 8px; color: @warn; }
QLabel#name { font-weight: bold; color: @text; }
QLabel#text { color: @text2; }
QLabel#muted { color: @muted; }
"""


def _label(text: str, name: str, fixed: bool = False) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName(name)
    if fixed:
        lb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return lb


def _row(*items: QWidget, spacing: int = 6) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(spacing)
    for it in items:
        h.addWidget(it)
    h.addStretch(1)
    return h


def _keys(text: str) -> QHBoxLayout:
    """키 글자("Ctrl+O", "← / →")를 키 모양 칩으로."""
    parts: list[QWidget] = []
    for gi, group in enumerate(text.split(" / ")):
        if gi:
            parts.append(_label("/", "muted"))
        for ki, k in enumerate(group.split("+")):
            if ki:
                parts.append(_label("+", "muted"))
            parts.append(_label(k, "key", fixed=True))
    return _row(*parts, spacing=4)


def _card(outer: QVBoxLayout, title: str, note: str = "") -> QVBoxLayout:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 14, 18, 16)
    lay.setSpacing(10)
    head = _row(_label(title, "h"), spacing=10)
    if note:                                     # 제목 오른쪽 회색 한마디
        head.insertWidget(1, _label(note, "muted"), 0, Qt.AlignmentFlag.AlignBottom)
    lay.addLayout(head)
    outer.addWidget(f)
    return lay


def _sep() -> QFrame:
    f = QFrame()
    f.setObjectName("sep")
    f.setFixedHeight(1)
    return f


def build_help(parent: QWidget | None, video_exts: tuple[str, ...]) -> QDialog:
    """단축키와 지원 형식을 한 창에 (D126). 글자는 열 때 tr(), 색은 열 때 테마."""
    d = QDialog(parent)
    d.setWindowTitle(tr("도움말"))
    d.setStyleSheet(theme.qss(HELP_QSS))
    v = QVBoxLayout(d)
    v.setContentsMargins(16, 16, 16, 16)
    v.setSpacing(12)

    sc = _card(v, tr("단축키"))
    g = QGridLayout()
    g.setHorizontalSpacing(16)
    g.setVerticalSpacing(8)
    half = (len(SHORTCUTS) + 1) // 2
    for i, (key, desc) in enumerate(SHORTCUTS):
        r, c = (i, 0) if i < half else (i - half, 2)
        g.addLayout(_keys(tr(key)), r, c)
        g.addWidget(_label(tr(desc), "text"), r, c + 1)
    g.setColumnStretch(1, 1)
    g.setColumnStretch(3, 1)
    sc.addLayout(g)

    fc = _card(v, tr("지원 형식"))
    g = QGridLayout()
    g.setHorizontalSpacing(14)
    g.setVerticalSpacing(10)
    top = Qt.AlignmentFlag.AlignTop
    per_row = 6
    ext_chips: list[QLabel] = []     # 확장자 칩은 끝에 같은 폭으로 (D126)

    def ext(text: str, name: str = "chip") -> QLabel:
        lb = _label(text, name, fixed=True)
        lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ext_chips.append(lb)
        return lb

    vids = QVBoxLayout()
    vids.setSpacing(6)
    for i in range(0, len(video_exts), per_row):
        vids.addLayout(_row(*(ext(e.lstrip(".")) for e in video_exts[i:i + per_row])))
    subs = QVBoxLayout()
    subs.setSpacing(6)
    subs.addLayout(_row(*(ext(e) for e in SUB_EXTS), _label(tr("내장 텍스트 자막"), "chip", fixed=True)))
    subs.addLayout(_row(ext("✕ PGS", "nochip"), ext("✕ VobSub", "nochip"), _label(tr("그림 자막은 안 됨"), "muted")))
    audio = QVBoxLayout()
    audio.setSpacing(6)
    audio.addLayout(_row(ext("AAC"), _label(tr("그대로"), "muted")))
    audio.addLayout(_row(*(ext(c) for c in ("Dolby", "DTS", "FLAC", "Opus")),
                         _label(tr("등은 스테레오로 바꿈"), "muted")))
    g.addWidget(_label(tr("영상"), "muted"), 0, 0, top)
    g.addLayout(vids, 0, 1)
    g.addWidget(_label(tr("자막"), "muted"), 1, 0, top)
    g.addLayout(subs, 1, 1)
    g.addWidget(_label(tr("음성"), "muted"), 2, 0, top)
    g.addLayout(audio, 2, 1)
    g.setColumnStretch(1, 1)
    fc.addLayout(g)
    mc = _card(v, tr("송출 방식"), tr("파일을 열면 자동으로 고름"))
    g = QGridLayout()
    g.setHorizontalSpacing(14)
    g.setVerticalSpacing(12)
    for r, (name, lines, chips) in enumerate(MODES):
        g.addWidget(_label(tr(name), "name"), r, 0, top)
        body = QVBoxLayout()
        body.setSpacing(2)
        for line in lines:
            body.addWidget(_label(tr(line), "text"))
        if chips:
            body.addLayout(_row(*(_label(tr(t), n, fixed=True) for t, n in chips)))
        g.addLayout(body, r, 1)
    g.setColumnStretch(1, 1)
    mc.addLayout(g)

    close = QPushButton(tr("닫기"))
    close.setMinimumWidth(88)
    close.setDefault(True)
    close.clicked.connect(d.accept)
    bh = QHBoxLayout()
    bh.addStretch(1)
    bh.addWidget(close)
    v.addLayout(bh)
    for lb in ext_chips:
        lb.ensurePolished()           # 창의 스타일(여백)을 입힌 뒤 폭을 잼
    width = max(lb.sizeHint().width() for lb in ext_chips)
    for lb in ext_chips:
        lb.setFixedWidth(width)
    return d


def show_help(parent: QWidget, video_exts: tuple[str, ...]) -> None:
    build_help(parent, video_exts).exec()


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
