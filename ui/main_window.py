"""메인 창.

스레드 규칙: 이 파일의 슬롯은 모두 UI 스레드에서 돈다.
바로 끝나는 호출(cm.pause, ctrl.seek 등)만 여기서 하고, load·set_audio는 TaskRunner로 보낸다.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Callable
from uuid import UUID

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QMainWindow, QMessageBox, QProgressBar,
                               QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from core.cast_manager import CastManager, DeviceInfo, PlaybackState
from core.config import AppConfig
from core.paths import app_dir, cache_dir
from core.planner import Mode, Plan, PlanError
from core.player import PlaybackController
from core.playlist import Playlist, PlaylistItem
from core.probe import MediaInfo
from ui import theme
from ui.bridge import CastBridge
from ui.dialogs import (APP_NAME, ask_ip, confirm, show_about, show_formats,
                        show_shortcuts)
from ui.menus import build_menus
from ui.tasks import TaskRunner, stop_and_wait
from ui.widgets import SeekSlider, fmt_time

_LOGGER = logging.getLogger(__name__)
VIDEO_EXTS = {".mp4", ".m4v", ".mkv", ".avi", ".ts", ".m2ts", ".mov", ".webm", ".wmv",
              ".mpg", ".mpeg", ".flv"}
AUTO_HOST_FALLBACK_MS = 8000     # mDNS로 마지막 기기를 못 찾으면 저장된 IP로 검색
RECONNECT_WINDOW = 30.0          # 끊긴 뒤 같은 UUID를 다시 찾는 시간(초)
SEEK_STEP, SEEK_COALESCE_MS = 5.0, 300
SEEK_BACK, SEEK_FWD = -10.0, 30.0   # 화면 버튼 (D076), 키 ←/→는 SEEK_STEP
VOL_STEP = 5

# 연결 상태: (표시 문구, 테마 색 이름)
ST_NONE, ST_BUSY, ST_OK, ST_LOST = ("미연결", "muted"), ("연결 중", "warn"), \
    ("연결됨", "success"), ("끊김", "danger")

H = 32                                                     # 버튼·입력 높이 (D076)
ICON_FONTS = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]   # Windows 11, 없으면 10
GLYPH = {"play": "", "pause": "", "stop": "", "vol": "",
         "mute": "", "refresh": "", "back": "", "fwd": "",
         "minus": "", "plus": "", "drop": ""}
QSS = """
QWidget#root { background: @base; }
QFrame#card { background: @surface; border: 1px solid @line2; border-radius: 10px; }
QFrame#drop { border: 1px dashed @faint; border-radius: 8px; }
QLabel#title { font-size: 15px; font-weight: bold; color: @text; }
QLabel#sub, QLabel#field, QLabel#drop_icon { color: @muted; }
QPushButton[icon_btn="true"] { padding: 0; }
QPushButton#big { border-radius: 20px; }
/* 밝게에서 회색 요소가 흰 카드에 묻히지 않게: 윤곽선·빈 막대를 한 단계 진하게, 꺼진 것도 같은 윤곽 */
QPushButton, QPushButton:disabled, QPushButton[role="primary"]:disabled { border: 1px solid @line2; }
QPushButton[role="primary"] { border: 1px solid @accent; }
/* 꺼진 버튼은 바탕 없이 윤곽선과 흐린 글자만 → 켜진(채워진) 버튼과 한눈에 구분 */
QPushButton:disabled, QPushButton[role="primary"]:disabled { background: transparent; color: @faint; }
QComboBox:disabled { background: @base; border: 1px solid @line2; }
QSlider::groove:horizontal { background: @line2; }
"""
# 밝게 전용: 기본 버튼 바탕(btn)이 흰 카드와 거의 같아, 화면 내용에 따라 밝기를 바꾸는
# 디스플레이(콘텐츠 적응 밝기 등)에서는 흰색으로 보임 → 테두리 색(line2)까지 진하게.
# 창 스타일시트는 앱 것보다 우선하므로 역할 버튼도 다시 적는다
QSS_LIGHT = """
QPushButton { background: @line2; }
QPushButton:hover { background: @btn2; }
QPushButton:pressed { background: @btn; }
QPushButton[role="primary"] { background: @accent; }
QPushButton[role="primary"]:hover { background: @accent2; }
"""


def _plan_text(plan: Plan, info: MediaInfo) -> str:
    """송출 방식을 읽기 쉬운 한 줄로. 자세한 이유는 풍선 도움말(plan.summary)."""
    ext = info.path.suffix.lstrip(".").upper() or "파일"
    how = {Mode.DIRECT: f"{ext} 그대로 보냄", Mode.REMUX: f"{ext} → HLS 변환",
           Mode.TRANSCODE: f"{ext} → HLS 재인코딩"}[plan.mode]
    video = "영상 그대로" if plan.video_copy else "영상 재인코딩"
    if plan.fps_cap:
        video += f" {float(plan.fps_cap):.0f}fps"
    audio = ("음성 없음" if plan.audio is None
             else "음성 그대로" if plan.audio_copy else "음성 AAC 2ch로 변환")
    return " · ".join((how, video, audio))


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig, cm: CastManager, ctrl: PlaybackController,
                 bridge: CastBridge, set_log: Callable[[bool], str | None],
                 log_error: str | None) -> None:
        super().__init__()
        self.cfg, self.cm, self.ctrl, self.bridge = cfg, cm, ctrl, bridge
        self._set_log = set_log
        self.tasks = TaskRunner(self)
        self.playlist = Playlist()
        self._conn = ST_NONE
        self._state = "IDLE"               # 수신기 플레이어 상태
        self._last_pos = 0.0
        self._expect_disconnect = False    # 우리가 끊는 중 (자동 재연결 안 함)
        self._auto_tried = False
        self._reconnect_until = 0.0
        self._reconnect_uuid: UUID | None = None
        self._seek_acc = 0.0
        self._vol_updating = False
        self._conn_extra = ""
        self._err = False                  # 상태줄 글이 오류 → 경고색
        self._title = ""                   # 연 파일 이름 (줄이기 전)

        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.resize(680, 0)
        self._build_ui()
        self.acts = build_menus(self, cfg.auto_connect, cfg.log_file, cfg.theme)
        self._wire()
        if cfg.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(cfg.window_geometry.encode()))

        self._poll = QTimer(self, interval=500)
        self._poll.timeout.connect(self._on_poll)
        self._poll.start()
        self._seek_timer = QTimer(self, singleShot=True, interval=SEEK_COALESCE_MS)
        self._seek_timer.timeout.connect(self._flush_seek)
        self._set_conn(ST_NONE)            # 연결 표시를 처음부터 보임 (F1-3)
        if log_error:
            self._msg(log_error, error=True)
        cm.start_discovery()
        if cfg.auto_connect and cfg.last_device_uuid and cfg.last_device_host:
            QTimer.singleShot(AUTO_HOST_FALLBACK_MS, self._auto_host_fallback)

    # ================= 화면 =================
    def _build_ui(self) -> None:
        """A안 (D076): 기기 / 미디어 / 트랙 카드. 높이 H, 오른쪽 끝 한 선."""
        def btn(text: str, tip: str = "", width: int = 96, role: str = "") -> QPushButton:
            b = QPushButton(text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setFixedSize(width, H)
            if tip:
                b.setToolTip(tip)
            if role:
                b.setProperty("role", role)
            return b

        def icon(glyph: str, tip: str, size: int = H, role: str = "") -> QPushButton:
            b = btn(GLYPH[glyph], tip, size, role)
            b.setFixedSize(size, size)
            b.setProperty("icon_btn", True)
            f = QFont()
            f.setFamilies(ICON_FONTS)
            f.setPixelSize(16 if size > H else 14)
            b.setFont(f)
            return b

        def label(text: str = "", name: str = "", width: int = 0,
                  align: Qt.AlignmentFlag | None = None) -> QLabel:
            lb = QLabel(text)
            if name:
                lb.setObjectName(name)
            if width:
                lb.setFixedWidth(width)
            if align is not None:
                lb.setAlignment(align)
            return lb

        def combo() -> QComboBox:
            c = QComboBox()
            c.setFixedHeight(H)
            c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            c.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            return c

        def card(parent: QVBoxLayout) -> QVBoxLayout:
            f = QFrame()
            f.setObjectName("card")
            v = QVBoxLayout(f)
            v.setContentsMargins(16, 14, 16, 14)
            v.setSpacing(10)
            parent.addWidget(f)
            return v

        def hbox(*ws, spacing: int = 8) -> QHBoxLayout:
            h = QHBoxLayout()
            h.setSpacing(spacing)
            for w in ws:
                if w is None:
                    h.addStretch(1)
                elif isinstance(w, tuple):
                    h.addWidget(*w)
                else:
                    h.addWidget(w)
            return h

        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        center = Qt.AlignmentFlag.AlignCenter
        root = QVBoxLayout()
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # 기기
        self.conn_label = label()
        self.dev_combo = combo()
        self.dev_combo.setMinimumWidth(160)
        self.btn_rescan = icon("refresh", "기기 다시 찾기 (F5)")
        self.btn_connect = btn("연결")
        card(root).addLayout(hbox(self.conn_label, (self.dev_combo, 1), self.btn_rescan,
                                  self.btn_connect))

        # 미디어: 파일이 없으면 끌어다 놓기 영역, 있으면 이름·방식
        mv = card(root)
        self.drop = QFrame()
        self.drop.setObjectName("drop")
        dv = QVBoxLayout(self.drop)
        dv.setContentsMargins(16, 18, 16, 18)
        dv.setSpacing(8)
        drop_icon = label(GLYPH["drop"], "drop_icon", align=center)
        f = QFont()
        f.setFamilies(ICON_FONTS)
        f.setPixelSize(28)
        drop_icon.setFont(f)
        self.drop_hint = label("", "sub", align=center)
        self.btn_open_big = btn("파일 열기", "Ctrl+O", 112, "primary")
        dv.addWidget(drop_icon)
        dv.addWidget(self.drop_hint)
        dv.addLayout(hbox(None, self.btn_open_big, None))
        mv.addWidget(self.drop)

        self.info_box = QWidget()
        self.file_label = label("", "title")
        self.plan_label = label("", "sub")
        for lb in (self.file_label, self.plan_label):
            lb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.btn_open = btn("파일 열기", "Ctrl+O · 끌어다 놓아도 됩니다")
        tv = QVBoxLayout()
        tv.setSpacing(2)
        tv.addWidget(self.file_label)
        tv.addWidget(self.plan_label)
        ih = QHBoxLayout(self.info_box)
        ih.setContentsMargins(0, 0, 0, 0)
        ih.setSpacing(8)
        ih.addLayout(tv, 1)
        ih.addWidget(self.btn_open, 0, Qt.AlignmentFlag.AlignTop)
        mv.addWidget(self.info_box)

        self.load_box = QWidget()
        self.load_stage = label("", "sub")
        self.load_bar = QProgressBar()
        self.load_bar.setRange(0, 100)
        self.load_pct = label("", "sub", 40, right)
        lh = hbox(self.load_stage, (self.load_bar, 1), self.load_pct)
        lh.setContentsMargins(0, 0, 0, 0)
        self.load_box.setLayout(lh)
        self.load_box.hide()
        mv.addWidget(self.load_box)

        self.pos_label = label("00:00", "sub", 56)
        self.dur_label = label("00:00", "sub", 56, right)
        self.seek = SeekSlider()
        self.seek.setFixedHeight(H)
        mv.addLayout(hbox(self.pos_label, (self.seek, 1), self.dur_label, spacing=10))

        self.btn_back = icon("back", f"{-SEEK_BACK:.0f}초 뒤로")
        self.btn_play = icon("play", "재생 / 일시정지 (Space)", 40, "primary")
        self.btn_play.setObjectName("big")
        self.btn_fwd = icon("fwd", f"{SEEK_FWD:.0f}초 앞으로")
        self.btn_stop = icon("stop", "정지 (S) · TV 플레이어 종료")
        self.btn_mute = icon("vol", "음소거 (M)")
        self.btn_mute.setCheckable(True)
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setFixedSize(140, H)
        self.vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_label = label("", "sub", 40, right)
        mv.addLayout(hbox(self.btn_back, self.btn_play, self.btn_fwd, self.btn_stop, None,
                          self.btn_mute, self.vol, self.vol_label))

        # 트랙
        self.audio_combo, self.sub_combo = combo(), combo()
        self.btn_scale_dn = icon("minus", "자막 작게")
        self.btn_scale_up = icon("plus", "자막 크게")
        self.scale_label = label("", "", 64, center)
        tip = "자막 싱크 {} 0.5초 (Shift+클릭: 0.1초)"
        self.btn_sync_dn = icon("minus", tip.format("−"))
        self.btn_sync_up = icon("plus", tip.format("+"))
        self.sync_label = label("+0.0초", "", 64, center)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(10)
        g.addWidget(label("음성", "field", 40), 0, 0)
        g.addWidget(self.audio_combo, 0, 1, 1, 4)
        g.addWidget(label("자막", "field", 40), 1, 0)
        g.addWidget(self.sub_combo, 1, 1, 1, 4)
        g.addWidget(label("크기", "field", 40), 2, 0)
        g.addLayout(hbox(self.btn_scale_dn, self.scale_label, self.btn_scale_up, spacing=6),
                    2, 1)
        g.setColumnStretch(2, 1)
        g.addWidget(label("싱크", "field"), 2, 3)
        g.addLayout(hbox(self.btn_sync_dn, self.sync_label, self.btn_sync_up, spacing=6),
                    2, 4)
        card(root).addLayout(g)
        root.addStretch(1)                  # 창을 키워도 카드는 제 높이

        w = QWidget()
        w.setObjectName("root")
        w.setLayout(root)
        self.setCentralWidget(w)
        self.setStyleSheet(theme.qss(QSS + (QSS_LIGHT if theme.current() == "light" else "")))
        self.scale_label.setText(f"{self.ctrl.subtitle_scale:.1f}")
        self._set_volume_ui(self.cfg.volume, False)

    def _wire(self) -> None:
        b, a = self.bridge, self.acts
        b.devices_changed.connect(self._on_devices)
        b.connected.connect(self._on_connected)
        b.connection_failed.connect(self._on_connect_failed)
        b.disconnected.connect(self._on_disconnected)
        b.connection_lost.connect(self._on_lost)
        b.media_status.connect(self._on_status)
        b.volume.connect(self._on_volume)
        b.finished.connect(lambda: self._on_playback_end("재생 완료"))
        b.app_closed.connect(lambda: self._on_playback_end("TV에서 플레이어가 종료됨"))
        b.load_failed.connect(lambda c, n: self._msg(f"불러오기 실패: {n} ({c})", error=True))
        b.error.connect(lambda m: self._msg(m, error=True))

        self.tasks.progress.connect(self._on_progress)
        self.tasks.succeeded.connect(self._on_task_ok)
        self.tasks.failed.connect(self._on_task_fail)
        self.tasks.started.connect(lambda _k: self._update_ui())

        self.btn_connect.clicked.connect(self._connect_toggle)
        self.dev_combo.currentIndexChanged.connect(lambda _i: self._update_ui())
        self.btn_rescan.clicked.connect(self._rescan)
        self.btn_open.clicked.connect(self._open_dialog)
        self.btn_open_big.clicked.connect(self._open_dialog)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_back.clicked.connect(lambda: self._nudge(SEEK_BACK))
        self.btn_fwd.clicked.connect(lambda: self._nudge(SEEK_FWD))
        self.btn_mute.toggled.connect(self._on_mute)
        self.vol.valueChanged.connect(self._on_vol_slider)
        self.seek.seek_requested.connect(self._seek_to)
        self.seek.preview.connect(lambda s: self.pos_label.setText(fmt_time(s)))
        self.audio_combo.activated.connect(self._on_audio_pick)
        self.sub_combo.activated.connect(self._on_sub_pick)
        self.btn_scale_dn.clicked.connect(lambda: self._scale(-0.1))
        self.btn_scale_up.clicked.connect(lambda: self._scale(+0.1))
        self.btn_sync_dn.clicked.connect(lambda: self._sync(-1))
        self.btn_sync_up.clicked.connect(lambda: self._sync(+1))

        a.open_file.triggered.connect(self._open_dialog)
        a.rescan.triggered.connect(self._rescan)
        a.add_ip.triggered.connect(self._add_ip)
        a.disconnect.triggered.connect(self._user_disconnect)
        a.quit.triggered.connect(self.close)
        a.auto_connect.toggled.connect(self._set_auto)
        for mode, act in a.themes.items():
            act.triggered.connect(lambda _c=False, m=mode: self._set_theme(m))
        theme.notifier.changed.connect(self._restyle)
        a.log_file.toggled.connect(self._toggle_log)
        a.open_logs.triggered.connect(self._open_logs)
        a.clear_cache.triggered.connect(self._clear_cache)
        a.shortcuts.triggered.connect(lambda: show_shortcuts(self))
        a.formats.triggered.connect(lambda: show_formats(self))
        a.about.triggered.connect(lambda: show_about(self, self.ctrl.detector.get(0)))

        # M·S는 버튼이 비활성이어도 단축키가 동작하므로 연결 상태를 직접 확인
        for key, fn in (("Space", self._toggle_play), ("Left", lambda: self._nudge(-SEEK_STEP)),
                        ("Right", lambda: self._nudge(SEEK_STEP)),
                        ("Up", lambda: self._vol_step(VOL_STEP)),
                        ("Down", lambda: self._vol_step(-VOL_STEP)),
                        ("M", lambda: self._connected and self.btn_mute.toggle()),
                        ("S", lambda: self._connected and self._stop())):
            QShortcut(QKeySequence(key), self).activated.connect(fn)

    # ================= 상태 반영 =================
    def _msg(self, text: str, error: bool = False) -> None:
        self._err = error
        self._paint_status()
        self.statusBar().showMessage(text, 0 if error else 8000)
        if error:
            _LOGGER.warning("UI 알림: %s", text)

    def _paint_status(self) -> None:
        self.statusBar().setStyleSheet(
            theme.qss("QStatusBar { color: @danger; }") if self._err else "")

    def _set_conn(self, st: tuple[str, str], extra: str = "") -> None:
        self._conn, self._conn_extra = st, extra
        self.conn_label.setText(
            f"<span style='color:{theme.color(st[1])}'>●</span>&nbsp;{st[0]}{extra}")
        self._update_ui()

    def _restyle(self) -> None:
        """테마가 바뀌면 이 창이 직접 넣은 색을 다시 칠한다."""
        self.setStyleSheet(theme.qss(QSS + (QSS_LIGHT if theme.current() == "light" else "")))
        self._paint_status()
        self._set_conn(self._conn, self._conn_extra)

    def _set_title(self, name: str) -> None:
        self._title = name
        self.file_label.setToolTip(name)
        self._elide_title()

    def _elide_title(self) -> None:
        fm = self.file_label.fontMetrics()
        self.file_label.setText(fm.elidedText(self._title, Qt.TextElideMode.ElideMiddle,
                                              max(40, self.file_label.width())))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._elide_title()

    @property
    def _connected(self) -> bool:
        return self._conn is ST_OK

    def _update_ui(self) -> None:
        busy = self.tasks.busy is not None
        loaded = self.ctrl.info is not None
        ok = self._connected
        self.btn_open.setEnabled(ok and not busy)
        self.btn_open_big.setEnabled(ok and not busy)
        has_file = loaded or bool(self._title)
        self.drop.setVisible(not has_file)
        self.info_box.setVisible(has_file)
        self.drop_hint.setText("동영상 파일을 여기에 끌어다 놓으세요" if ok
                               else "먼저 기기를 연결하세요")
        dev = self.cm.device
        here = dev is not None and self.dev_combo.currentData() == dev.uuid
        self.btn_connect.setText("연결 해제" if here else "연결")
        self.acts.open_file.setEnabled(ok and not busy)
        self.acts.disconnect.setEnabled(self.cm.device is not None)
        self.acts.clear_cache.setEnabled(not self.ctrl.active and not busy)
        ctl = ok and loaded and not busy
        for w in (self.btn_play, self.btn_stop, self.btn_back, self.btn_fwd, self.seek,
                  self.audio_combo, self.sub_combo, self.btn_scale_dn, self.btn_scale_up):
            w.setEnabled(ctl)
        sub_on = ctl and self.ctrl.subtitle is not None
        self.btn_sync_dn.setEnabled(sub_on)
        self.btn_sync_up.setEnabled(sub_on)
        for w in (self.vol, self.btn_mute):
            w.setEnabled(ok)
        playing = self.ctrl.active and self._state in ("PLAYING", "BUFFERING")
        self.btn_play.setText(GLYPH["pause" if playing else "play"])
        self.setAcceptDrops(ok and not busy)

    def _fill_tracks(self) -> None:
        info, plan = self.ctrl.info, self.ctrl.plan
        self.audio_combo.clear()
        for a in info.audio if info else ():
            self.audio_combo.addItem(a.label, a.order)
        if plan and plan.audio is not None:
            self.audio_combo.setCurrentIndex(plan.audio.order)
        self.sub_combo.clear()
        self.sub_combo.addItem("끄기", 0)
        subs, cur = self.ctrl.subs, self.ctrl.subtitle
        for n, t in enumerate(subs.tracks if subs else [], 1):
            self.sub_combo.addItem(t.display, n)
            if not t.supported:                     # 회색 비활성, 자리만 남김
                self.sub_combo.model().item(n).setEnabled(False)  # pyright: ignore[reportAttributeAccessIssue]  # 기본 모델은 QStandardItemModel
            if cur is t:
                self.sub_combo.setCurrentIndex(n)
        self._show_sync()

    def _show_plan(self) -> None:
        p, info = self.ctrl.plan, self.ctrl.info
        if info is not None:
            self._set_title(info.path.name)
        self.plan_label.setText(_plan_text(p, info) if p and info else "")
        self.plan_label.setToolTip(p.summary if p else "")

    def _show_sync(self) -> None:
        t, subs = self.ctrl.subtitle, self.ctrl.subs
        d = subs.delay(t.track_id) if (t and subs) else 0.0
        self.sync_label.setText(f"{d:+.1f}초")

    # ================= 기기 =================
    def _on_devices(self, devs: list[DeviceInfo]) -> None:
        cur = self.dev_combo.currentData()
        self.dev_combo.clear()
        for d in devs:
            self.dev_combo.addItem(d.name, d.uuid)
            self.dev_combo.setItemData(self.dev_combo.count() - 1, d.host,
                                       Qt.ItemDataRole.ToolTipRole)
        target = self.cm.device.uuid if self.cm.device else (cur or self._saved_uuid())
        idx = self.dev_combo.findData(target)
        if idx >= 0:
            self.dev_combo.setCurrentIndex(idx)
        if self.cm.device is not None or self._conn is ST_BUSY:
            return
        uuids = {d.uuid for d in devs}
        # 끊긴 뒤 자동 재연결
        if (self._reconnect_uuid is not None and self._reconnect_uuid in uuids
                and time.monotonic() < self._reconnect_until):
            self._connect(self._reconnect_uuid)
            return
        # 시작 시 자동 연결 (UUID로 찾음 → 발견된 최신 IP로 연결)
        saved = self._saved_uuid()
        if self.cfg.auto_connect and not self._auto_tried and saved is not None and saved in uuids:
            self._auto_tried = True
            self._connect(saved)

    def _saved_uuid(self) -> UUID | None:
        try:
            return UUID(self.cfg.last_device_uuid) if self.cfg.last_device_uuid else None
        except ValueError:
            return None

    def _auto_host_fallback(self) -> None:
        """mDNS로 못 찾으면 저장된 IP로 검색. 그 IP의 기기 UUID가 같아야 연결된다
        (공유기가 IP를 다른 장비에 줬을 수 있음)."""
        host = self.cfg.last_device_host
        if self._auto_tried or self.cm.device is not None or not host:
            return
        self._msg(f"{self.cfg.last_device_name or '마지막 기기'}을(를) mDNS로 찾지 못해 "
                  f"{host}로 확인합니다…")
        self.cm.add_known_host(host)
        QTimer.singleShot(AUTO_HOST_FALLBACK_MS, self._auto_give_up)

    def _auto_give_up(self) -> None:
        if not self._auto_tried and self.cm.device is None:
            self._auto_tried = True
            self._msg(f"{self.cfg.last_device_name or '마지막 기기'}을(를) 찾지 못했습니다.")

    def _connect(self, uuid: UUID) -> None:
        same = uuid == self._reconnect_uuid   # 끊긴 기기 → 송출·끊김 기억 유지 (D033 ②)
        if self.ctrl.active and not same:
            self.ctrl.stop()
        self._expect_disconnect = self.cm.device is not None
        self._set_conn(ST_BUSY)
        self.cm.connect(uuid, keep_lost=same)

    def _connect_selected(self) -> None:
        uuid = self.dev_combo.currentData()
        if uuid is None:
            self._msg("기기를 먼저 찾으세요 (F5).")
            return
        self._connect(uuid)

    def _connect_toggle(self) -> None:
        """버튼 하나: 고른 기기가 연결된 기기면 해제, 아니면 연결 (D076)."""
        dev = self.cm.device
        if dev is not None and self.dev_combo.currentData() == dev.uuid:
            self._user_disconnect()
        else:
            self._connect_selected()

    def _rescan(self) -> None:
        self.cm.rescan()
        self._msg("기기를 찾는 중…")

    def _add_ip(self) -> None:
        ip = ask_ip(self)
        if not ip:
            return
        if ip not in self.cfg.known_hosts:
            self.cfg.known_hosts.append(ip)
            self.cfg.save()
        self.cm.add_known_host(ip)
        self._msg(f"{ip} 확인 중… 목록에 나타나면 [연결]을 누르세요.")

    def _user_disconnect(self) -> None:
        self._expect_disconnect = True
        self._reconnect_uuid = None
        self.ctrl.forget_lost()          # 직접 끊었으면 끊김 위치로 이어 가지 않음
        self.cm.disconnect()             # 정지 → 수신 앱 종료 → 연결 해제
        self.ctrl.shutdown()

    def _on_connected(self, dev: DeviceInfo) -> None:
        resume = self._reconnect_uuid == dev.uuid      # 끊긴 기기에 다시 연결됨
        self._reconnect_uuid = None
        self._expect_disconnect = False
        self.cfg.last_device_uuid, self.cfg.last_device_name = str(dev.uuid), dev.name
        self.cfg.last_device_host = dev.host
        self.cfg.save()
        self._set_conn(ST_OK)
        if resume and self.ctrl.recover():              # 자동 이어 재생
            self._msg("다시 연결됨. 끊긴 위치부터 이어 갑니다.")
        elif self.ctrl.info and not self.ctrl.active:
            self._msg("연결됨. 재생 버튼을 누르면 이어서 재생합니다.")

    def _on_connect_failed(self, msg: str) -> None:
        self._set_conn(ST_NONE)
        self._msg(msg, error=True)

    def _on_lost(self, dev: DeviceInfo) -> None:
        self._last_pos = self.cm.position() or self._last_pos
        self.ctrl.mark_lost()            # 송출 유지 (shutdown하면 TV가 404를 받음)
        self._state = "IDLE"
        self._reconnect_uuid = dev.uuid
        self._set_conn(ST_LOST, " — 다시 연결 중…")

    def _on_disconnected(self) -> None:
        self._state = "IDLE"
        if self._expect_disconnect:
            self._expect_disconnect = False
            if self._conn is not ST_BUSY:
                self._set_conn(ST_NONE)
            return
        # 송출 자원·끊긴 위치는 RECONNECT_WINDOW 동안 유지 (D033 ②), 정리는 _reconnect_timeout
        if self._reconnect_uuid is None and self.cfg.last_device_uuid:
            self._reconnect_uuid = self._saved_uuid()
        self._reconnect_until = time.monotonic() + RECONNECT_WINDOW
        self._set_conn(ST_LOST, f" — {int(RECONNECT_WINDOW)}초 동안 다시 찾는 중…")
        # 검색을 새로 띄우면 목록이 비어 mDNS 응답까지 기기가 안 보임 → 목록 유지 (D033 ③)
        QTimer.singleShot(int(RECONNECT_WINDOW * 1000), self._reconnect_timeout)

    def _reconnect_timeout(self) -> None:
        if self.cm.device is None and self._conn is ST_LOST:
            self._reconnect_uuid = None
            self.ctrl.shutdown()
            self.ctrl.forget_lost()
            self._set_conn(ST_NONE)
            self._msg("기기에 다시 연결하지 못했습니다. [연결]을 눌러 주세요.", error=True)

    # ================= 파일 =================
    def _open_dialog(self) -> None:
        if not self._connected:
            return
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
        start = self.cfg.last_folder if Path(self.cfg.last_folder or ".").is_dir() else ""
        path, _ = QFileDialog.getOpenFileName(self, "동영상 열기", start,
                                              f"동영상 ({exts});;모든 파일 (*)")
        if path:
            self._open(Path(path))

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls() and self._connected and not self.tasks.busy:
            e.acceptProposedAction()
        else:
            if not self._connected:
                self._msg("먼저 기기를 연결하세요.")
            e.ignore()

    def dropEvent(self, e) -> None:
        files = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self._open(files[0])

    def _open(self, path: Path) -> None:
        if not path.is_file():
            self._msg(f"파일이 없습니다: {path}", error=True)
            return
        was_active = self.ctrl.active
        if was_active and not confirm(
                self, f"지금 재생 중인 파일을 멈추고 새 파일로 바꾸겠습니까?\n\n{path.name}"):
            return
        item = PlaylistItem(path)
        self.playlist.set_single(item)
        self.cfg.last_folder = str(path.parent)
        self.cfg.save()
        self._set_title(path.name)
        self.plan_label.setText("")

        def job():
            if was_active:
                stop_and_wait(self.ctrl)
            info = self.ctrl.load(item, on_progress=self.tasks.report)
            self.ctrl.play(0.0)
            return info

        self.tasks.submit("load", job)

    def _on_progress(self, stage: str, pct: int) -> None:
        self.load_stage.setText(stage)
        self.load_bar.setValue(pct)
        self.load_pct.setText(f"{pct}%")
        self.load_box.show()

    def _on_task_ok(self, kind: str, result) -> None:
        self.load_box.hide()
        if kind == "load":
            self._last_pos = 0.0
            self.seek.set_duration(result.duration)
            self.dur_label.setText(fmt_time(result.duration))
            self._fill_tracks()
            self._msg("재생 요청을 보냈습니다.")
        elif kind == "audio":
            self._msg("음성 트랙을 바꿨습니다.")
        self._show_plan()
        self._update_ui()

    def _on_task_fail(self, kind: str, msg: str) -> None:
        self.load_box.hide()
        self._msg(("불러오기 실패: " if kind == "load" else "음성 변경 실패: ") + msg,
                  error=True)
        if kind == "audio":
            self._fill_tracks()      # 콤보를 원래 트랙으로
        self._update_ui()

    # ================= 재생 제어 =================
    def _toggle_play(self) -> None:
        if not (self._connected and self.ctrl.info) or self.tasks.busy:
            return
        if not self.ctrl.active:          # 정지·완료·재연결 뒤 → 마지막 위치부터
            self.ctrl.play(self._last_pos)
        elif self._state in ("PLAYING", "BUFFERING"):
            self.cm.pause()
        else:
            self.cm.resume()

    def _stop(self) -> None:
        if self.ctrl.active:
            self._last_pos = 0.0
            self.ctrl.stop()
            self._msg("정지 (TV 플레이어 종료)")

    def _seek_to(self, sec: float) -> None:
        if self.ctrl.info:
            self._last_pos = sec
            self.ctrl.seek(sec)

    def _nudge(self, delta: float) -> None:
        if not (self.ctrl.info and self._connected):
            return
        if not self._seek_timer.isActive():
            self._seek_acc = self.cm.position() if self.ctrl.active else self._last_pos
        dur = self.ctrl.info.duration
        self._seek_acc = min(max(0.0, self._seek_acc + delta), max(0.0, dur - 1))
        self.seek.set_position(self._seek_acc)
        self.pos_label.setText(fmt_time(self._seek_acc))
        self._seek_timer.start()

    def _flush_seek(self) -> None:
        if not self._connected:          # 끊기기 직전에 시작한 탐색은 버림
            return
        self._seek_to(self._seek_acc)

    def _on_status(self, st: PlaybackState) -> None:
        self._state = st.player_state
        if st.player_state in ("PLAYING", "PAUSED", "BUFFERING"):
            self._last_pos = st.position
            if not self._seek_timer.isActive():
                self.seek.set_position(st.position)
                self.pos_label.setText(fmt_time(st.position))
        self._update_ui()

    def _on_poll(self) -> None:
        if (self.ctrl.active and self._state == "PLAYING"
                and not self.seek.dragging and not self._seek_timer.isActive()):
            pos = self.cm.position()
            self._last_pos = pos
            self.seek.set_position(pos)
            self.pos_label.setText(fmt_time(pos))

    def _on_playback_end(self, text: str) -> None:
        self._state = "IDLE"
        if text == "재생 완료":
            self._last_pos = 0.0
        self._msg(text)
        self._update_ui()

    # ---- 볼륨 ----
    def _set_volume_ui(self, level: float, muted: bool) -> None:
        self._vol_updating = True
        self.vol.setValue(round(level * 100))
        self.btn_mute.blockSignals(True)
        self.btn_mute.setChecked(muted)
        self.btn_mute.blockSignals(False)
        self._show_mute()
        self._vol_updating = False
        self.vol_label.setText(f"{round(level * 100)}%")

    def _on_mute(self, muted: bool) -> None:
        self._show_mute()
        self.cm.set_muted(muted)

    def _show_mute(self) -> None:
        self.btn_mute.setText(GLYPH["mute" if self.btn_mute.isChecked() else "vol"])

    def _on_volume(self, level, muted) -> None:
        if level is None or self.vol.isSliderDown():
            return
        self._set_volume_ui(float(level), bool(muted))
        self.cfg.volume = float(level)

    def _on_vol_slider(self, v: int) -> None:
        self.vol_label.setText(f"{v}%")
        if not self._vol_updating and self._connected:
            self.cfg.volume = v / 100
            self.cm.set_volume(v / 100)

    def _vol_step(self, d: int) -> None:
        if self._connected:
            self.vol.setValue(min(100, max(0, self.vol.value() + d)))

    # ---- 음성 / 자막 ----
    def _on_audio_pick(self, idx: int) -> None:
        order = self.audio_combo.itemData(idx)
        plan = self.ctrl.plan
        if order is None or (plan and plan.audio and plan.audio.order == order):
            return
        if not self.tasks.submit(
                "audio", lambda: self.ctrl.set_audio(order, on_progress=self.tasks.report)):
            self._fill_tracks()

    def _on_sub_pick(self, idx: int) -> None:
        try:
            self.ctrl.select_subtitle(self.sub_combo.itemData(idx) or 0)
        except PlanError as err:
            self._msg(str(err), error=True)
        self._show_sync()
        self._update_ui()

    def _scale(self, d: float) -> None:
        s = self.ctrl.set_subtitle_scale(self.ctrl.subtitle_scale + d)
        self.scale_label.setText(f"{s:.1f}")
        self.cfg.subtitle_scale = s

    def _sync(self, sign: int) -> None:
        shift = QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
        try:
            self.ctrl.adjust_subtitle_delay(sign * (0.1 if shift else 0.5), wait=1.5)
        except PlanError as err:
            self._msg(str(err), error=True)
        self._show_sync()

    # ================= 옵션 =================
    def _set_auto(self, on: bool) -> None:
        self.cfg.auto_connect = on
        self.cfg.save()

    def _set_theme(self, mode: str) -> None:
        self.cfg.theme = mode
        self.cfg.save()
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        theme.apply_theme(app, mode)

    def _toggle_log(self, on: bool) -> None:
        err = self._set_log(on)
        self.cfg.log_file = on
        self.cfg.save()
        if err:
            self._msg(err, error=True)
        else:
            self._msg("로그 기록 " + ("켬" if on else "끔"))

    def _open_logs(self) -> None:
        d = app_dir() / "logs"
        d.mkdir(exist_ok=True)
        os.startfile(d)   # noqa: S606 (Windows 전용)

    def _clear_cache(self) -> None:
        if self.ctrl.active or not confirm(
                self, "키프레임 분석·자막 추출 캐시를 지우겠습니까?\n(다음에 열 때 다시 만듭니다)"):
            return
        for sub in ("keyframes", "subtitles"):
            shutil.rmtree(cache_dir() / sub, ignore_errors=True)
        self._msg("캐시를 비웠습니다.")

    # ================= 종료 =================
    def closeEvent(self, e) -> None:
        if self.tasks.busy == "load" and QMessageBox.question(
                self, APP_NAME, "파일을 불러오는 중입니다. 종료하겠습니까?") \
                != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        self.cfg.window_geometry = bytes(self.saveGeometry().toBase64().data()).decode()
        self.cfg.save()
        self._poll.stop()
        self.statusBar().showMessage("종료 중… (정지 → TV 플레이어 종료 → 연결 해제)")
        e.accept()          # 실제 정리는 main.py finally
