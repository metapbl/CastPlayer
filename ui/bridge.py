"""CastCallbacks(pychromecast·워커 스레드) → Qt Signal(UI 스레드).

UI 스레드에 있는 QObject의 Signal을 다른 스레드에서 emit하면 Qt가 큐에 넣어
UI 스레드에서 슬롯을 호출한다.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.cast_manager import CastCallbacks


class CastBridge(QObject):
    devices_changed = Signal(object)      # list[DeviceInfo]
    connected = Signal(object)            # DeviceInfo
    connection_failed = Signal(str)
    disconnected = Signal()
    connection_lost = Signal(object)      # DeviceInfo
    media_status = Signal(object)         # PlaybackState
    volume = Signal(object, object)       # level(float|None), muted(bool)
    finished = Signal()
    load_failed = Signal(int, str)
    app_closed = Signal()
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # PlaybackController가 on_finished/on_app_closed를 감싸므로 이 객체를 그대로 넘길 것
        self.callbacks = CastCallbacks(
            on_devices_changed=self.devices_changed.emit,
            on_connected=self.connected.emit,
            on_connection_failed=self.connection_failed.emit,
            on_disconnected=lambda: self.disconnected.emit(),
            on_media_status=self.media_status.emit,
            on_volume=self.volume.emit,
            on_finished=lambda: self.finished.emit(),
            on_load_failed=self.load_failed.emit,
            on_app_closed=lambda: self.app_closed.emit(),
            on_error=self.error.emit,
            on_connection_lost=self.connection_lost.emit,
        )
