# 다크(Graphite)·라이트(Paper) 테마 — PySide6 6.8 이상 (QStyleHints.setColorScheme).
# Graphite/Paper 테마 1.4.3. Copyright (c) 2026 metapbl. MIT License.
# 창별 QSS 는 @이름 으로 적어 qss() 로 바꾼다.
# 설정 저장은 앱이 맡는다. 이 모듈은 mode 값만 받는다.

import re
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPalette
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QDialog,
    QPushButton,
)

_ICONS = Path(__file__).resolve().parent.parent / "assets" / "icons"
TOKENS: dict = {
    "dark": {
        "base": "#1c1c1c",
        "surface": "#272727",
        "raised": "#323232",
        "line": "#383838",
        "line2": "#4a4a4a",
        "btn": "#363636",
        "btn2": "#454545",
        "accent": "#4cc2ff",
        "accent2": "#7dd3ff",
        "on_accent": "#06222f",
        "text": "#f3f3f3",
        "text2": "#cfcfcf",
        "muted": "#9a9a9a",
        "faint": "#6e6e6e",
        "danger": "#e5636b",
        "success": "#3f9c6a",
        "success2": "#57b884",
        "warn": "#e0b050",
        "ext": "#7dd3ff",
        "track": "#3a3a3a",
        "sel": "#23465a",
        "on_strong": "#ffffff"
    },
    "light": {
        "base": "#f3f4f6",
        "surface": "#ffffff",
        "raised": "#eef0f2",
        "line": "#e1e4e8",
        "line2": "#c9ced4",
        "btn": "#eceef1",
        "btn2": "#dfe2e6",
        "accent": "#0f6cbd",
        "accent2": "#0c5697",
        "on_accent": "#ffffff",
        "text": "#1b1f24",
        "text2": "#3f4650",
        "muted": "#656d77",
        "faint": "#7f8892",
        "danger": "#c8323c",
        "success": "#1f8a4c",
        "success2": "#2aa35c",
        "warn": "#a86e00",
        "ext": "#0f6cbd",
        "track": "#e4e7eb",
        "sel": "#d3e6f7",
        "on_strong": "#ffffff"
    }
}

_current: dict = TOKENS["dark"]
_name: str | None = None  # 지금 칠해진 테마. 처음 적용 전에는 None
_mode = "system"
_listening = False


class _Notifier(QObject):
    changed = Signal()  # 테마가 실제로 바뀜 — 자기 QSS 를 가진 창이 다시 칠한다


notifier = _Notifier()


class _WidgetFixes(QObject):
    """앱 전체 이벤트 필터. Qt 기본 동작 중 Windows 관례와 다른 것을 고친다.

    - 항목을 채운 뒤 레이아웃에 넣은 목록·트리는 행 간격이 스타일의 높이를 반영하지 않아 행이 겹친다. 스타일을 입힐 때(Polish) 다시 배치한다.
    - 버튼류는 Qt 기본(StrongFocus)대로면 클릭만 해도 포커스 고리가 남는다. Windows 11 처럼 Tab 으로만 포커스를 받게 한다.
    - 대화상자 밖의 포커스 받은 QPushButton 은 Space 로만 눌린다. Enter 로도 누르게 한다.
      대화상자 안은 Qt 의 기본 버튼·autoDefault 규칙을 따르므로 건드리지 않는다.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Polish:
            if isinstance(watched, QAbstractItemView):
                watched.scheduleDelayedItemsLayout()
            # shortcut: 기본값과 앱이 직접 고른 StrongFocus 를 구별하지 못한다. 클릭 포커스가 필요한 버튼은 ClickFocus 로 지정하게 한다
            elif isinstance(watched, QAbstractButton) and watched.focusPolicy() == Qt.FocusPolicy.StrongFocus:
                watched.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        elif (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.KeypadModifier)
            and isinstance(watched, QPushButton)
            and watched.isEnabled()
            and not isinstance(watched.window(), QDialog)
        ):
            if not event.isAutoRepeat():
                watched.animateClick()
            return True
        return False


_widget_fixes = _WidgetFixes()


def qss(css: str) -> str:
    """QSS 의 @이름 을 현재 테마 색으로 바꾼다. 없는 이름은 KeyError. a@2x.png 같은 글자 뒤 @ 는 그대로 둔다."""
    return re.sub(r"(?<!\w)@(\w+)", lambda m: _current[m.group(1)], css)


def color(name: str) -> str:
    """현재 테마의 색 하나."""
    return _current[name]


def current() -> str | None:
    """지금 칠해진 테마 이름(dark/light). 처음 적용 전에는 None."""
    return _name


def resolve(mode: str, scheme: Qt.ColorScheme) -> str:
    """설정값과 시스템 색 모드로 쓸 테마를 정한다. 알 수 없으면 다크."""
    if mode in TOKENS:
        return mode
    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def icon_path(kind: str, name: str | None = None) -> Path:
    """테마별 아이콘(check, radio, up, down) 경로. SVG 는 색을 직접 가지므로 테마마다 파일이 다르다."""
    return _ICONS / f"{kind}_{name or _name or 'dark'}.svg"


# 역할 버튼: QPushButton 에 setProperty("role", "primary" | "danger"). 역할이 없거나 "secondary" 면 기본 모양.
# 켜진 기본 버튼은 바탕색 + 진한 윤곽, 꺼진 버튼만 회색으로 채운다 (Windows 11 관례). 채운 색은 역할 버튼에만.
_APP_QSS = """
QPushButton {
    background: @surface; color: @text; border: 1px solid @muted; border-radius: 6px; padding: 6px 14px;
    outline: none;  /* Fusion 포커스 네모를 지운다. 포커스는 2px 고리로 보인다 */
}
QPushButton:hover { background: @raised; }
QPushButton:pressed { background: @line; }
/* 포커스는 2px: 1px 색 바꿈만으로는 muted→accent 대비가 1.0~1.4 라 보이지 않는다. 안쪽 1px 은 바탕→고리색 대비로 3:1 을 넘긴다.
   두께가 늘어난 만큼 padding 을 줄여 크기를 지킨다 */
