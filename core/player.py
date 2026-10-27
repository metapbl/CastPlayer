"""재생 오케스트레이션: load(분석·준비) → play(서버 등록·송출), seek, 음성/자막 변경.

DIRECT: 파일 그대로 (Range). REMUX/TRANSCODE: HLS VOD (hls.py).
탐색은 모두 수신기 seek로 통일. 재생 종료/정지 후 탐색 시 그 위치부터 다시 불러옴.
자막: 불러올 때 모두 WebVTT로 변환해 /sub/<token>/<trackId>.vtt로 서빙.
      전환·스타일은 EDIT_TRACKS_INFO. 싱크 변경은 현재 위치에서 다시 불러옴
      (수신기는 같은 자막 파일을 다시 받지 않음, 실측).
연결이 끊긴 동안(mark_lost ~ recover 확인 완료)에는 다시 불러오기를 하지 않는다.
       play()가 이전 HLS 세션을 닫으면 TV가 이전 주소로 조각을 받다가 404를 받기 때문.
       대신 "복구 뒤 다시 불러오기"로 표시만 해 두고, recover가 확인 결과에 따라 처리한다.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from .cast_manager import CastCallbacks, CastManager, MediaRequest
from .encoders import EncoderDetector, EncoderProfile
from .hls import (HLS_MEDIA_INFO, HLS_MIME, HlsSession, Timeline, fixed_timeline,
                  keyframe_timeline)
from .keyframes import KeyframeError, keyframes
from .media_server import FileResource, HlsResource, MediaServer
from .netutil import local_ip_for
from .paths import ffmpeg_path
from .planner import Mode, Plan, PlanError, make_plan
from .playlist import PlaylistItem
from .probe import MediaInfo, probe
from .subtitles import (SUB_OFF, SubtitleSet, SubtitleTrack, clamp_scale,
                        load_subtitles, text_style)

_LOGGER = logging.getLogger(__name__)
ProgressFn = Callable[[str, int], None]   # (단계 이름, 퍼센트)


def _stage(fn: ProgressFn | None, name: str) -> Callable[[int], None] | None:
    """(단계, %) 콜백 → keyframes/subtitles용 (%) 콜백."""
    if fn is None:
        return None
    return lambda pct: fn(name, pct)


class PlaybackController:
    def __init__(self, cm: CastManager, server: MediaServer,
                 detector: EncoderDetector, callbacks: CastCallbacks,
                 subtitle_scale: float = 1.0) -> None:
        self.cm = cm
        self.server = server
        self.detector = detector
        self._cb = callbacks
        self._lock = threading.RLock()
        self.item: PlaylistItem | None = None
        self.info: MediaInfo | None = None
        self.plan: Plan | None = None
        self.timeline: Timeline | None = None
        self.encoder: EncoderProfile | None = None
        self.subs: SubtitleSet | None = None
        self.subtitle_scale = clamp_scale(subtitle_scale)
        self._sub_id: int | None = None                 # 켜진 자막 trackId (None=끔)
        self._delay_timer: threading.Timer | None = None   # 싱크 변경 후 다시 불러오기 대기
        self._route: str | None = None
        self._sub_route: str | None = None
        self._session: HlsSession | None = None
        # 연결 끊김 상태
        self._lost: tuple[float, bool] | None = None   # 끊긴 순간 (위치, 일시정지)
        self._offline = False          # 끊김 ~ 복구 확인 완료 사이 (다시 불러오기 금지)
        self._reload_pending = False   # 끊긴 동안 다시 불러오기 요청이 있었음
        self._lost_gen = 0             # 끊김 기억이 바뀔 때마다 증가 (늦게 온 확인 결과 무시용)

        # 완료/앱 종료 시 송출 자원 정리 후 상위 콜백 호출
        user_finished, user_closed = callbacks.on_finished, callbacks.on_app_closed

        def finished() -> None:
            self._release()
            if user_finished:
                user_finished()

        def app_closed() -> None:
            self._release()
            if user_closed:
                user_closed()

        callbacks.on_finished = finished
        callbacks.on_app_closed = app_closed

    @property
    def active(self) -> bool:
        return self._route is not None

    @property
    def subtitle(self) -> SubtitleTrack | None:
        """켜진 자막 트랙."""
        return self.subs.track(self._sub_id) if self.subs else None

    # ---- 준비 (시간이 걸릴 수 있음: 키프레임 분석, 인코더 확인, 자막 추출) ----
    def load(self, item: PlaylistItem, on_progress: ProgressFn | None = None) -> MediaInfo:
        info = probe(item.path)                       # ProbeError 전파
        plan = make_plan(info, item.audio_stream)     # PlanError 전파
        timeline, encoder = self._prepare(info, plan, None, on_progress)
        subs = load_subtitles(info, _stage(on_progress, "자막 추출"))
        if item.subtitle_key is None:
            sub = subs.auto_select()
        elif item.subtitle_key == SUB_OFF:
            sub = None
        else:
            sub = subs.find(item.subtitle_key)
        with self._lock:
            self.forget_lost()                        # 새 파일에 옛 끊김 위치를 쓰지 않음
            self.item, self.info, self.plan = item, info, plan
            self.timeline, self.encoder = timeline, encoder
            self.subs = subs
            self._sub_id = sub.track_id if sub else None
            item.subtitle_key = sub.key if sub else SUB_OFF
        return info

    def _prepare(self, info: MediaInfo, plan: Plan, timeline: Timeline | None,
                 on_progress: ProgressFn | None
                 ) -> tuple[Timeline | None, EncoderProfile | None]:
        if plan.mode is Mode.DIRECT:
            return timeline, self.encoder
        if info.duration <= 0:
            raise PlanError("전체 길이를 알 수 없어 HLS로 보낼 수 없습니다.")
        if not plan.video_copy:
            encoder = self.detector.get()
            if encoder is None:
                raise PlanError("사용 가능한 H.264 인코더가 없습니다.")
            return timeline or fixed_timeline(info.duration), encoder
        if timeline is None:
            try:
                kf = keyframes(info.path, info.duration,
                               _stage(on_progress, "키프레임 분석"))
            except KeyframeError as err:
                raise PlanError(str(err)) from err
            timeline = keyframe_timeline(kf, info.duration)
        return timeline, None

    # ---- 재생 ----
    def play(self, start: float = 0.0, autoplay: bool = True) -> None:
        """autoplay=False: 불러온 뒤 일시정지 상태 유지.
        새로 송출을 시작하므로 끊김 기억·복구 대기 표시를 지운다."""
        with self._lock:
            if not (self.item and self.info and self.plan):
                self._error("불러온 파일이 없습니다.")
                return
            dev = self.cm.device
            if dev is None or not dev.host:
                self._error("연결된 기기가 없습니다.")
                return
            if self.plan.mode is not Mode.DIRECT and self.timeline is None:
                self._error("HLS 준비가 되지 않았습니다.")
                return
            self.forget_lost()
            ip = local_ip_for(dev.host)
            info, plan, title = self.info, self.plan, self.item.title
            old_routes, old_session = (self._route, self._sub_route), self._session

            # 자막 트랙 (지원 트랙이 있을 때만). 매번 새 토큰 → 수신기가 VTT를 새로 받음
            media_info: dict[str, Any] = {}
            sub_route = None
            if self.subs and self.subs.supported:
                sub_route = self.server.register(HlsResource(self.subs.get), prefix="sub")
                media_info["tracks"] = self.subs.cast_tracks(
                    self.server.url_for(sub_route, ip))
                media_info["textTrackStyle"] = text_style(self.subtitle_scale)

            if plan.mode is Mode.DIRECT:
                session = None
                route = self.server.register(FileResource(info.path, "video/mp4"))
                url, mime = self.server.url_for(route, ip), "video/mp4"
            else:
                session = HlsSession(ffmpeg_path(), info, plan, self.timeline,
                                     self.encoder, start, on_error=self._error)
                route = self.server.register(HlsResource(session.get), prefix="hls")
                url, mime = self.server.url_for(route, ip) + "/master.m3u8", HLS_MIME
                media_info.update(HLS_MEDIA_INFO)
            req = MediaRequest(url=url, mime=mime, title=title, start_time=start or None,
                               duration=info.duration or None,
                               media_info=media_info or None,
                               active_track=self._sub_id,
                               autoplay=autoplay)

            for r in old_routes:
                if r:
                    self.server.unregister(r)
            if old_session:
                old_session.close()
            self._route, self._sub_route, self._session = route, sub_route, session
            _LOGGER.info("재생: %s @%.1f%s → %s", plan.mode.value, start,
                         "" if autoplay else " (일시정지 유지)", req.url)
            if self._sub_id:
                _LOGGER.info("자막: 트랙 %d (%s)", self._sub_id, self.subtitle.label)
            self.cm.play_media(req)

    def seek(self, position: float) -> None:
        with self._lock:
            if not (self.info and self.plan):
                return
            pos = max(0.0, position)
            if self.info.duration:
                pos = min(pos, max(0.0, self.info.duration - 1.0))
            _LOGGER.info("탐색: %.1f초", pos)   # 버퍼링 판정에서 탐색 뒤 10초를 빼는 기준 (D050)
            if not self.active:      # 재생 완료/정지 후 → 그 위치부터 다시 불러오기
                self.play(pos)
                return
            self.cm.seek(pos)

    def set_audio(self, order: int, on_progress: ProgressFn | None = None) -> None:
        """일시정지 중에 바꾸면 다시 불러온 뒤에도 일시정지 유지 (자막 싱크와 같은 방식).
        키프레임 분석 중에 연결이 끊겼으면 다시 불러오기는 복구 뒤로 미룸."""
        with self._lock:
            if not (self.item and self.info):
                return
            cur = self.plan.audio if self.plan else None
            if cur is not None and cur.order == order:
                _LOGGER.info("이미 선택된 음성 트랙입니다: %s", cur.label)
                return
            info, timeline = self.info, self.timeline
        plan = make_plan(info, order)                                   # PlanError 전파
        timeline, encoder = self._prepare(info, plan, timeline, on_progress)  # lock 밖
        with self._lock:
            self.item.audio_stream = order
            self.plan, self.timeline, self.encoder = plan, timeline, encoder
            if not self.active:
                return
            if self._offline:
                self._reload_pending = True
                _LOGGER.info("음성 변경: 연결 복구 중 → 복구 뒤 다시 불러옴")
                return
            pos, paused = self.cm.position(), self.cm.paused
            _LOGGER.info("음성 변경: %.1f초에서 다시 불러옴%s", pos,
                         " (일시정지 유지)" if paused else "")
            self.play(pos, autoplay=not paused)

    # ---- 자막 ----
    def select_subtitle(self, number: int) -> SubtitleTrack | None:
        """number: 0=끄기, 1부터=자막 목록 번호. 고를 수 없으면 PlanError."""
        with self._lock:
            if not (self.item and self.subs):
                raise PlanError("불러온 파일이 없습니다.")
            track = None
            if number != 0:
                if not 1 <= number <= len(self.subs.tracks):
                    raise PlanError(f"자막 #{number}이 없습니다.")
                track = self.subs.tracks[number - 1]
                if not track.supported:
                    raise PlanError(f"자막 #{number}은 고를 수 없습니다 ({track.note}).")
            self._sub_id = track.track_id if track else None
            self.item.subtitle_key = track.key if track else SUB_OFF
            if self.active:
                self.cm.set_subtitle(self._sub_id)
            return track

    def adjust_subtitle_delay(self, delta: float, wait: float = 0.0) -> float:
        """켜진 자막의 지연값 += delta (delta=0이면 0으로). +는 늦춤. 반환: 새 지연값.
        수신기는 같은 자막 파일을 다시 받지 않는다 (실측: 끄고 켜도 GET 재요청 없음).
        재생 중이면 현재 위치에서 다시 불러온다.
        wait > 0이면 마지막 변경 후 wait초 뒤 한 번만 다시 불러옴 (콘솔 0, GUI 1.5)."""
        with self._lock:
            if not (self.subs and self._sub_id):
                raise PlanError("켜진 자막이 없습니다.")
            new = 0.0 if delta == 0 else self.subs.delay(self._sub_id) + delta
            self.subs.set_delay(self._sub_id, new)
            if self.active:
                if self._delay_timer is not None:
                    self._delay_timer.cancel()
                    self._delay_timer = None
                if wait > 0:
                    timer = threading.Timer(wait, lambda: self._reload_for_subtitle(timer))
                    timer.daemon = True
                    self._delay_timer = timer
                    timer.start()
                else:
                    self._reload_for_subtitle()
            return self.subs.delay(self._sub_id)

    def _reload_for_subtitle(self, timer: threading.Timer | None = None) -> None:
        """자막 싱크 반영: 현재 위치에서 다시 불러오기.
        play()가 자막 경로를 새 토큰으로 등록하므로 수신기가 VTT를 새로 받는다.
        일시정지 중이었으면 다시 불러온 뒤에도 일시정지 유지.
        timer: 대기 후 실행일 때 자기 자신. 그 사이 새 타이머로 바뀌었으면 무시.
        연결이 끊긴 동안이면 복구 뒤로 미룸 (바뀐 지연값은 이미 저장됨)."""
        with self._lock:
            if timer is not None:
                if timer is not self._delay_timer:
                    return
                self._delay_timer = None
            if not self.active:
                return
            if self._offline:
                self._reload_pending = True
                _LOGGER.info("자막 싱크 반영: 연결 복구 중 → 복구 뒤 다시 불러옴")
                return
            pos, paused = self.cm.position(), self.cm.paused
            _LOGGER.info("자막 싱크 반영: %.1f초에서 다시 불러옴%s", pos,
                         " (일시정지 유지)" if paused else "")
            self.play(pos, autoplay=not paused)

    def set_subtitle_scale(self, scale: float) -> float:
        with self._lock:
            self.subtitle_scale = clamp_scale(scale)
            if self.active:
                self.cm.set_text_style(text_style(self.subtitle_scale))
            return self.subtitle_scale

    def stop(self) -> None:
        """수신 앱 종료가 끝난 뒤 송출 자원 정리."""
        self.forget_lost()
        self.cm.stop(then=self._release)

    def shutdown(self) -> None:
        """송출 자원 정리. 끊김 기억은 남긴다 (지우려면 forget_lost)."""
        self._release()

    # ---- 연결 끊김 / 복구 ----
    def mark_lost(self) -> None:
        """연결이 끊긴 순간 호출. 송출 자원(HLS 세션, ffmpeg, 자막 경로)은 그대로 둔다.
        TV는 버퍼로 계속 재생하다가, 다시 연결되면 같은 주소로 이어서 받아 간다.
        복구 확인이 끝날 때까지 다시 불러오기 금지. 미뤄 둔 요청은 유지.
        위치는 cm.lost_point를 쓴다. 이 시점의 cm.position()/cm.paused는
               pychromecast가 상태를 비운 뒤라 0/False다 (socket_client 원본 확인)."""
        with self._lock:
            self._lost_gen += 1
            self._offline = True
            self._lost = self.cm.lost_point if self.active else None
            if self._lost:
                _LOGGER.info("연결 끊김: %.1f초%s, 송출 유지", self._lost[0],
                             " (일시정지 중)" if self._lost[1] else "")

    def forget_lost(self) -> None:
        """끊김 기억과 복구 대기 표시를 지움 (새 파일, 정지, 사용자 연결 해제, 새 송출)."""
        with self._lock:
            self._lost_gen += 1
            self._lost = None
            self._offline = False
            self._reload_pending = False

    def recover(self) -> bool:
        """끊긴 뒤 같은 기기에 다시 연결됐을 때 호출. 복구할 것이 있었으면 True.
        - 송출이 남아 있으면 수신기 세션을 확인
            살아 있음: 그대로 이어 감 (끊긴 동안 미뤄 둔 다시 불러오기가 있으면 현재 위치에서 1회)
            없음: 끊긴 위치부터 다시 불러옴 (바뀐 음성·싱크 반영)
        - 재연결 포기로 송출이 정리됐으면 바로 끊긴 위치부터 다시 불러옴
        일시정지 중이었으면 다시 불러온 뒤에도 일시정지 유지.
        세션 확인이 끝날 때까지 끊김 상태(_offline)를 유지한다."""
        with self._lock:
            lost, self._lost = self._lost, None
            if lost is None or not (self.item and self.info):
                self._offline = self._reload_pending = False
                return False
            pos, paused = lost
            if not self.active:
                _LOGGER.info("다시 연결됨: %.1f초부터 다시 불러옴", pos)
                self.play(pos, autoplay=not paused)          # play가 끊김 상태를 지움
                return True
            route, gen = self._route, self._lost_gen

        def after(alive: bool) -> None:                      # cast 워커 스레드
            with self._lock:
                if gen != self._lost_gen or self._route != route:
                    return       # 그 사이 다시 끊김·정지·파일 교체·다시 불러오기
                pending = self._reload_pending
                self._offline = self._reload_pending = False
                if alive and not pending:
                    return
                if alive:
                    p, pa = self.cm.position(), self.cm.paused
                    _LOGGER.info("복구 뒤 미뤄 둔 다시 불러오기: %.1f초%s", p,
                                 " (일시정지 유지)" if pa else "")
                else:
                    p, pa = pos, paused
                self.play(p, autoplay=not pa)

        self.cm.check_session(after)
        return True

    # ---- 내부 ----
    def _release(self) -> None:
        with self._lock:
            if self._session:
                self._session.close()
                self._session = None
            for r in (self._route, self._sub_route):
                if r:
                    self.server.unregister(r)
            self._route = self._sub_route = None

    def _error(self, msg: str) -> None:
        _LOGGER.error(msg)
        if self._cb.on_error:
            self._cb.on_error(msg)
