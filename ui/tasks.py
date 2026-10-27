"""오래 걸리는 작업(파일 불러오기, 음성 변경)을 백그라운드 스레드 1개에서 실행."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from core.planner import PlanError
from core.player import PlaybackController
from core.probe import ProbeError

_LOGGER = logging.getLogger(__name__)


class TaskRunner(QObject):
    started = Signal(str)              # 작업 종류 ("load" / "audio")
    progress = Signal(str, int)        # 단계 이름, %
    succeeded = Signal(str, object)    # 종류, 결과
    failed = Signal(str, str)          # 종류, 메시지

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._q: queue.Queue[tuple[str, Callable[[], Any]]] = queue.Queue()
        self._busy: str | None = None
        threading.Thread(target=self._run, name="ui-task", daemon=True).start()

    @property
    def busy(self) -> str | None:
        """실행 중인 작업 종류 (없으면 None)."""
        return self._busy

    def submit(self, kind: str, fn: Callable[[], Any]) -> bool:
        """한 번에 하나만. 이미 실행 중이면 False."""
        if self._busy:
            return False
        self._busy = kind
        self._q.put((kind, fn))
        self.started.emit(kind)
        return True

    def report(self, stage: str, pct: int) -> None:
        """PlaybackController의 on_progress로 넘김 (작업 스레드에서 호출됨)."""
        self.progress.emit(stage, pct)

    def _run(self) -> None:
        while True:
            kind, fn = self._q.get()
            try:
                result = fn()
            except (ProbeError, PlanError) as err:
                self._busy = None
                self.failed.emit(kind, str(err))
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("작업 실패: %s", kind)
                self._busy = None
                self.failed.emit(kind, f"내부 오류: {err}")
            else:
                self._busy = None
                self.succeeded.emit(kind, result)


def stop_and_wait(ctrl: PlaybackController, timeout: float = 10.0) -> None:
    """정지(수신 앱 종료)와 송출 자원 정리가 끝날 때까지 기다림. 작업 스레드에서만 호출.
    새 파일로 바꿀 때 사용: 정리가 늦게 돌면 새로 등록한 경로까지 지울 수 있으므로 기다린다."""
    done = threading.Event()

    def after() -> None:
        ctrl.shutdown()
        done.set()

    ctrl.cm.stop(then=after)
    if not done.wait(timeout):
        _LOGGER.warning("정지 대기 시간 초과 (%.0f초)", timeout)
