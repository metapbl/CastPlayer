"""작은 위젯과 표시 함수."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider, QWidget


def fmt_time(sec: float | None) -> str:
    s = max(0, int(sec or 0))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class SeekSlider(QSlider):
    """탐색 바. 값은 밀리초.
    - 드래그 중에는 위치 갱신을 받지 않고 preview만 보내며, 놓을 때 seek_requested 한 번
    - 손잡이 밖을 클릭하면 그 위치로 바로 이동 (페이지 단위 이동 대신)
    - 키보드 포커스를 받지 않음 (←/→는 창 단축키가 처리)"""
    seek_requested = Signal(float)   # 초
    preview = Signal(float)          # 드래그 중 위치(초), 표시용
    SCALE = 1000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setRange(0, 0)
        self.sliderMoved.connect(lambda v: self.preview.emit(v / self.SCALE))
        self.sliderReleased.connect(
            lambda: self.seek_requested.emit(self.value() / self.SCALE))

    @property
    def dragging(self) -> bool:
        return self.isSliderDown()

    def set_duration(self, sec: float) -> None:
        self.setRange(0, max(0, int(sec * self.SCALE)))

    def set_position(self, sec: float) -> None:
        if not self.isSliderDown():
            self.setValue(int(sec * self.SCALE))

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.maximum() > 0:
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            style = self.style()
            handle = style.subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                          QStyle.SubControl.SC_SliderHandle, self)
            pos = e.position().toPoint()
            if not handle.contains(pos):
                groove = style.subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                              QStyle.SubControl.SC_SliderGroove, self)
                span = max(1, groove.width() - handle.width())
                x = pos.x() - groove.x() - handle.width() // 2
                val = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                     x, span, opt.upsideDown)
                self.setValue(val)
                self.seek_requested.emit(val / self.SCALE)
                e.accept()
                return
        super().mousePressEvent(e)