QPushButton:focus { border: 2px solid @accent; padding: 5px 13px; }
/* 토글 버튼(setCheckable) 켜짐: Windows 11 관례대로 강조색 채움 */
QPushButton:checked { background: @accent; color: @on_accent; border: 1px solid @accent; }
QPushButton:checked:hover { background: @accent2; border: 1px solid @accent2; }
QPushButton:checked:focus { border: 2px solid @on_accent; padding: 5px 13px; }
QPushButton[role="primary"] { background: @accent; color: @on_accent; border: 1px solid @accent; font-weight: bold; }
QPushButton[role="primary"]:hover { background: @accent2; border: 1px solid @accent2; }
QPushButton[role="primary"]:pressed { background: @accent; }
QPushButton[role="primary"]:focus { border: 2px solid @on_accent; padding: 5px 13px; }
/* 글자는 on_strong 이 아니라 on_accent: 다크에서 on_strong 은 danger 위 대비가 3.3 이다 */
QPushButton[role="danger"] { background: @danger; color: @on_accent; border: 1px solid @danger; font-weight: bold; }
QPushButton[role="danger"]:hover { border: 1px solid @text; }
QPushButton[role="danger"]:focus { border: 2px solid @on_accent; padding: 5px 13px; }
QPushButton:disabled, QPushButton[role="primary"]:disabled, QPushButton[role="danger"]:disabled {
    background: @raised; color: @faint; border: 1px solid @line;
}

