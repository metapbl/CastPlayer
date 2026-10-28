"""pychromecast 래퍼: 검색, 연결, 재생 제어.

- 모든 블로킹 명령은 전용 워커 스레드 1개에서 순차 실행 (UI 스레드 차단 없음, 명령 경합 없음)
- 콜백은 pychromecast/워커 스레드에서 호출됨 → UI는 Qt Signal로 넘겨 받을 것
- 연결 감시: pychromecast 연결 상태(LOST/CONNECTED/DISCONNECTED)를 콜백으로 알림
- 다시 연결 직후 앱 채널이 열리기 전의 오류(NotConnected 등)는 실패가 아닌 "준비 전"으로 다룸
- 재생 요청은 새 세션이 생길 때까지 기다림 → 그 뒤 명령은 모두 새 세션 번호로 나감
- 연달아 끊겨도 처음 끊긴 위치를 잃지 않음, 확인 중 다시 끊기면 판정 보류
- 다시 연결 후 세션 확인은 수신기 상태를 처음 받은 뒤에 보냄 (소켓 동시 쓰기 회피)
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

import pychromecast
import zeroconf
from pychromecast.config import APP_MEDIA_RECEIVER
from pychromecast.const import CAST_TYPE_CHROMECAST
from pychromecast.controllers.media import (
    MEDIA_PLAYER_ERROR_CODES,
    MEDIA_PLAYER_STATE_BUFFERING,
    MEDIA_PLAYER_STATE_PAUSED,
    MEDIA_PLAYER_STATE_PLAYING,
    STREAM_TYPE_BUFFERED,
    MediaStatus,
    MediaStatusListener,
)
from pychromecast.controllers.receiver import CastStatus, CastStatusListener
from pychromecast.discovery import CastBrowser, SimpleCastListener
from pychromecast.error import (
    ControllerNotRegistered,
    NotConnected,
    PyChromecastError,
    PyChromecastStopped,
    UnsupportedNamespace,
)
from pychromecast.socket_client import (
    CONNECTION_STATUS_CONNECTED,
    CONNECTION_STATUS_DISCONNECTED,
    CONNECTION_STATUS_LOST,
    ConnectionStatus,
    ConnectionStatusListener,
)

_LOGGER = logging.getLogger(__name__)

_ACTIVE_STATES = (MEDIA_PLAYER_STATE_PLAYING, MEDIA_PLAYER_STATE_PAUSED,
                  MEDIA_PLAYER_STATE_BUFFERING)
# 처음 켤 자막은 재생이 시작된 뒤 보냄 (BUFFERING 중에는 tracks가 아직 안 옴, 실측 로그)
_SUB_READY_STATES = (MEDIA_PLAYER_STATE_PLAYING, MEDIA_PLAYER_STATE_PAUSED)
# 준비 전 신호: 소켓은 붙었지만 앱 채널이 아직 안 열림 (다시 연결 직후, socket_client 원본 확인)
#   세션이 죽었다는 뜻이 아니므로 실패로 판정하지 않는다.
_NOT_READY = (NotConnected, UnsupportedNamespace, ControllerNotRegistered)


# pychromecast 종료 경합 traceback 억제
#   소켓 스레드는 stop 직후에도 heartbeat PING을 보낼 수 있는데,
#   HeartbeatController.ping()은 NotConnected만 잡으므로 PyChromecastStopped가
#   run()까지 올라가 ERROR + traceback으로 기록됨 (라이브러리 코드 확인, 무해).
#   PyChromecastStopped는 우리가 disconnect()한 뒤에만 생기므로 항상 소음으로 본다.
class _StoppedNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if not isinstance(exc, PyChromecastStopped):
            return True                       # 다른 오류는 그대로
        if not logging.getLogger(record.name).isEnabledFor(logging.DEBUG):
            return False                      # -v가 아니면 출력하지 않음
        record.msg = f"{record.getMessage()} → 종료 중 heartbeat 경합 (무시)"
        record.args = None
        record.levelno, record.levelname = logging.DEBUG, "DEBUG"
        record.exc_info = record.exc_text = None
        return True


logging.getLogger("pychromecast.socket_client").addFilter(_StoppedNoiseFilter())


@dataclass(frozen=True)
class DeviceInfo:
    uuid: UUID
    name: str
    model: str | None
    host: str | None


@dataclass(frozen=True)
class MediaRequest:
    url: str
    mime: str
    title: str
    stream_type: str = STREAM_TYPE_BUFFERED   # 라이브러리 기본값(LIVE) 대신 명시
    start_time: float | None = None
    duration: float | None = None  # ffprobe 기준 전체 길이 (PC 표시용)
    # MediaInformation 추가 필드 (HLS: hlsSegmentFormat 등, 자막: tracks, textTrackStyle)
    media_info: dict[str, Any] | None = None
    active_track: int | None = None   # 처음 켤 자막 trackId (재생 시작 후 EDIT_TRACKS_INFO)
    autoplay: bool = True   # False면 불러온 뒤 일시정지 상태 유지


@dataclass(frozen=True)
class PlaybackState:
    player_state: str          # PLAYING / PAUSED / BUFFERING / IDLE / UNKNOWN
    position: float
    duration: float | None
    idle_reason: str | None


@dataclass
class CastCallbacks:
    on_devices_changed: Callable[[list[DeviceInfo]], None] | None = None
    on_connected: Callable[[DeviceInfo], None] | None = None    # 다시 연결됐을 때도 호출
    on_connection_failed: Callable[[str], None] | None = None
    on_disconnected: Callable[[], None] | None = None
    on_media_status: Callable[[PlaybackState], None] | None = None
    on_volume: Callable[[float, bool], None] | None = None
    on_finished: Callable[[], None] | None = None          # 연속재생 훅
    on_load_failed: Callable[[int, str], None] | None = None
    on_app_closed: Callable[[], None] | None = None        # TV 쪽에서 앱 종료됨
    on_error: Callable[[str], None] | None = None
    # 우리가 끊지 않았는데 연결이 끊김. pychromecast가 스스로 다시 연결을 시도하며,
    # 성공하면 on_connected, 포기하면 on_disconnected가 이어서 호출됨
    on_connection_lost: Callable[[DeviceInfo], None] | None = None


class _ConnListener(ConnectionStatusListener):
    """cast마다 하나. 이미 버린 cast의 소식은 manager가 무시한다."""

    def __init__(self, manager: "CastManager", cast: pychromecast.Chromecast) -> None:
        self._manager = manager
        self._cast = cast

    def new_connection_status(self, status: ConnectionStatus) -> None:
        self._manager._on_conn_status(self._cast, status)


class CastManager(MediaStatusListener, CastStatusListener):
    CONNECT_TIMEOUT = 15.0
    RECONNECT_FOR = 90.0     # 끊긴 순간부터 이 시간(초)까지 마지막 IP로 다시 연결 시도 (D056, D059)
    RECONNECT_EVERY = 3.0    # 그 시도 간격(초). pychromecast는 간격이 두 배씩 늘어 직접 반복
    RETRY_WAIT = 5.0         # 시도 한 번의 연결 대기(초)
    FIND_WAIT = 10.0         # [연결] 때 목록에 기기가 없으면 나타나길 기다리는 시간(초) (D033 ③)
    CMD_TIMEOUT = 5.0
    READY_WAIT = 5.0     # 다시 연결 후 앱 채널·수신기 상태를 기다리는 최대 시간(초)
    READY_POLL = 0.2     # 그 사이 다시 시도·확인 간격(초)
    LOAD_WAIT = 15.0        # 재생 요청 후 새 세션을 기다리는 최대 시간(초)
    CLOSE_LOAD_WAIT = 3.0   # 종료 중이면 이만큼만 (shutdown 제한 8초 안에 끝나도록)
    # 끊긴 위치 기록. pychromecast는 LOST를 알리기 전에 미디어 채널을 닫으며 상태를
    # 비우므로(위치 0, UNKNOWN) 끊긴 뒤에는 mc.status로 위치를 알 수 없다 (socket_client 원본 확인)
    _last_point: tuple[str, float, str, float] | None = None  # (url, 위치, 상태, time.monotonic())
    _lost_point: tuple[float, bool] | None = None             # 끊긴 순간 (위치, 일시정지)

    def __init__(self, callbacks: CastCallbacks,
                 known_hosts: list[str] | None = None) -> None:
        self.cb = callbacks
        self._known_hosts = list(known_hosts or [])
        self._zconf: zeroconf.Zeroconf | None = None
        self._browser: CastBrowser | None = None
        self._cast: pychromecast.Chromecast | None = None
        self._device: DeviceInfo | None = None
        self._req: MediaRequest | None = None
        self._expect_app = False      # 우리가 수신 앱을 띄워 사용 중인지
        self._finished_fired = False
        # (url, trackId|None): 이 url이 재생되기 시작하면 켤 자막
        self._pending_sub: tuple[str, int | None] | None = None
        # 연결이 끊긴 순간의 (요청, 처음 켤 자막). 다시 연결되면 check_session이 되살림
        self._lost: tuple[MediaRequest, tuple[str, int | None] | None] | None = None
        self._conn_gen = 0                    # LOST마다 1 증가 (확인 중 다시 끊김 판별)
        self._rx_ready = threading.Event()    # 이번 연결에서 수신기 상태를 받았는지
        # 재생 요청 대기 중: (url, 이전 세션 번호, 새 세션이 생기면 켤 이벤트)
        self._load_wait: tuple[str, int | None, threading.Event] | None = None
        # (재생 상태, 바뀐 시각): 상태가 바뀔 때마다 INFO 한 줄 (버퍼링 횟수 판정용)
        self._play_state: tuple[str, float] = ("없음", time.monotonic())
        self._lost_at = 0.0                   # 마지막 LOST 시각 (다시 연결 기한 계산)
        self._vol_lock = threading.Lock()
        self._pending_volume: float | None = None
        self._closed = False
        self._q: queue.Queue[Callable[[], None] | None] = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="cast-worker",
                                        daemon=True)
        self._worker.start()

    # ================= 검색 =================
    def start_discovery(self) -> None:
        if self._browser:
            return
        self._zconf = zeroconf.Zeroconf()
        listener = SimpleCastListener(
            add_callback=self._emit_devices,
            remove_callback=self._emit_devices,
            update_callback=self._emit_devices,
        )
        self._browser = CastBrowser(
            listener, self._zconf, self._known_hosts or None)
        self._browser.start_discovery()

    def add_known_host(self, host: str) -> None:
        """mDNS가 막힌 환경용: IP 수동 추가 후 검색 재시작."""
        if host in self._known_hosts:
            return
        self._known_hosts.append(host)
        if self._browser:
            self._browser.stop_discovery()
            self._browser = None
            if self._zconf:
                self._zconf.close()
                self._zconf = None
        self.start_discovery()

    def rescan(self) -> None:
        """기기 다시 찾기.
        연결된 기기는 다시 연결할 때 이 zeroconf를 쓰므로, 연결돼 있으면 검색을
        다시 시작하지 않고 현재 목록만 다시 알린다."""
        if self._cast is not None or not self._browser:
            self._emit_devices()
            return
        self._browser.stop_discovery()
        self._browser = None
        if self._zconf:
            self._zconf.close()
            self._zconf = None
        self.start_discovery()

    @property
    def device(self) -> DeviceInfo | None:
        """현재 연결된 기기."""
        return self._device

    def devices(self) -> list[DeviceInfo]:
        if not self._browser:
            return []
        out = []
        for uuid, ci in list(self._browser.devices.items()):
            if ci.cast_type not in (None, CAST_TYPE_CHROMECAST):
                continue  # 오디오 기기/그룹 제외
            out.append(DeviceInfo(uuid, ci.friendly_name or str(uuid),
                                  ci.model_name, ci.host))
        return sorted(out, key=lambda d: d.name)

    def _emit_devices(self, *_args) -> None:
        if self.cb.on_devices_changed:
            self.cb.on_devices_changed(self.devices())

    # ================= 공개 명령 (비동기) =================
    def connect(self, uuid: UUID, keep_lost: bool = False) -> None:
        """keep_lost: 끊긴 기기에 다시 연결 → 끊김 기억을 남겨 recover가 세션을 확인 (D033 ②)."""
        self._submit(lambda: self._do_connect(uuid, keep_lost))

    def disconnect(self) -> None:
        """사용자가 요청한 연결 해제: 정지 → 수신 앱 종료 → 연결 해제."""
        self._submit(lambda: self._do_disconnect(quit_app=True))

    def play_media(self, req: MediaRequest) -> None:
        self._submit(lambda: self._do_play(req))

    def pause(self) -> None:
        self._submit(lambda: self._media_cmd("pause"))

    def resume(self) -> None:
        self._submit(lambda: self._media_cmd("play"))

    def seek(self, position: float) -> None:
        """수신기 seek (DIRECT, HLS 공통). 위치는 원본 기준 초."""
        self._submit(lambda: self._media_cmd("seek", max(0.0, position)))

    def set_subtitle(self, track_id: int | None) -> None:
        """자막 켜기(trackId) / 끄기(None). 재생 시작 전이면 시작 후 켤 트랙만 바꿈."""
        pend = self._pending_sub
        if pend is not None:
            self._pending_sub = (pend[0], track_id)
            return
        ids = [track_id] if track_id else []
        self._submit(lambda: self._do_edit_tracks(ids, None))

    def set_text_style(self, style: dict[str, Any]) -> None:
        """자막 스타일(글자 크기 등)만 변경. 켜진 트랙은 그대로."""
        self._submit(lambda: self._do_edit_tracks(None, style))

    def check_session(self, then: Callable[[bool], None]) -> None:
        """다시 연결된 뒤, 끊기기 전 미디어 세션이 수신기에서 살아 있는지 확인.
        마지막으로 받은 상태는 끊기기 전 값일 수 있으므로 수신기에 직접 묻는다(GET_STATUS).
        (MediaStatus.update는 빈 status를 무시하므로 mc.status로는 세션 소멸을 알 수 없음)
        살아 있으면 끊기기 전 요청 상태를 되살린다. then(alive)은 워커 스레드에서 호출.
        준비 전 오류는 READY_WAIT까지 다시 시도, 판정 이유를 로그로 남김,
        되살린 뒤 현재 상태로 new_media_status를 다시 판단(전체 길이·처음 자막).
        수신기 상태(RECEIVER_STATUS)를 이번 연결에서 처음 받을 때까지 기다린 뒤 묻는다.
               다시 연결 직후 소켓 스레드도 GET_STATUS·PING을 보내는데, 같은 SSL 소켓에 동시에
               쓰면 BAD_LENGTH로 또 끊긴다 (drop_v.txt 19:53:50 실측).
        확인 중 다시 끊기면 판정하지 않고 기억을 남긴다. then은 부르지 않으며,
               다음 CONNECTED의 recover가 다시 확인한다."""

        def job() -> None:
            gen = self._conn_gen
            lost = self._lost              # 판정이 끝날 때까지 지우지 않음
            cast = self._cast
            alive, why = False, ""
            if cast is None:
                why = "연결 없음"
            elif lost is None:
                why = "기억된 요청 없음"
            else:
                deadline = time.monotonic() + self.READY_WAIT
                if not self._wait_rx_ready(cast, gen, deadline):
                    _LOGGER.debug("수신기 상태를 받지 못한 채 확인 진행")
                if self._conn_gen == gen:
                    alive, why = self._judge(cast, lost[0], deadline)
                if alive and cast is not self._cast:
                    alive, why = False, "그 사이 연결이 바뀜"
            if self._conn_gen != gen:
                _LOGGER.info("다시 연결 후 수신기 세션: 판정 보류 (확인 중 다시 끊김) "
                             "→ 다음 연결 때 다시 확인")
                return
            if self._lost is lost:
                self._lost = None
            if alive and lost is not None and cast is not None:
                req, pend = lost
                self._req, self._pending_sub = req, pend
                self._expect_app, self._finished_fired = True, False
                self.new_media_status(cast.media_controller.status)
            _LOGGER.info("다시 연결 후 수신기 세션: %s",
                         "유지됨 → 그대로 이어 감" if alive
                         else f"없음({why}) → 다시 불러옴")
            then(alive)

        self._submit(job)

    def stop(self, then: Callable[[], None] | None = None) -> None:
        """then: 정지(수신 앱 종료) 완료 후 워커 스레드에서 호출."""
        def job():
            try:
                self._do_stop()
            finally:
                if then:
                    then()
        self._submit(job)

    def set_volume(self, level: float) -> None:
        """슬라이더 연타 시 마지막 값만 전송 (coalescing)."""
        level = min(1.0, max(0.0, level))
        with self._vol_lock:
            scheduled = self._pending_volume is not None
            self._pending_volume = level
        if not scheduled:
            self._submit(self._flush_volume)

    def set_muted(self, muted: bool) -> None:
        def job():
            if cast := self._require():
                try:
                    cast.set_volume_muted(muted, timeout=self.CMD_TIMEOUT)
                except PyChromecastError as err:
                    self._cmd_error("음소거", err)
        self._submit(job)

    def position(self) -> float:
        """UI 타이머 폴링용 현재 위치(초)."""
        cast = self._cast
        if not cast:
            return 0.0
        return cast.media_controller.status.adjusted_current_time or 0.0

    @property
    def paused(self) -> bool:
        """수신기가 일시정지 상태인지 (마지막으로 받은 상태 기준)."""
        cast = self._cast
        if not cast:
            return False
        return cast.media_controller.status.player_state == MEDIA_PLAYER_STATE_PAUSED

    @property
    def lost_point(self) -> tuple[float, bool] | None:
        """마지막 연결 끊김 순간의 (위치, 일시정지). 요청이 없었으면 None.
        LOST 처리 때 소켓 스레드에서 확정되며, on_connection_lost보다 먼저 정해진다.
        복구 전에 연달아 끊기면 처음 끊긴 위치가 유지된다."""
        return self._lost_point

    def shutdown(self, timeout: float = 8.0) -> None:
        """프로그램 종료: 정지 → 수신 앱 종료 → 연결 해제 → 검색 종료."""
        if self._closed:
            return
        self._closed = True
        while True:  # 대기 중인 명령 폐기
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        done = threading.Event()

        def final():
            try:
                self._do_stop()
            finally:
                self._do_disconnect(quit_app=False)
                done.set()

        self._q.put(final)
        self._q.put(None)
        if not done.wait(timeout):
            _LOGGER.warning("종료 처리 시간 초과")
        if self._browser:
            self._browser.stop_discovery()
            self._browser = None
        if self._zconf:
            self._zconf.close()
            self._zconf = None

    # ================= 워커 내부 =================
    def _submit(self, job: Callable[[], None]) -> None:
        if not self._closed:
            self._q.put(job)

    def _run(self) -> None:
        while (job := self._q.get()) is not None:
            try:
                job()
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.exception("cast 작업 실패")
                self._error(f"내부 오류: {err}")

    def _require(self) -> pychromecast.Chromecast | None:
        if self._cast is None:
            self._error("연결된 기기가 없습니다.")
        return self._cast

    def _error(self, msg: str) -> None:
        if self.cb.on_error:
            self.cb.on_error(msg)

    def _cmd_error(self, what: str, err: PyChromecastError, notify: bool = True) -> None:
        """명령 실패 처리. 준비 전 오류는 실패가 아니라 "연결 복구 중"으로 안내.
        notify=False: 준비 전 오류면 로그만 (정지·종료 중처럼 안내가 필요 없을 때)."""
        if isinstance(err, _NOT_READY):
            _LOGGER.info("%s: 연결 복구 중이라 보내지 않음 (%s)", what, type(err).__name__)
            if notify:
                self._error(f"연결 복구 중이라 {what} 명령을 보내지 못했습니다. "
                            "잠시 후 다시 시도하세요.")
            return
        self._error(f"{what} 실패: {err}")

    def _wait_rx_ready(self, cast: pychromecast.Chromecast, gen: int,
                       deadline: float) -> bool:
        """이번 연결의 수신기 상태를 받을 때까지 대기.
        False: 기한 초과·다시 끊김·연결 변경·종료 (호출한 쪽이 _conn_gen으로 구분)."""
        while not self._rx_ready.wait(self.READY_POLL):
            if (self._closed or cast is not self._cast or self._conn_gen != gen
                    or time.monotonic() >= deadline):
                return False
        return True

    def _judge(self, cast: pychromecast.Chromecast, req: MediaRequest,
               deadline: float) -> tuple[bool, str]:
        """check_session의 판정 부분 (내용은 이전과 같음). 반환: (살아 있음, 이유)."""
        r, why = self._ask(cast, cast.socket_client.receiver_controller, deadline)
        if r is None:
            return False, why
        apps = (r.get("status") or {}).get("applications") or []
        if not any(a.get("appId") == APP_MEDIA_RECEIVER for a in apps):
            return False, "수신 앱 없음"
        r, why = self._ask(cast, cast.media_controller, deadline)
        if r is None:
            return False, why
        why = "세션 없음"
        for s in r.get("status") or []:
            if s.get("playerState") not in _ACTIVE_STATES:
                continue
            cid = (s.get("media") or {}).get("contentId")
            if cid in (None, req.url):
                return True, ""
            why = "다른 주소 재생 중"
        return False, why

    def _ask(self, cast: pychromecast.Chromecast, ctl,
             deadline: float) -> tuple[dict | None, str]:
        """ctl에 GET_STATUS를 보내고 응답 원본을 받음. 반환: (응답, 실패 이유).
        준비 전 오류는 deadline까지 READY_POLL 간격으로 다시 시도한다.
        다시 연결 중 대기 요청은 (False, None)으로 강제 완료되므로 '응답 없음'으로 본다."""
        while True:
            box: dict[str, Any] = {}
            done = threading.Event()

            def cb(*args) -> None:
                if len(args) > 1 and isinstance(args[1], dict):
                    box["r"] = args[1]
                done.set()

            try:
                ctl.send_message({"type": "GET_STATUS"}, callback_function=cb)
            except _NOT_READY as err:
                if (time.monotonic() >= deadline or self._closed
                        or cast is not self._cast):
                    return None, f"채널 준비 안 됨 ({type(err).__name__})"
                time.sleep(self.READY_POLL)
                continue
            except PyChromecastError as err:
                return None, f"오류 ({err})"
            if not done.wait(self.CMD_TIMEOUT):
                return None, "응답 없음"
            r = box.get("r")
            return (r, "") if r is not None else (None, "응답 없음")

    def _do_connect(self, uuid: UUID, keep_lost: bool = False) -> None:
        lost = self._lost
        self._do_disconnect(quit_app=True)
        self._lost = lost if keep_lost else None
        self._rx_ready.clear()
        ci = self._find_device(uuid)
        if ci is None:
            self._fail_connect("기기 정보를 찾을 수 없습니다.")
            return
        cast = None
        try:
            cast = pychromecast.get_chromecast_from_cast_info(
                ci, self._zconf, tries=3, retry_wait=2, timeout=10)
            cast.wait(timeout=self.CONNECT_TIMEOUT)
        except (PyChromecastError, OSError) as err:
            if cast:
                try:
                    cast.disconnect(timeout=2)
                except (PyChromecastError, TimeoutError):
                    pass
            self._fail_connect(f"연결 실패: {err}")
            return

        cast.register_status_listener(self)
        cast.media_controller.register_status_listener(self)
        cast.register_connection_listener(_ConnListener(self, cast))
        # 실제로 연결된 주소 (mDNS가 알려준 최신 IP)
        sc_host = cast.socket_client.host
        host = sc_host if sc_host and sc_host != "unknown" else ci.host
        self._cast = cast
        self._device = DeviceInfo(uuid, ci.friendly_name or str(uuid),
                                  ci.model_name, host)
        if self.cb.on_connected:
            self.cb.on_connected(self._device)
        if cast.status:
            self.new_cast_status(cast.status)

    def _find_device(self, uuid: UUID) -> Any:
        """검색 목록에서 기기 정보를 찾는다. 다시 찾기 직후에는 목록이 비어 있으므로 FIND_WAIT까지 기다림."""
        deadline = time.monotonic() + self.FIND_WAIT
        while True:
            ci = self._browser.devices.get(uuid) if self._browser else None
            if ci is not None or time.monotonic() >= deadline or self._closed:
                return ci
            time.sleep(self.READY_POLL)

    def _open_cast(self, dev: DeviceInfo) -> pychromecast.Chromecast:
        """마지막 IP로 직접 연결 (mDNS는 끊긴 뒤 한동안 기기를 못 찾음). 실패하면 예외."""
        assert dev.host is not None
        cast = pychromecast.get_chromecast_from_host(
            (dev.host, 8009, dev.uuid, dev.model, dev.name), tries=1, timeout=self.RETRY_WAIT)
        try:
            cast.wait(timeout=self.RETRY_WAIT)
        except (PyChromecastError, OSError):
            try:
                cast.disconnect(timeout=2)
            except (PyChromecastError, TimeoutError):
                pass
            raise
        return cast

    def _retry_connect(self, old: pychromecast.Chromecast, deadline: float) -> None:
        """워커에서 한 번 시도. 실패하면 RECONNECT_EVERY 뒤 다시 큐에 넣고, 기한이 지나면 정리.
        사용자가 끊거나 다른 기기에 연결하면(_cast가 바뀜) 그만둔다."""
        if self._cast is not old or self._closed:
            return
        dev = self._device
        assert dev is not None       # 연결된 적이 있어야 다시 연결을 시도함
        try:
            cast = self._open_cast(dev)
        except (PyChromecastError, OSError) as err:
            if time.monotonic() + self.RECONNECT_EVERY < deadline:
                _LOGGER.info("다시 연결 시도 실패 (%s): %s", dev.host, err)
                timer = threading.Timer(self.RECONNECT_EVERY, lambda: self._submit(
                    lambda: self._retry_connect(old, deadline)))
                timer.daemon = True
                timer.start()
            else:
                _LOGGER.warning("다시 연결 기한 지남: %s", dev.name)
                self._drop(old)
            return
        if self._cast is not old or self._closed:      # 시도하는 사이 사용자가 끊음
            try:
                cast.disconnect(timeout=2)
            except (PyChromecastError, TimeoutError):
                pass
            return
        try:
            old.disconnect(timeout=2)
        except (PyChromecastError, TimeoutError):
            pass
        cast.register_status_listener(self)
        cast.media_controller.register_status_listener(self)
        cast.register_connection_listener(_ConnListener(self, cast))
        self._rx_ready.clear()
        self._cast = cast
        _LOGGER.info("다시 연결됨 (마지막 IP): %s (%s)", dev.name, dev.host)
        if self.cb.on_connected:
            self.cb.on_connected(dev)    # 끊김 기억(_lost)은 그대로 → recover가 세션 확인
        if cast.status:
            self.new_cast_status(cast.status)

    def _drop(self, cast: pychromecast.Chromecast) -> None:
        """다시 연결을 포기: 연결 정보만 지우고 알린다 (송출 자원 정리는 UI가 결정)."""
        if self._cast is not cast:
            return
        self._cast = None
        self._device = None
        self._rx_ready.clear()
        try:
            cast.disconnect(timeout=2)
        except (PyChromecastError, TimeoutError):
            pass
        if self.cb.on_disconnected:
            self.cb.on_disconnected()

    def _fail_connect(self, msg: str) -> None:
        if self.cb.on_connection_failed:
            self.cb.on_connection_failed(msg)

    def _do_play(self, req: MediaRequest) -> None:
        """block_until_active 대신 새 세션이 생길 때까지 기다린다.
        block_until_active는 이전 세션 번호가 남아 있으면 바로 돌아오므로, 재생 중 다시 불러온
        직후의 정지·일시정지·탐색이 이전 세션 번호로 나가 거절됐다 (INVALID_MEDIA_SESSION_ID)."""
        cast = self._require()
        if not cast:
            return
        try:
            if cast.app_id != APP_MEDIA_RECEIVER:
                cast.start_app(APP_MEDIA_RECEIVER)
            self._req = req
            self._lost = None              # 새로 불러오면 이전 끊김 기억은 의미 없음
            self._expect_app = True
            self._finished_fired = False
            self._pending_sub = (req.url, req.active_track)
            mc = cast.media_controller
            old_sid = mc.status.media_session_id
            loaded = threading.Event()
            box: dict[str, Any] = {}

            def on_reply(*args: Any) -> None:                          # LOAD 응답
                if len(args) > 1 and isinstance(args[1], dict):
                    box["r"] = args[1]
                loaded.set()

            self._load_wait = (req.url, old_sid, loaded)
            deadline = time.monotonic() + self.READY_WAIT
            while True:
                try:
                    mc.play_media(                                # subtitles= 인자 쓰지 않음
                        req.url, req.mime,
                        title=req.title,
                        stream_type=req.stream_type,
                        current_time=req.start_time,
                        autoplay=req.autoplay,
                        media_info=req.media_info,
                        callback_function=on_reply,
                    )
                    break
                except _NOT_READY:                                     # 다시 연결 직후
                    if time.monotonic() >= deadline or cast is not self._cast:
                        raise
                    time.sleep(self.READY_POLL)
            self._wait_loaded(cast, old_sid, loaded, box)
        except PyChromecastError as err:
            self._cmd_error("재생 요청", err)
        finally:
            self._load_wait = None

    def _wait_loaded(self, cast: pychromecast.Chromecast, old_sid: int | None,
                     loaded: threading.Event, box: dict[str, Any]) -> None:
        """새 세션이 생길 때까지 대기 (워커 스레드).
        끝나는 조건: LOAD 응답 도착, 또는 새 주소의 상태가 이전과 다른 세션 번호로 도착
        (new_media_status가 loaded를 켬 — 실측상 LOAD 후 약 0.4초에 오므로 TRANSCODE도 빠름).
        다시 끊김·연결 변경이면 그만 기다리고, 기한을 넘기면 경고만 남기고 진행한다."""
        gen, t0 = self._conn_gen, time.monotonic()
        while not loaded.wait(self.READY_POLL):
            if cast is not self._cast or self._conn_gen != gen:
                _LOGGER.info("불러오기 응답 대기 중단: 연결이 바뀜")
                return
            limit = self.CLOSE_LOAD_WAIT if self._closed else self.LOAD_WAIT
            if time.monotonic() - t0 >= limit:
                _LOGGER.warning("불러오기 응답 없음 (%.0f초) — 그대로 진행", limit)
                return
        r = box.get("r") or {}
        kind = r.get("type")
        if kind not in (None, "MEDIA_STATUS"):
            _LOGGER.warning("불러오기 응답: %s %s", kind,
                            r.get("reason") or r.get("detailedErrorCode") or "")
            return
        # 응답 콜백이 상태 갱신보다 먼저 불릴 수도 있으므로 새 번호가 반영될 때까지 잠깐 확인
        mc = cast.media_controller
        end = time.monotonic() + 1.0
        while mc.status.media_session_id in (None, old_sid) and time.monotonic() < end:
            time.sleep(0.05)
        _LOGGER.debug("불러오기 완료: 세션 %s → %s (%.2f초)", old_sid,
                      mc.status.media_session_id, time.monotonic() - t0)

    def _media_cmd(self, name: str, *args) -> None:
        cast = self._require()
        if not cast:
            return
        try:
            getattr(cast.media_controller, name)(*args, timeout=self.CMD_TIMEOUT)
        except PyChromecastError as err:
            label = {"pause": "일시정지", "play": "재생", "seek": "이동"}.get(name, name)
            self._cmd_error(label, err)

    def _do_edit_tracks(self, active: list[int] | None,
                        style: dict[str, Any] | None) -> None:
        """EDIT_TRACKS_INFO 직접 전송 (enable_subtitle은 스타일을 보낼 수 없음).
        active=None이면 켜진 트랙 유지, []이면 끄기. mediaSessionId는 현재 상태 값."""
        cast = self._require()
        if not cast:
            return
        mc = cast.media_controller
        st = mc.status
        if st.media_session_id is None or st.player_state not in _ACTIVE_STATES:
            _LOGGER.debug("재생 중이 아니라 자막 설정을 보내지 않음 (%s)", st.player_state)
            return
        msg: dict[str, Any] = {"type": "EDIT_TRACKS_INFO",
                               "mediaSessionId": st.media_session_id}
        if active is not None:
            msg["activeTrackIds"] = active
        if style:
            msg["textTrackStyle"] = style
        done = threading.Event()
        try:
            mc.send_message(msg, inc_session_id=True,
                            callback_function=lambda *_: done.set())
        except PyChromecastError as err:
            self._cmd_error("자막 설정", err)
            return
        if not done.wait(self.CMD_TIMEOUT):
            self._error("자막 설정 응답 없음")

    def _do_stop(self) -> None:
        """정지 = 미디어 STOP + 기본 수신 앱 강제 종료."""
        cast = self._cast
        self._expect_app = False
        self._req = None
        self._pending_sub = None
        self._lost = None
        if not cast:
            return
        # 재생/일시정지/버퍼링 중일 때만 STOP 전송
        #   (재생 완료 후에는 세션이 없어 INVALID_MEDIA_SESSION_ID 응답)
        st = cast.media_controller.status
        if st.media_session_id is not None and st.player_state in _ACTIVE_STATES:
            try:
                cast.media_controller.stop(timeout=self.CMD_TIMEOUT)
            except PyChromecastError:
                _LOGGER.debug("STOP 실패(무시)", exc_info=True)
        try:
            # 다른 앱(유튜브 등)은 건드리지 않고 기본 수신 앱만 종료
            if cast.app_id in (APP_MEDIA_RECEIVER, None):
                cast.quit_app(timeout=self.CMD_TIMEOUT)
        except PyChromecastError as err:
            self._cmd_error("수신 앱 종료", err, notify=False)

    def _do_disconnect(self, quit_app: bool) -> None:
        self._lost = None
        cast = self._cast
        if not cast:
            return
        if quit_app:
            self._do_stop()
        self._cast = None
        self._device = None
        self._rx_ready.clear()
        try:
            cast.disconnect(timeout=5)
        except (PyChromecastError, TimeoutError):
            _LOGGER.debug("disconnect 지연", exc_info=True)
        if self.cb.on_disconnected:
            self.cb.on_disconnected()

    def _flush_volume(self) -> None:
        with self._vol_lock:
            level, self._pending_volume = self._pending_volume, None
        cast = self._require()
        if cast and level is not None:
            try:
                cast.set_volume(level, timeout=self.CMD_TIMEOUT)
            except PyChromecastError as err:
                self._cmd_error("볼륨 설정", err)

    # ================= 연결 감시 (pychromecast 소켓 스레드에서 호출) =================
    def _on_conn_status(self, cast: pychromecast.Chromecast,
                        status: ConnectionStatus) -> None:
        """우리가 끊은 cast는 _cast가 이미 None(또는 다른 cast)이라 무시된다.
        LOST: pychromecast가 스스로 다시 연결을 시도함 (tries=3, retry_wait=2, 이후 _retry_connect)
              이때 미디어 상태는 이미 비워져 있음 → 끊긴 위치는 _last_point로 계산
              복구 전에 또 끊기면(_req가 비어 있고 기억이 남아 있음) 처음 기억을 유지
        CONNECTED: LOST 뒤 다시 연결됨 (처음 연결은 리스너 등록 전이라 오지 않음)
                   이 시점에는 앱 채널이 아직 없음 → 미디어 명령은 준비 전 오류가 날 수 있음
        DISCONNECTED: pychromecast가 포기함 → 끊긴 지 RECONNECT_FOR 안이면 _retry_connect, 아니면 정리
        이 함수는 소켓 스레드에서 돌므로 응답을 기다리는 일은 절대 하지 않는다(교착)."""
        if cast is not self._cast or self._closed:
            return
        st, dev = status.status, self._device
        if st == CONNECTION_STATUS_LOST:
            _LOGGER.warning("연결 끊김: %s", dev.name if dev else "?")
            self._conn_gen += 1
            self._lost_at = time.monotonic()
            self._rx_ready.clear()
            req = self._req
            if req is None and self._lost is not None:                 # 연달아 끊김
                point = self._lost_point
                if point is not None:
                    _LOGGER.info("끊긴 위치: 이전 기록 유지 %.1f초%s", point[0],
                                 " (일시정지)" if point[1] else "")
            else:
                # 끊긴 순간의 위치·일시정지 확정
                point = None
                if req is not None:
                    rec = self._last_point
                    if rec is not None and rec[0] == req.url:
                        _, pos, pstate, t = rec
                        if pstate == MEDIA_PLAYER_STATE_PLAYING:
                            pos += time.monotonic() - t
                        if req.duration:
                            pos = min(pos, max(0.0, req.duration - 1.0))
                        point = (pos, pstate == MEDIA_PLAYER_STATE_PAUSED)
                    else:                     # 새 요청의 첫 상태를 받기 전에 끊김
                        point = (req.start_time or 0.0, not req.autoplay)
                    _LOGGER.info("끊긴 위치: %.1f초%s", point[0],
                                 " (일시정지)" if point[1] else "")
                self._lost_point = point
                # 끊기기 전 요청 기억 (수신기가 그대로 재생 중이면 되살림)
                self._lost = (req, self._pending_sub) if req is not None else None
            self._expect_app = False      # 끊긴 동안의 상태로 앱 종료/재생 완료를 오인하지 않음
            self._req = None
            self._pending_sub = None
            if dev and self.cb.on_connection_lost:
                self.cb.on_connection_lost(dev)
        elif st == CONNECTION_STATUS_CONNECTED:
            self._rx_ready.clear()        # 이번 연결의 수신기 상태는 아직 안 옴
            if dev:
                host = status.address.address if status.address else None
                dev = DeviceInfo(dev.uuid, dev.name, dev.model, host or dev.host)
                self._device = dev
                _LOGGER.info("다시 연결됨: %s (%s)", dev.name, dev.host)
                if self.cb.on_connected:
                    self.cb.on_connected(dev)
        elif st == CONNECTION_STATUS_DISCONNECTED:
            deadline = self._lost_at + self.RECONNECT_FOR
            if dev and dev.host and time.monotonic() < deadline:
                _LOGGER.warning("pychromecast 다시 연결 포기 → 마지막 IP로 %.0f초까지 직접 시도: %s",
                                deadline - time.monotonic(), dev.name)
                self._submit(lambda: self._retry_connect(cast, deadline))
            else:
                _LOGGER.warning("다시 연결 포기: %s", dev.name if dev else "?")
                self._submit(lambda: self._drop(cast))   # 소켓 스레드에서 자기 자신을 join하지 않도록

    # ================= pychromecast 리스너 =================
    def new_media_status(self, status: MediaStatus) -> None:
        if self._cast is None:
            return
        # 재생 요청 대기 해제: 새 주소의 상태가 이전과 다른 세션 번호로 도착
        wait = self._load_wait
        if (wait is not None and status.content_id == wait[0]
                and status.media_session_id not in (None, wait[1])):
            wait[2].set()
        prev, since = self._play_state
        now = time.monotonic()
        # UNKNOWN은 끊기기 직전의 빈 상태라 전환으로 세지 않음
        if status.player_state not in (prev, "UNKNOWN"):
            _LOGGER.info("재생 상태: %s → %s, %.1f초", prev, status.player_state, now - since)
            self._play_state = (status.player_state, now)
        req = self._req
        pos = status.adjusted_current_time or 0.0
        state = PlaybackState(
            player_state=status.player_state,
            position=pos,
            duration=(req.duration if req and req.duration else status.duration),
            idle_reason=status.idle_reason,
        )
        # 끊김 대비: 현재 요청의 재생 상태일 때만 위치 기록 (LOST 직전의 빈 상태는 무시됨)
        if (req is not None and status.content_id == req.url
                and status.player_state in _ACTIVE_STATES):
            self._last_point = (req.url, pos, status.player_state, time.monotonic())
        if self.cb.on_media_status:
            self.cb.on_media_status(state)
        # 새 미디어가 재생되기 시작하면 처음 자막을 켬 (이전 세션 상태는 url로 구분)
        pend = self._pending_sub
        if (pend is not None and status.content_id == pend[0]
                and status.player_state in _SUB_READY_STATES
                and status.media_session_id is not None):
            self._pending_sub = None
            track = pend[1]
            if track:
                _LOGGER.debug("자막 켜기: 트랙 %d", track)
                self._submit(lambda: self._do_edit_tracks([track], None))
        # 교체된 이전 세션의 FINISHED는 무시
        if (status.player_state == "IDLE" and status.idle_reason == "FINISHED"
                and self._expect_app and not self._finished_fired
                and req is not None and status.content_id == req.url):
            self._finished_fired = True
            if self.cb.on_finished:
                self.cb.on_finished()

    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        name = MEDIA_PLAYER_ERROR_CODES.get(error_code, "UNKNOWN")
        if self.cb.on_load_failed:
            self.cb.on_load_failed(error_code, name)

    def new_cast_status(self, status: CastStatus) -> None:
        self._rx_ready.set()   # 이 연결에서 수신기 상태 수신 → 세션 확인을 보내도 됨
        if self.cb.on_volume:
            self.cb.on_volume(status.volume_level, status.volume_muted)
        if self._expect_app and status.app_id != APP_MEDIA_RECEIVER:
            self._expect_app = False
            self._req = None
            if self.cb.on_app_closed:
                self.cb.on_app_closed()
