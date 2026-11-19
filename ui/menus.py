"""메뉴바: [메뉴] [옵션] [정보]. 동작 연결은 MainWindow가 한다."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu

from core.i18n import N_, tr


@dataclass
class MenuActions:
    open_file: QAction
    rescan: QAction
    add_ip: QAction
    disconnect: QAction
    quit: QAction
    auto_connect: QAction
    themes: dict[str, QAction]     # system / dark / light
    log_file: QAction
    open_logs: QAction
    clear_cache: QAction
    shortcuts: QAction
    formats: QAction
    about: QAction
    texts: list[tuple[QAction, str]]   # (항목, 번역 키): retranslate_menus가 글자를 넣음


_TEXTS: list[tuple[QAction, str]] = []   # build_menus 한 번 동안 모음


def _add(win: QMainWindow, menu: QMenu, text: str, shortcut: str | None = None,
         checked: bool | None = None) -> QAction:
    act = QAction(win)
    _TEXTS.append((act, text))
    if shortcut:
        act.setShortcut(QKeySequence(shortcut))
    if checked is not None:
        act.setCheckable(True)
        act.setChecked(checked)
    menu.addAction(act)
    return act


def _menu(parent, key: str) -> QMenu:
    menu = parent.addMenu("")
    _TEXTS.append((menu.menuAction(), key))
    return menu


def build_menus(win: QMainWindow, auto_connect: bool, log_file: bool,
                theme: str) -> MenuActions:
    bar = win.menuBar()
    _TEXTS.clear()

    m = _menu(bar, N_("메뉴"))
    open_file = _add(win, m, N_("파일 열기…"), "Ctrl+O")
    m.addSeparator()
    rescan = _add(win, m, N_("기기 다시 찾기"), "F5")
    add_ip = _add(win, m, N_("IP로 기기 추가…"))
    disconnect = _add(win, m, N_("기기 연결 해제"))
    m.addSeparator()
    quit_ = _add(win, m, N_("프로그램 종료"), "Ctrl+Q")

    o = _menu(bar, N_("옵션"))
    auto = _add(win, o, N_("시작 시 마지막 기기 자동 연결"), checked=auto_connect)
    t = _menu(o, N_("테마"))
    group = QActionGroup(win)
    themes = {}
    for key, text in (("system", N_("시스템 설정 따르기")), ("dark", N_("어둡게")),
                      ("light", N_("밝게"))):
        themes[key] = group.addAction(_add(win, t, text, checked=key == theme))
    o.addSeparator()
    log = _add(win, o, N_("로그 기록"), checked=log_file)
    logs = _add(win, o, N_("로그 폴더 열기"))
    o.addSeparator()
    cache = _add(win, o, N_("캐시 비우기…"))

    i = _menu(bar, N_("정보"))
    shortcuts = _add(win, i, N_("단축키 목록"))
    formats = _add(win, i, N_("지원 형식"))
    i.addSeparator()
    about = _add(win, i, N_("CastPlayer 정보"))

    acts = MenuActions(open_file, rescan, add_ip, disconnect, quit_, auto, themes, log,
                       logs, cache, shortcuts, formats, about, list(_TEXTS))
    retranslate_menus(acts)
    return acts


def retranslate_menus(acts: MenuActions) -> None:
    for act, key in acts.texts:
        act.setText(tr(key))