QLineEdit, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QComboBox {
    background: @base; color: @text; border: 1px solid @line2; border-radius: 4px; padding: 4px 8px;
    selection-background-color: @accent; selection-color: @on_accent;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {
    border: 1px solid @accent;
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {
    background: @base; color: @faint; border: 1px solid @line2;
}

QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow { image: url("%down%"); width: 10px; height: 10px; }
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button { border: none; background: transparent; width: 18px; }
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background: @raised; }
QAbstractSpinBox::up-arrow { image: url("%up%"); width: 10px; height: 10px; }
QAbstractSpinBox::down-arrow { image: url("%down%"); width: 10px; height: 10px; }

QAbstractItemView {
    background: @base; alternate-background-color: @surface; color: @text;
    border: 1px solid @line2; border-radius: 6px; outline: 0; gridline-color: @line;
}
QAbstractItemView:focus { border: 1px solid @accent; }
QAbstractItemView::item { padding: 0 6px; height: 22px; }
QAbstractItemView::item:hover { background: @raised; }
QAbstractItemView::item:selected { background: @sel; color: @text; }
QAbstractItemView:disabled { color: @faint; }
QHeaderView { background: @raised; }
QHeaderView::section {
    background: @raised; color: @text2; border: none; border-right: 1px solid @line; border-bottom: 1px solid @line;
    padding: 6px;
}
QTableCornerButton::section { background: @raised; border: none; }

/* 글자는 숨긴다: 어떤 글자색도 line2 와 accent 양쪽에서 읽히지 않는다. 퍼센트는 옆 QLabel 로.
   홈은 track 이 아니라 line2: 라이트 track 은 흰 surface 위에서 보이지 않는다 */
QProgressBar { background: @line2; color: transparent; border: none; border-radius: 3px; max-height: 6px; }
QProgressBar::chunk { background: @accent; border-radius: 3px; }

QGroupBox { color: @text2; border: 1px solid @line2; border-radius: 6px; margin-top: 8px; padding: 12px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }

QSlider::groove:horizontal { background: @line2; height: 6px; border-radius: 3px; }
QSlider::groove:vertical { background: @line2; width: 6px; border-radius: 3px; }
QSlider::sub-page:horizontal, QSlider::add-page:vertical { background: @accent; border-radius: 3px; }
QSlider::handle:horizontal, QSlider::handle:vertical {
    background: @accent; width: 12px; height: 12px; border: 2px solid @surface; border-radius: 8px;
}
QSlider::handle:horizontal { margin: -5px 0; }
QSlider::handle:vertical { margin: 0 -5px; }
QSlider::handle:horizontal:hover, QSlider::handle:vertical:hover { background: @accent2; }
QSlider::handle:horizontal:focus, QSlider::handle:vertical:focus { border: 2px solid @text; }
QSlider::sub-page:horizontal:disabled, QSlider::add-page:vertical:disabled,
QSlider::handle:horizontal:disabled, QSlider::handle:vertical:disabled { background: @faint; }

QCheckBox, QRadioButton { spacing: 8px; }
QCheckBox:disabled, QRadioButton:disabled { color: @faint; }
QCheckBox::indicator, QAbstractItemView::indicator {
    width: 16px; height: 16px; border-radius: 4px; border: 1px solid @muted; background: @base;
}
QRadioButton::indicator { width: 16px; height: 16px; border-radius: 9px; border: 1px solid @muted; background: @base; }
QCheckBox::indicator:hover, QAbstractItemView::indicator:hover, QRadioButton::indicator:hover { border: 1px solid @accent; }
QCheckBox::indicator:focus, QRadioButton::indicator:focus { border: 2px solid @accent; }
QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {
    background: @accent; border: 1px solid @accent; image: url("%check%");
}
QCheckBox::indicator:checked:hover, QAbstractItemView::indicator:checked:hover {
    background: @accent2; border: 1px solid @accent2;
}
QRadioButton::indicator:checked { background: @accent; border: 1px solid @accent; image: url("%radio%"); }
QCheckBox::indicator:checked:focus, QRadioButton::indicator:checked:focus { border: 2px solid @on_accent; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { background: @surface; border: 1px solid @line2; }
QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {
    background: @faint; border: 1px solid @faint; image: none;
}

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle { background: @btn2; border-radius: 3px; }
QScrollBar::handle:vertical { min-height: 28px; }
QScrollBar::handle:horizontal { min-width: 28px; }
QScrollBar::handle:hover { background: @muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QAbstractScrollArea::corner { background: transparent; }

QToolTip { background: @raised; color: @text; border: 1px solid @line2; padding: 2px 4px; }
"""


def app_qss() -> str:
    """앱 전체에 거는 공통 위젯 스타일."""
    return qss(re.sub(r"%(\w+)%", lambda m: icon_path(m.group(1)).as_posix(), _APP_QSS))


def _paint(app: QApplication) -> None:
    palette = app.palette()
    role = QPalette.ColorRole
    for r, name in (
        (role.Window, "surface"),
        (role.Base, "base"),
        (role.AlternateBase, "surface"),
        (role.Text, "text"),
        (role.WindowText, "text"),
        (role.Button, "btn"),
        (role.ButtonText, "text"),
        (role.Highlight, "accent"),
        (role.HighlightedText, "on_accent"),
        (role.ToolTipBase, "raised"),
        (role.ToolTipText, "text"),
        (role.PlaceholderText, "muted"),
        (role.Link, "accent"),
    ):
        palette.setColor(r, QColor(_current[name]))
    for r in (role.Text, role.WindowText, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, r, QColor(_current["faint"]))
    app.setPalette(palette)
    app.setStyleSheet(app_qss())


def _sync() -> None:
    """설정과 시스템 색 모드에 맞춰 칠한다. 이미 그 테마면 아무것도 하지 않는다."""
    global _current, _name
    app = QApplication.instance()
    assert isinstance(app, QApplication), "apply_theme(app) 을 먼저 부른다"
    name = resolve(_mode, app.styleHints().colorScheme())
    if name == _name:
        return
    first = _name is None
    _name = name
    _current = TOKENS[name]
    _paint(app)
    if not first:
        notifier.changed.emit()


def apply_theme(app: QApplication, mode: str = "system") -> None:
    """테마를 적용한다. mode: system(시스템 따라가기) / dark / light."""
    global _mode, _listening
    _mode = mode
    hints = app.styleHints()
    if not _listening:
        app.installEventFilter(_widget_fixes)
        app.setStyle("Fusion")  # QSS 와 팔레트는 Fusion 기준으로 맞췄다. windows11 스타일에서는 어긋난다
        hints.colorSchemeChanged.connect(lambda _scheme: _sync())
        _listening = True
    # 제목 표시줄도 같은 색 모드를 쓰게 한다. Unknown 은 시스템 설정을 따른다.
    hints.setColorScheme(
        {"dark": Qt.ColorScheme.Dark, "light": Qt.ColorScheme.Light}.get(mode, Qt.ColorScheme.Unknown)
    )
    _sync()
