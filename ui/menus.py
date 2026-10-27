"""메뉴바: [메뉴] [옵션] [정보]. 동작 연결은 MainWindow가 한다."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMenu


@dataclass
class MenuActions:
    open_file: QAction
    rescan: QAction
    add_ip: QAction
    disconnect: QAction
    quit: QAction
    auto_connect: QAction
    debug_log: QAction
    open_logs: QAction
    clear_cache: QAction
    shortcuts: QAction
    formats: QAction
    about: QAction


def _add(win: QMainWindow, menu: QMenu, text: str, shortcut: str | None = None,
         checked: bool | None = None) -> QAction:
    act = QAction(text, win)
    if shortcut:
        act.setShortcut(QKeySequence(shortcut))
    if checked is not None:
        act.setCheckable(True)
        act.setChecked(checked)
    menu.addAction(act)
    return act


def build_menus(win: QMainWindow, auto_connect: bool, debug_log: bool) -> MenuActions:
    bar = win.menuBar()

    m = bar.addMenu("메뉴")
    open_file = _add(win, m, "파일 열기…", "Ctrl+O")
    m.addSeparator()
    rescan = _add(win, m, "기기 다시 찾기", "F5")
    add_ip = _add(win, m, "IP로 기기 추가…")
    disconnect = _add(win, m, "기기 연결 해제")
    m.addSeparator()
    quit_ = _add(win, m, "프로그램 종료", "Ctrl+Q")

    o = bar.addMenu("옵션")
    auto = _add(win, o, "시작 시 마지막 기기 자동 연결", checked=auto_connect)
    o.addSeparator()
    debug = _add(win, o, "디버그 로그", checked=debug_log)
    logs = _add(win, o, "로그 폴더 열기")
    o.addSeparator()
    cache = _add(win, o, "캐시 비우기…")

    i = bar.addMenu("정보")
    shortcuts = _add(win, i, "단축키 목록")
    formats = _add(win, i, "지원 형식")
    i.addSeparator()
    about = _add(win, i, "CastPlayer 정보")

    return MenuActions(open_file, rescan, add_ip, disconnect, quit_, auto, debug,
                       logs, cache, shortcuts, formats, about)
