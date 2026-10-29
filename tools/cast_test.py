"""콘솔 테스트 (통합): probe → plan → DIRECT / HLS(REMUX·TRANSCODE) 송출 + 자막 + 연결 끊김 시험.

실행 (castplayer 폴더에서):
    python -m tools.cast_test "D:\\video\\movie.mkv"
    python -m tools.cast_test "D:\\video\\movie.mkv" --audio 2 --sub 1 --start 600 --host 192.0.2.10 -v
    python -m tools.cast_test --selftest                            # TV 없이 끊김·복구 자가검사
    python -m tools.cast_test "D:\\video\\movie.mkv" --droptest -v  # 실기기 끊김 시험 3장면 자동
    python -m tools.cast_test "D:\\video\\movie.mkv" -v --log       # logs/cast_test_날짜_시각.log 에도 기록
    python -m tools.cast_test "D:\\video\\movie.mkv" -v --log a     # a.log에 이어 쓰기 (확장자 생략 시 .log)

로그 단계: (없음)=INFO  -v=DEBUG(pychromecast 중복·긴 메시지 압축)  -vv=DEBUG 원본 전부
"""
# 자가검사는 가짜 객체(SimpleNamespace 등)를 진짜 타입 자리에 넣으므로 이 두 규칙은 끈다 (D068)
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
import argparse
import logging
import queue
import os
import subprocess   # 명령줄 기록용 list2cmdline
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from typing import Any, Callable, TextIO

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from pychromecast.controllers.media import MediaStatus
from pychromecast.error import NotConnected, PyChromecastError
from pychromecast.socket_client import (CONNECTION_STATUS_DISCONNECTED, CONNECTION_STATUS_LOST,
                                        ConnectionStatus)

import core.cast_manager as cm_mod  # 자가검사에서 pychromecast 연결 함수 대역 교체
import core.media_server as ms_mod  # 자가검사에서 SLOW_SEND 대역 교체
import main as main_mod             # 자가검사: GUI 로그 파일 (D070)
import core.paths as paths_mod     # 자가검사에서 bin_dir 대역 교체
import core.planner as planner_mod  # player_mod.make_plan을 바꿔도 진짜 make_plan을 부르기 위해
import core.player as player_mod   # 자가검사에서 local_ip_for·make_plan 대역 교체
from core.cast_manager import (CastCallbacks, CastManager, DeviceInfo, MediaRequest,
                               PlaybackState)
from core.config import AppConfig
from core.encoders import EncoderDetector
from core.media_server import HlsResource, MediaServer
from core.paths import app_dir, ffmpeg_path, ffprobe_path   # app_dir 추가
from core.planner import Mode, PlanError
from core.player import PlaybackController
from core.playlist import PlaylistItem
from core.probe import AudioStream, MediaInfo, ProbeError, VideoStream
from core.subtitles import Cue, SubtitleSet, SubtitleTrack, text_style
import ui.main_window as mw_mod     # 자가검사: 화면 없는 창 (D071), 대기 시간·대화창 대역 교체
from ui.bridge import CastBridge

_LOGGER = logging.getLogger("cast_test")

HELP = """명령: p=일시정지  r=재개  s=정지(앱 종료)  o=처음부터 재생
      g 초=이동(재생 끝난 뒤면 다시 불러옴)  a 번호=음성 변경  t=트랙 목록
      c 번호=자막 선택(0=끄기)  y 초=자막 싱크(+늦춤 -당김, 0=원래대로)  z 배율=자막 크기
      v 0.3=볼륨  m on|off=음소거  i=현재 위치  x=연결 끊김 시험  q=종료"""

# 탐색기 '경로 복사' 등에서 섞여 들어오는 보이지 않는 문자
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"))

LOG_DIR = app_dir() / "logs"   # --log 파일명 생략 시 (paths 기준, GUI와 같은 폴더)
LOG_EXT = ".log"               # GUI 로그와 같은 확장자 (D070)
RAW_LIMIT = 600     # -v에서 TV가 보낸 메시지(Received:)를 남길 최대 글자 수


def clean_path(s: str) -> Path:
    return Path(s.translate(_INVISIBLE).strip().strip('"'))


# ===================== 로그 파일 (--log) · 압축 (-v) =====================
class _LogSink:
    """로그 파일 하나. 모든 스레드가 같은 잠금으로 줄 단위 기록 후 즉시 flush (비정상 종료 대비)."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        fresh = not path.exists() or path.stat().st_size == 0
        self._f = open(path, "a", encoding="utf-8")  # pylint: disable=consider-using-with
        self._lock = threading.Lock()
        if not fresh:
            self.raw("")                                  # 이어 쓸 때 앞 기록과 한 줄 띄움

    def raw(self, text: str) -> None:
        """그대로 기록 (logging 줄은 이미 시각 포함)."""
        with self._lock:
            try:
                self._f.write(text + "\n")
                self._f.flush()
            except ValueError:                            # 종료 중 닫힌 뒤 늦게 온 출력
                pass

    def line(self, text: str) -> None:
        """print·입력 줄: 앞에 [시:분:초]."""
        self.raw(f"[{datetime.now():%H:%M:%S}] {text}")


class _Tee:
    """sys.stdout/stderr 대체: 화면에는 그대로, 파일에는 완성된 줄만 시각을 붙여 기록.
    스레드별로 줄을 모아 섞이지 않게 하고, '\\r'로 덮어쓰는 진행률은 마지막 상태만 남긴다."""

    def __init__(self, console: TextIO, sink: _LogSink) -> None:
        self.console, self._sink = console, sink
        self._parts: dict[int, str] = {}

    def write(self, s: str) -> int:
        self.console.write(s)
        tid = threading.get_ident()
        *lines, rest = (self._parts.get(tid, "") + s).split("\n")
        for ln in lines:
            self._sink.line(ln.rstrip("\r").rsplit("\r", 1)[-1])
        self._parts[tid] = rest.rsplit("\r", 1)[-1]
        return len(s)

    def flush(self) -> None:
        self.console.flush()

    def console_only(self, text: str) -> None:
        """입력 안내(프롬프트)는 화면에만. 파일에는 record()가 입력과 합쳐 한 줄로 남김."""
        self.console.write(text)
        self.console.flush()

    def record(self, text: str) -> None:
        self._sink.line(text)

    def __getattr__(self, name: str) -> Any:              # encoding, isatty, fileno 등
        return getattr(self.console, name)


class _SinkHandler(logging.Handler):
    """logging → 로그 파일 (print와 같은 파일·같은 잠금)."""

    def __init__(self, sink: _LogSink) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._sink.raw(self.format(record))
        except Exception:  # pylint: disable=broad-except
            self.handleError(record)


class _CompactFilter(logging.Filter):
    """-v 전용: pychromecast DEBUG의 중복·과다 출력을 줄임 (화면·파일 공통).
    - 'Media:Updated status ...', 'Received status: CastStatus(...)': 바로 앞 Received 원문의 반복 → 버림
    - '... Received: ...'(TV가 보낸 원문): RAW_LIMIT자까지만 (playerState·currentTime·activeTrackIds·
      idleReason은 앞부분에 있음). 보내는 메시지(Sending:)와 연결 흐름 줄은 그대로 둔다.
    같은 필터가 화면·파일 핸들러에 각각 붙으므로 한 기록에 두 번 불린다 → 처음 한 번만 처리."""

    DROP = ("Media:Updated status", "Received status:")

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_compacted", False):          # 두 번째 핸들러: 이미 처리됨
            return True
        if not record.name.startswith("pychromecast"):
            return True
        msg = record.getMessage()
        if msg.startswith(self.DROP):
            return False                                  # 표시 없이 버림 → 다음 핸들러도 버림
        if "] Received: " in msg and len(msg) > RAW_LIMIT:
            record.msg, record.args = f"{msg[:RAW_LIMIT]} …(+{len(msg) - RAW_LIMIT}자)", None
        record._compacted = True                          # pylint: disable=protected-access
        return True


def open_log(name: str) -> _LogSink:
    """name=''이면 logs/cast_test_날짜_시각.log, 아니면 지정 경로(현재 폴더 기준).
    확장자를 생략하면 .log를 붙이고, 직접 쓴 확장자는 그대로 둔다. 항상 이어 쓰기."""
    if not name:
        path = LOG_DIR / f"cast_test_{datetime.now():%Y%m%d_%H%M%S}{LOG_EXT}"
    else:
        path = clean_path(name).resolve()
        if not path.suffix:
            path = path.with_suffix(LOG_EXT)
    sink = _LogSink(path)
    sink.raw(f"===== 시작 {datetime.now():%Y-%m-%d %H:%M:%S} =====")
    sink.raw("명령: python -m tools.cast_test " + subprocess.list2cmdline(sys.argv[1:]))
    return sink


def setup_logging(verbose: int, selftest: bool, sink: _LogSink | None) -> None:
    """화면 핸들러는 원래 stderr에 직접 (tee를 거치면 시각이 두 번 붙음). 파일은 _SinkHandler."""
    level = (logging.DEBUG if verbose
             else logging.ERROR if selftest else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if sink:
        handlers.append(_SinkHandler(sink))
    compact = _CompactFilter() if verbose == 1 else None
    root = logging.getLogger()
    root.setLevel(level)
    for h in handlers:
        h.setFormatter(fmt)
        if compact:
            h.addFilter(compact)
        root.addHandler(h)


def ask(prompt: str) -> str:
    """input() 대신: --log일 때 입력한 명령도 '> g 3000'처럼 파일에 남김."""
    out = sys.stdout
    if isinstance(out, _Tee):
        out.console_only(prompt)
        line = input()
        out.record(prompt + line)
        return line
    return input(prompt)


def parse_cmd(line: str) -> tuple[str | None, str | None]:
    """'g 300', 'g300', 'y - 5' 모두 인식. 명령(한 글자) 뒤의 공백은 모두 지우고 붙여 읽음."""
    line = line.strip()
    if not line:
        return None, None
    rest = "".join(line[1:].split())
    return line[0].lower(), (rest or None)


def print_info(info: MediaInfo) -> None:
    print(f"파일: {info.path.name}  ({info.format_name}, {info.duration:.0f}초)")
    v = info.video
    if v:
        print(f"영상: {v.codec} {v.profile} L{v.level} {v.width}x{v.height} "
              f"{float(v.fps):.3f}fps {v.pix_fmt} tag={v.tag}")
    for a in info.audio:
        print("음성:", a.label)


def print_subs(ctrl: PlaybackController) -> None:
    """자막 목록 (번호는 c 명령용, *는 켜진 자막)."""
    subs = ctrl.subs
    if not subs or not subs.tracks:
        print("자막: 없음")
        return
    cur = ctrl.subtitle
    for n, t in enumerate(subs.tracks, 1):
        mark = "*" if cur is t else " "
        d = subs.delay(t.track_id) if t.supported else 0.0
        extra = f"  싱크 {d:+.2f}초" if d else ""
        print(f"{mark}자막 {n}: {t.display}{extra}")
    print(f"  {'(자막 끔)  ' if cur is None else ''}글자 크기 {ctrl.subtitle_scale:.2f}")


def progress(stage: str, pct: int) -> None:
    print(f"\r{stage} {pct:3d}%", end="", flush=True)
    if pct >= 100:
        print()


def print_plan(ctrl: PlaybackController) -> None:
    assert ctrl.plan is not None
    print("재생 방식:", ctrl.plan.summary)
    # DIRECT로 돌아온 뒤에도 남아 있는 timeline·encoder는 표시하지 않음 (남은 이슈 10)
    if ctrl.timeline and ctrl.plan.mode is not Mode.DIRECT:
        print(f"HLS 조각: {ctrl.timeline.count}개")
    if ctrl.encoder and ctrl.plan.mode is Mode.TRANSCODE:
        print("인코더:", ctrl.encoder.name)


# ===================== 연결 끊김 시험 (실기기) =====================
def drop_connection(cm: CastManager) -> str | None:
    """실제 '원격에서 연결이 닫힘'과 같은 경로로 끊는다. 반환: 실패 이유 (None=성공).
    pychromecast 내부 속성 사용 (socket_client 원본 확인):
      _force_recon=True → 소켓 스레드가 다음 루프에서 채널 정리 → LOST → 곧바로 다시 연결.
      socketpair[1]에 1바이트를 써서 select 대기를 즉시 깨운다 (disconnect()와 같은 방식)."""
    cast = cm._cast  # pylint: disable=protected-access
    if cast is None:
        return "연결된 기기가 없습니다."
    sc = cast.socket_client
    pair = getattr(sc, "socketpair", None)
    if not hasattr(sc, "_force_recon") or pair is None:
        return "설치된 pychromecast 버전에서는 끊김 시험을 할 수 없습니다 (내부 속성 없음)."
    sc._force_recon = True  # pylint: disable=protected-access
    try:
        pair[1].send(b"x")
    except OSError as err:
        _LOGGER.warning("select 깨우기 실패(최대 5초 뒤 끊김): %s", err)
    return None


class UiQueue:
    """GUI의 Qt 큐 연결 흉내: 콜백을 받은 순서대로 별도 스레드 하나에서 실행."""

    def __init__(self) -> None:
        self._q: queue.Queue[Callable[[], None]] = queue.Queue()
        threading.Thread(target=self._run, name="ui-sim", daemon=True).start()

    def post(self, fn: Callable[[], None]) -> None:
        self._q.put(fn)

    def _run(self) -> None:
        while True:
            fn = self._q.get()
            try:
                fn()
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("ui 작업 실패")


class Monitor:
    """끊김 시험용 사건 기록: state, lost, marked, reconnected, alive, load, load_failed, delay."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self.events: list[tuple[float, str, Any]] = []
        self.state = "UNKNOWN"
        self.lost_hook: Callable[[], None] | None = None   # mark_lost 직후 ui 스레드에서 1회 실행

    def add(self, kind: str, value: Any = None) -> None:
        with self._cond:
            self.events.append((time.monotonic(), kind, value))
            if kind == "state":
                self.state = value
            self._cond.notify_all()

    def since(self, t: float, kind: str) -> list[tuple[float, Any]]:
        return [(ts, v) for ts, k, v in list(self.events) if ts >= t and k == kind]

    def wait(self, pred: Callable[[], Any], timeout: float) -> bool:
        end = time.monotonic() + timeout
        with self._cond:
            while not pred():
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(left)
            return True


def instrument(cm: CastManager, mon: Monitor) -> None:
    """play_media·check_session 호출을 기록 (ctrl은 self.cm.play_media로 부르므로 교체가 반영됨)."""
    play, check = cm.play_media, cm.check_session

    def play_media(req: MediaRequest) -> None:
        mon.add("load", req)
        play(req)

    def check_session(then: Callable[[bool], None]) -> None:
        def done(alive: bool) -> None:
            mon.add("alive", alive)
            then(alive)
        check(done)

    cm.play_media, cm.check_session = play_media, check_session


def droptest(cm: CastManager, ctrl: PlaybackController, mon: Monitor) -> bool:
    """실기기 끊김 시험 3장면. 각 장면: 통과 / 부분 통과(세션이 없어 끊긴 위치에서 다시 불러옴) / 실패."""
    results: list[str] = []

    def report(name: str, verdict: str, detail: str) -> None:
        results.append(verdict)
        print(f"[끊김 시험] {name}: {verdict} — {detail}")

    def cycle(t0: float) -> str | None:
        err = drop_connection(cm)
        if err:
            return err
        print("  연결을 끊었습니다. 다시 연결 대기…")
        if not mon.wait(lambda: mon.since(t0, "lost"), 10):
            return "LOST가 오지 않음 (이 방법으로는 끊김이 재현되지 않음)"
        if not mon.wait(lambda: mon.since(t0, "reconnected"), 30):
            return "30초 안에 다시 연결되지 않음"
        if not mon.wait(lambda: mon.since(t0, "alive"), 20):
            return "세션 확인 결과가 오지 않음"
        return None

    def facts(t0: float) -> tuple[bool, list[MediaRequest], list[Any]]:
        alive = mon.since(t0, "alive")[-1][1]
        loads = [v for _, v in mon.since(t0, "load")]
        fails = [v for _, v in mon.since(t0, "load_failed")]
        return alive, loads, fails

    def point_text(pos0: float) -> str:
        lp = cm.lost_point
        if lp is None:
            return "끊긴 위치 기록 없음"
        return f"끊긴 위치 {lp[0]:.1f}초{'(일시정지)' if lp[1] else ''} / 끊기 직전 {pos0:.1f}초"

    def wait_reloaded(t: float, timeout: float = 60) -> bool:
        """t 이후 새로 불러오기(LOAD)가 나갔으면, 그 뒤 PLAYING이 아닌 상태(이전 세션 IDLE,
        새 세션 BUFFERING 등)를 한 번 거쳐 다시 PLAYING이 될 때까지 기다린다.
        불러오기 전부터 PLAYING이던 상태로 바로 통과하지 않기 위함 (종료 시 STOP 경합 방지)."""
        if not mon.wait(lambda: mon.since(t, "load"), 5):
            return True                      # 다시 불러오지 않았음 → 기다릴 것 없음
        t_load = mon.since(t, "load")[0][0]

        def ready() -> bool:
            other = False
            for _, v in mon.since(t_load, "state"):
                if v != "PLAYING":
                    other = True
                elif other:
                    return True
            return False

        return mon.wait(ready, timeout)

    # ---- 1. 재생 중 끊김 ----
    name = "1/3 재생 중 끊김"
    print(f"[끊김 시험] {name}: 재생 시작 대기…")
    if not mon.wait(lambda: mon.state == "PLAYING", 90):
        report(name, "실패", "재생이 시작되지 않음")
        return False
    print("  20초 재생 후 끊습니다.")
    time.sleep(20)
    t0, pos0 = time.monotonic(), cm.position()
    err = cycle(t0)
    if err:
        report(name, "실패", err)
        return False
    playing = mon.wait(lambda: mon.state == "PLAYING", 60)
    time.sleep(8)
    alive, loads, fails = facts(t0)
    lp, pos1 = cm.lost_point, cm.position()
    lp_ok = lp is not None and abs(lp[0] - pos0) < 3 and not lp[1]
    detail = (f"{point_text(pos0)}, 세션 {'유지' if alive else '없음'}, 다시 불러오기 {len(loads)}회, "
              f"로드 실패 {fails or '없음'}, 현재 {pos1:.1f}초 {mon.state}")
    if alive and not loads and not fails and playing and pos1 > pos0 + 5 and lp_ok:
        report(name, "통과", detail)
    elif (not alive and len(loads) == 1 and not fails and playing and lp_ok
          and abs((loads[0].start_time or 0.0) - pos0) < 5):
        report(name, "부분 통과", detail)
    else:
        report(name, "실패", detail)

    # ---- 2. 일시정지 중 끊김 ----
    name = "2/3 일시정지 중 끊김"
    print(f"[끊김 시험] {name}")
    cm.pause()
    if not mon.wait(lambda: mon.state == "PAUSED", 15):
        report(name, "실패", "일시정지되지 않음")
    else:
        time.sleep(2)
        t0, pos0 = time.monotonic(), cm.position()
        err = cycle(t0)
        if err:
            report(name, "실패", err)
        else:
            mon.wait(lambda: mon.state == "PAUSED", 60)
            time.sleep(3)
            alive, loads, fails = facts(t0)
            lp = cm.lost_point
            lp_ok = lp is not None and abs(lp[0] - pos0) < 1.5 and lp[1]
            still = mon.state == "PAUSED"
            detail = (f"{point_text(pos0)}, 세션 {'유지' if alive else '없음'}, "
                      f"다시 불러오기 {len(loads)}회, 로드 실패 {fails or '없음'}, 상태 {mon.state}")
            if alive and not loads and not fails and still and lp_ok:
                report(name, "통과", detail)
            elif (not alive and len(loads) == 1 and loads[0].autoplay is False
                  and not fails and still and lp_ok):
                report(name, "부분 통과", detail)
            else:
                report(name, "실패", detail)
    cm.resume()
    mon.wait(lambda: mon.state == "PLAYING", 20)

    # ---- 3. 싱크 변경 직후 끊김 ----
    name = "3/3 싱크 변경 직후 끊김"
    print(f"[끊김 시험] {name}")
    if ctrl.subtitle is None:
        subs = ctrl.subs
        n = next((i for i, t in enumerate(subs.tracks if subs else [], 1) if t.supported), 0)
        if n:
            t = ctrl.select_subtitle(n)
            assert t is not None
            print(f"  자막 {n}번을 켰습니다: {t.display}")
    if ctrl.subtitle is None:
        report(name, "건너뜀", "고를 수 있는 자막이 없음")
    elif not mon.wait(lambda: mon.state == "PLAYING", 30):
        report(name, "실패", "재생 중이 아님")
    else:
        time.sleep(3)
        t0 = time.monotonic()

        def hook() -> None:     # ui 스레드에서 mark_lost 바로 다음 (recover보다 반드시 먼저)
            mon.add("delay", ctrl.adjust_subtitle_delay(0.5))

        mon.lost_hook = hook
        err = cycle(t0)
        mon.lost_hook = None
        if err:
            report(name, "실패", err)
        else:
            mon.wait(lambda: mon.since(t0, "load"), 20)
            first = mon.since(t0, "load")
            t_load = first[0][0] if first else time.monotonic()
            playing = mon.wait(
                lambda: any(v == "PLAYING" for _, v in mon.since(t_load, "state")), 60)
            time.sleep(5)
            loads = mon.since(t0, "load")
            fails = [v for _, v in mon.since(t0, "load_failed")]
            alive_ts, alive = mon.since(t0, "alive")[0]
            early = [ts for ts, _ in loads if ts < alive_ts]
            delayed = bool(mon.since(t0, "delay"))
            detail = (f"싱크 변경 {'끊긴 동안 실행' if delayed else '실행 안 됨'}, "
                      f"세션 {'유지' if alive else '없음'}, 다시 불러오기 {len(loads)}회"
                      f"({f'복구 확인 전 {len(early)}회' if early else '모두 복구 확인 뒤'}), "
                      f"로드 실패 {fails or '없음'}, 상태 {mon.state}")
            ok = delayed and len(loads) == 1 and not early and not fails and playing
            report(name, "통과" if ok else "실패", detail)
        t_back = time.monotonic()
        ctrl.adjust_subtitle_delay(0)       # 원래 싱크로 되돌림 (다시 불러옴)
        if not wait_reloaded(t_back):                                  # 새 세션 PLAYING까지
            print("  (원래 싱크로 다시 불러온 뒤 재생을 확인하지 못함 — 판정에는 영향 없음)")

    print("[끊김 시험] 결과:", ", ".join(results))
    return "실패" not in results


# ===================== 자가검사 (TV 없이) =====================
class _FakeCM:
    """CastManager 대역. 실제처럼 끊기면 수신기 상태(위치·일시정지)가 지워진다."""

    def __init__(self) -> None:
        self.device = SimpleNamespace(host="10.0.0.9", name="시험 TV")
        self.pos, self.is_paused = 0.0, False
        self.lost_point: tuple[float, bool] | None = None
        self.loads: list[MediaRequest] = []
        self.pending: Callable[[bool], None] | None = None

    def position(self) -> float:
        return self.pos

    @property
    def paused(self) -> bool:
        return self.is_paused

    def play_media(self, req: MediaRequest) -> None:
        self.loads.append(req)

    def seek(self, _pos: float) -> None:
        pass

    def set_subtitle(self, _tid: int | None) -> None:
        pass

    def set_text_style(self, _style: dict) -> None:
        pass

    def stop(self, then: Callable[[], None] | None = None) -> None:
        if then:
            then()

    def check_session(self, then: Callable[[bool], None]) -> None:
        self.pending = then

    def drop(self, pos: float, paused: bool) -> None:
        self.lost_point = (pos, paused)
        self.pos, self.is_paused = 0.0, False

    def answer(self, alive: bool) -> None:
        then, self.pending = self.pending, None
        if then:
            then(alive)


class _FakeServer:
    def __init__(self) -> None:
        self.n = 0
        self.unregistered: list[str] = []

    def register(self, _res: Any, prefix: str = "media") -> str:
        self.n += 1
        return f"{prefix}/{self.n}"

    def url_for(self, route: str, ip: str) -> str:
        return f"http://{ip}:8765/{route}"

    def unregister(self, route: str) -> None:
        self.unregistered.append(route)


class _FakeSubs:
    supported = True

    def __init__(self) -> None:
        self._d = 0.0

    def get(self, _name: str) -> None:
        return None

    def cast_tracks(self, _base: str) -> list[dict]:
        return [{"trackId": 1}]

    def delay(self, _tid: int) -> float:
        return self._d

    def set_delay(self, _tid: int, v: float) -> None:
        self._d = v

    def track(self, tid: int) -> Any:
        return SimpleNamespace(label="시험 자막", track_id=tid)


def _fake_plan(order: int) -> Any:
    return SimpleNamespace(mode=Mode.DIRECT, video_copy=True, summary="DIRECT (시험)",
                           audio=SimpleNamespace(order=order, label=f"음성 {order + 1}"))


def _fresh(cm: _FakeCM | None = None, callbacks: CastCallbacks | None = None
           ) -> tuple[_FakeCM, PlaybackController, _FakeServer]:
    cm, server = cm or _FakeCM(), _FakeServer()
    ctrl = PlaybackController(cm, server, None, callbacks or CastCallbacks())  # type: ignore[arg-type]
    ctrl.item = SimpleNamespace(title="시험", audio_stream=None, subtitle_key=None)
    ctrl.info = SimpleNamespace(path=Path("selftest.mp4"), duration=6000.0)
    ctrl.plan = _fake_plan(0)
    ctrl.subs, ctrl._sub_id = _FakeSubs(), 1  # pylint: disable=protected-access
    ctrl.play(0.0)
    cm.loads.clear()
    return cm, ctrl, server


def _start(req: MediaRequest) -> float:
    return req.start_time or 0.0


def _desc(cm: _FakeCM) -> str:
    if not cm.loads:
        return "다시 불러오기 없음"
    return "불러오기 " + ", ".join(
        f"@{_start(r):.1f}초{'' if r.autoplay else '(일시정지)'}" for r in cm.loads)


def _sp_alive():
    cm, ctrl, _ = _fresh()
    cm.drop(1000.0, False)
    ctrl.mark_lost()
    rec = ctrl.recover()
    cm.answer(True)
    return rec and not cm.loads, _desc(cm)


def _sp_dead_pos():
    cm, ctrl, _ = _fresh()
    cm.drop(1234.5, False)
    ctrl.mark_lost()
    ctrl.recover()
    cm.answer(False)
    r = cm.loads[-1] if cm.loads else None
    return len(cm.loads) == 1 and _start(r) == 1234.5 and r is not None and r.autoplay, _desc(cm)


def _sp_dead_paused():
    cm, ctrl, _ = _fresh()
    cm.drop(500.0, True)
    ctrl.mark_lost()
    ctrl.recover()
    cm.answer(False)
    r = cm.loads[-1] if cm.loads else None
    return len(cm.loads) == 1 and _start(r) == 500.0 and r is not None and not r.autoplay, _desc(cm)


def _sp_delay_held():
    cm, ctrl, server = _fresh()
    route = ctrl._route  # pylint: disable=protected-access
    cm.drop(800.0, False)
    ctrl.mark_lost()
    ctrl.adjust_subtitle_delay(0.5)
    held = not cm.loads and ctrl._route == route and not server.unregistered  # noqa
    ctrl.recover()
    cm.pos = 805.0                 # 복구 뒤 수신기가 알려 준 현재 위치
    cm.answer(True)
    ok = held and len(cm.loads) == 1 and _start(cm.loads[0]) == 805.0
    return ok, f"끊긴 동안 {'보류됨' if held else '실행됨(HLS 세션 닫힘)'}, {_desc(cm)}"


def _sp_delay_during_check():
    cm, ctrl, _ = _fresh()
    cm.drop(400.0, False)
    ctrl.mark_lost()
    ctrl.recover()
    ctrl.adjust_subtitle_delay(0.5)          # 세션 확인 응답을 기다리는 중
    held = not cm.loads
    cm.pos = 402.0
    cm.answer(True)
    ok = held and len(cm.loads) == 1 and _start(cm.loads[0]) == 402.0
    return ok, f"확인 중 {'보류됨' if held else '실행됨'}, {_desc(cm)}"


def _sp_audio_held():
    cm, ctrl, _ = _fresh()
    cm.drop(900.0, True)
    ctrl.mark_lost()
    ctrl.set_audio(1)
    held = not cm.loads
    ctrl.recover()
    cm.answer(False)
    r = cm.loads[-1] if cm.loads else None
    audio = ctrl.plan.audio if ctrl.plan else None
    ok = (held and len(cm.loads) == 1 and _start(r) == 900.0 and r is not None and not r.autoplay
          and audio is not None and audio.order == 1)
    return ok, f"끊긴 동안 {'보류됨' if held else '실행됨'}, {_desc(cm)}"


def _sp_giveup():
    cm, ctrl, _ = _fresh()
    cm.drop(700.0, False)
    ctrl.mark_lost()
    ctrl.shutdown()                          # 재연결 포기 → 송출 정리 (끊김 기억은 남음)
    rec = ctrl.recover()
    ok = rec and cm.pending is None and len(cm.loads) == 1 and _start(cm.loads[0]) == 700.0
    return ok, _desc(cm)


def _sp_user_disconnect():
    cm, ctrl, _ = _fresh()
    cm.drop(600.0, False)
    ctrl.mark_lost()
    ctrl.forget_lost()                       # 메뉴 "연결 해제"
    ctrl.shutdown()
    rec = ctrl.recover()
    return not rec and not cm.loads, _desc(cm)


def _sp_stop():
    cm, ctrl, _ = _fresh()
    cm.drop(600.0, False)
    ctrl.mark_lost()
    ctrl.stop()
    rec = ctrl.recover()
    return not rec and not cm.loads, _desc(cm)


def _sp_seek_log():
    lines: list[str] = []

    class _Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(record.getMessage())

    log = logging.getLogger("core.player")
    grab, level, prop = _Grab(), log.level, log.propagate
    log.addHandler(grab)
    log.setLevel(logging.INFO)               # 자가검사는 ERROR만 보이므로 잠시 낮춤
    log.propagate = False
    try:
        _cm, ctrl, _ = _fresh()
        ctrl.seek(123.45)
    finally:
        log.removeHandler(grab)
        log.setLevel(level)
        log.propagate = prop
    return "탐색: 123.5초" in lines, f"{lines}"


def _sp_new_play():
    cm, ctrl, _ = _fresh()
    cm.drop(300.0, False)
    ctrl.mark_lost()
    ctrl.play(0.0)                           # 직접 연결 후 새로 재생 → 끊김 상태 지움
    rec = ctrl.recover()
    ctrl.adjust_subtitle_delay(0.5)          # 이제는 바로 다시 불러와야 함
    return not rec and len(cm.loads) == 2, _desc(cm)


def _sp_late_answer():
    cm, ctrl, _ = _fresh()
    cm.drop(100.0, False)
    ctrl.mark_lost()
    ctrl.recover()
    first, cm.pending = cm.pending, None
    cm.drop(200.0, False)                    # 확인 중 다시 끊김
    ctrl.mark_lost()
    assert first is not None
    first(False)                             # 첫 번째 확인 결과가 늦게 도착
    ignored = not cm.loads
    ctrl.recover()
    cm.answer(False)
    ok = ignored and len(cm.loads) == 1 and _start(cm.loads[0]) == 200.0
    return ok, f"늦은 결과 {'무시됨' if ignored else '반영됨'}, {_desc(cm)}"


_PLAYER_CASES = [
    ("재생 중 끊김 → 세션 유지면 다시 불러오지 않음", _sp_alive),
    ("세션 없음 → 끊긴 위치부터 (상태가 지워진 뒤에도)", _sp_dead_pos),
    ("일시정지 중 끊김 → 일시정지 유지로 다시 불러옴", _sp_dead_paused),
    ("끊긴 동안 싱크 변경 → 보류 후 복구 뒤 1회", _sp_delay_held),
    ("세션 확인 중 싱크 변경 → 보류 후 1회", _sp_delay_during_check),
    ("끊긴 동안 음성 변경 → 보류 후 끊긴 위치에서 1회", _sp_audio_held),
    ("재연결 포기 후 다시 연결 → 끊긴 위치부터", _sp_giveup),
    ("메뉴 연결 해제 후 → 이어 재생 안 함", _sp_user_disconnect),
    ("정지 후 → 이어 재생 안 함", _sp_stop),
    ("탐색하면 INFO 한 줄 (버퍼링 판정용)", _sp_seek_log),
    ("새로 재생한 뒤 → 끊김 상태 해제", _sp_new_play),
    ("늦게 온 세션 확인 결과 → 무시", _sp_late_answer),
]


class _FakeCtl:
    """GET_STATUS를 받는 컨트롤러 대역: fails번 exc를 던진 뒤 reply로 응답."""

    def __init__(self, fails: int = 0, exc: Callable[[], Exception] = NotConnected,
                 reply: tuple = (True, {"status": []})) -> None:
        self.fails, self.exc, self.reply, self.sent = fails, exc, reply, 0

    def send_message(self, _msg: dict, callback_function=None, **_kw) -> None:
        self.sent += 1
        if self.fails > 0:
            self.fails -= 1
            raise self.exc()
        if callback_function:
            callback_function(*self.reply)


def _manager_cases(check: Callable[[str, bool, str], None]) -> None:
    # pylint: disable=protected-access
    cm = CastManager(CastCallbacks())
    cm.READY_POLL = 0.01
    cast = object()
    cm._cast = cast

    def case(name: str, fn: Callable[[], tuple[bool, str]]) -> None:
        try:
            ok, detail = fn()
        except Exception as err:  # pylint: disable=broad-except
            ok, detail = False, f"예외: {err!r}"
        check(name, ok, detail)

    def ask_retry():
        ctl = _FakeCtl(fails=3)
        r, why = cm._ask(cast, ctl, time.monotonic() + 1.0)
        return r is not None and ctl.sent == 4, f"시도 {ctl.sent}회 {why}"

    def ask_timeout():
        ctl = _FakeCtl(fails=10_000)
        r, why = cm._ask(cast, ctl, time.monotonic() + 0.2)
        return r is None and "채널 준비 안 됨" in why, why

    def ask_error():
        ctl = _FakeCtl(fails=1, exc=lambda: PyChromecastError("시험 오류"))
        r, why = cm._ask(cast, ctl, time.monotonic() + 1.0)
        return r is None and ctl.sent == 1 and "오류" in why, f"시도 {ctl.sent}회 {why}"

    def ask_false():
        r, why = cm._ask(cast, _FakeCtl(reply=(False, None)), time.monotonic() + 1.0)
        return r is None and why == "응답 없음", why

    def status(url: str, state: str, pos: float) -> MediaStatus:
        st = MediaStatus()
        st.content_id, st.player_state, st.current_time = url, state, pos
        st.media_session_id = 1
        st.last_updated = datetime.now(timezone.utc)
        return st

    lost = ConnectionStatus(CONNECTION_STATUS_LOST, None, None)
    req_a = MediaRequest(url="http://t/a", mime="video/mp4", title="t", duration=6000.0)

    def point_paused():
        cm._req = req_a
        cm.new_media_status(status(req_a.url, "PAUSED", 321.0))
        cm.new_media_status(MediaStatus())       # LOST 직전 pychromecast가 보내는 빈 상태
        cm._on_conn_status(cast, lost)
        lp = cm.lost_point
        return lp is not None and abs(lp[0] - 321.0) < 0.01 and lp[1], f"{lp}"

    def point_playing():
        cm._req = req_a
        cm.new_media_status(status(req_a.url, "PLAYING", 100.0))
        time.sleep(0.3)
        cm.new_media_status(MediaStatus())
        cm._on_conn_status(cast, lost)
        lp = cm.lost_point
        return lp is not None and abs(lp[0] - 100.3) < 0.15 and not lp[1], f"{lp}"

    def point_before_first_status():
        cm._req = MediaRequest(url="http://t/b", mime="video/mp4", title="t",
                               start_time=50.0, autoplay=False)
        cm._on_conn_status(cast, lost)           # 기록은 이전 주소(a) 것뿐
        lp = cm.lost_point
        return lp == (50.0, True), f"{lp}"

    def state_log():
        lines: list[str] = []

        class _Grab(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if record.getMessage().startswith("재생 상태:"):
                    lines.append(record.getMessage())

        log = logging.getLogger("core.cast_manager")
        grab, level, prop = _Grab(), log.level, log.propagate
        log.addHandler(grab)
        log.setLevel(logging.INFO)               # 자가검사는 ERROR만 보이므로 잠시 낮춤
        log.propagate = False                    # 화면에는 내보내지 않음
        try:
            cm._req = req_a
            cm._play_state = ("PAUSED", time.monotonic())
            cm.new_media_status(status(req_a.url, "PLAYING", 10.0))
            cm.new_media_status(status(req_a.url, "PLAYING", 10.5))   # 같은 상태 → 줄 없음
            time.sleep(0.2)
            cm.new_media_status(status(req_a.url, "BUFFERING", 10.7))
            cm.new_media_status(MediaStatus())                        # 빈 상태(UNKNOWN) → 무시
            cm.new_media_status(status(req_a.url, "PLAYING", 11.0))
        finally:
            log.removeHandler(grab)
            log.setLevel(level)
            log.propagate = prop
        heads = [ln.split(",")[0] for ln in lines]
        want = ["재생 상태: PAUSED → PLAYING", "재생 상태: PLAYING → BUFFERING",
                "재생 상태: BUFFERING → PLAYING"]
        secs = float(lines[1].split(", ")[1].rstrip("초")) if len(lines) > 1 else -1.0
        return heads == want and secs >= 0.2, f"{lines}"

    # ---- 연달아 끊김·확인 중 끊김·수신기 상태 대기 ----
    apps_reply = (True, {"status": {"applications": [{"appId": "CC1AD845"}]}})  # 기본 수신 앱
    media_reply = (True, {"status": [{"playerState": "PLAYING",
                                      "media": {"contentId": req_a.url}}]})

    def fake_cast(rx: _FakeCtl, media: _FakeCtl) -> Any:
        media.status = MediaStatus()             # type: ignore[attr-defined]
        return SimpleNamespace(socket_client=SimpleNamespace(receiver_controller=rx),
                               media_controller=media)

    def point_double_lost():
        cm._req = req_a
        cm.new_media_status(status(req_a.url, "PAUSED", 654.0))
        cm._on_conn_status(cast, lost)
        first = cm._lost
        cm._on_conn_status(cast, lost)           # 다시 연결 직후 또 끊김 (_req는 이미 비어 있음)
        lp = cm.lost_point
        ok = (first is not None and cm._lost is first and lp is not None
              and abs(lp[0] - 654.0) < 0.01 and lp[1])
        return ok, f"{lp}, 요청 기억 {'유지' if cm._lost is first else '지워짐'}"

    def check_held():
        class _LostOnSend(_FakeCtl):
            def send_message(self, msg, callback_function=None, **kw):
                cm._on_conn_status(fc, lost)     # 확인 중에 다시 끊김
                super().send_message(msg, callback_function=callback_function, **kw)

        fc = fake_cast(_LostOnSend(reply=apps_reply), _FakeCtl(reply=media_reply))
        cm._cast, cm._req = fc, None
        cm._lost = mem = (req_a, None)
        cm._rx_ready.set()
        got = threading.Event()
        cm.check_session(lambda _alive: got.set())
        called = got.wait(1.0)
        ok = not called and cm._lost is mem
        return ok, (f"결과 {'전달됨' if called else '보류'}, "
                    f"요청 기억 {'유지' if cm._lost is mem else '지워짐'}")

    def check_waits_rx():
        rx = _FakeCtl(reply=apps_reply)
        fc = fake_cast(rx, _FakeCtl(reply=media_reply))
        cm._cast, cm._req = fc, None
        cm._lost = (req_a, None)
        cm._rx_ready.clear()                     # 다시 연결 직후: 수신기 상태 아직 안 옴
        res: list[bool] = []
        got = threading.Event()
        cm.check_session(lambda alive: (res.append(alive), got.set()))
        time.sleep(0.3)
        early = rx.sent
        cm.new_cast_status(SimpleNamespace(volume_level=1.0, volume_muted=False,
                                           app_id="CC1AD845"))
        got.wait(2.0)
        ok = early == 0 and rx.sent == 1 and res == [True]
        return ok, f"상태 받기 전 전송 {early}회, 뒤 {rx.sent}회, 결과 {res}"

    try:
        case("세션 확인: 준비 전 오류 3회 뒤 응답 → 다시 시도해 받음", ask_retry)
        case("세션 확인: 준비 전 오류가 계속 → 기한 뒤 '채널 준비 안 됨'", ask_timeout)
        case("세션 확인: 그 밖의 오류 → 다시 시도 없이 실패", ask_error)
        case("세션 확인: 대기 요청 강제 완료(False) → '응답 없음'", ask_false)
        case("끊긴 위치: 일시정지 중 (빈 상태에 지워지지 않음)", point_paused)
        case("재생 상태 전환 로그: 바뀔 때만 한 줄, 이전 상태 유지 시간", state_log)
        case("끊긴 위치: 재생 중 경과 시간 반영", point_playing)
        case("끊긴 위치: 첫 상태 전 끊김 → 시작 위치·autoplay 기준", point_before_first_status)
        case("끊긴 위치: 연달아 두 번 끊김 → 처음 위치 유지", point_double_lost)
        case("세션 확인: 확인 중 다시 끊김 → 판정 보류·기억 유지", check_held)
        case("세션 확인: 수신기 상태 받기 전에는 보내지 않음", check_waits_rx)
    finally:
        cm._cast, cm._req, cm._expect_app = None, None, False
        cm.shutdown(timeout=1.0)


def _reconnect_cases(check: Callable[[str, bool, str], None]) -> None:
    """pychromecast가 포기한 뒤 마지막 IP로 직접 다시 연결 (D056). 기한·간격은 짧게 줄여 시험."""
    # pylint: disable=protected-access
    lost = ConnectionStatus(CONNECTION_STATUS_LOST, None, None)
    gone = ConnectionStatus(CONNECTION_STATUS_DISCONNECTED, None, None)
    req = MediaRequest(url="http://t/r", mime="video/mp4", title="t", duration=6000.0)

    def run(fails: int, cut_after: float | None = None) -> dict:
        ev = {"connected": [], "disconnected": 0, "tries": []}
        done = threading.Event()

        def on_conn(dev) -> None:
            ev["connected"].append(dev)
            done.set()

        def on_gone() -> None:
            ev["disconnected"] += 1
            done.set()

        cm = CastManager(CastCallbacks(on_connected=on_conn, on_disconnected=on_gone))
        cm.RECONNECT_FOR, cm.RECONNECT_EVERY = 0.6, 0.1
        old = SimpleNamespace(disconnect=lambda timeout=None: None)
        new = SimpleNamespace(register_status_listener=lambda _l: None,
                              media_controller=SimpleNamespace(
                                  register_status_listener=lambda _l: None),
                              register_connection_listener=lambda _l: None,
                              socket_client=SimpleNamespace(host="10.0.0.9"), status=None,
                              disconnect=lambda timeout=None: None)
        dev = DeviceInfo(uuid4(), "시험 TV", None, "10.0.0.9")

        def open_cast(d: DeviceInfo) -> Any:
            ev["tries"].append((time.monotonic(), d.host))
            if len(ev["tries"]) <= fails:
                raise PyChromecastError("시험 연결 실패")
            return new

        cm._open_cast = open_cast                # type: ignore[method-assign]
        cm._cast, cm._device, cm._req = old, dev, req
        try:
            cm._on_conn_status(old, lost)
            ev["lost_kept"] = cm._lost
            cm._on_conn_status(old, gone)        # pychromecast가 다시 연결을 포기
            if cut_after is not None:
                time.sleep(cut_after)
                cm._cast = None                  # 사용자가 끊음 (_do_disconnect와 같은 효과)
                n = len(ev["tries"])
                time.sleep(0.4)
                ev["after_cut"] = len(ev["tries"]) - n
            else:
                done.wait(2.0)
            ev["now_cast"], ev["new"], ev["dev"], ev["lost"] = cm._cast, new, dev, cm._lost
        finally:
            cm._cast = None
            cm.shutdown(timeout=1.0)
        return ev

    def give_up():
        ev = run(fails=10_000)
        t = [x[0] for x in ev["tries"]]
        gaps = [b - a for a, b in zip(t, t[1:])]
        ok = (ev["disconnected"] == 1 and len(t) >= 4 and not ev["connected"]
              and all(0.08 <= g < 0.3 for g in gaps)
              and all(h == "10.0.0.9" for _, h in ev["tries"]))
        return ok, f"시도 {len(t)}회, 간격 {[round(g, 2) for g in gaps]}, 해제 {ev['disconnected']}회"

    def succeed():
        ev = run(fails=2)
        ok = (len(ev["tries"]) == 3 and len(ev["connected"]) == 1
              and ev["connected"][0].uuid == ev["dev"].uuid and ev["now_cast"] is ev["new"]
              and ev["lost"] is not None and ev["lost"] is ev["lost_kept"]
              and ev["disconnected"] == 0)
        return ok, (f"시도 {len(ev['tries'])}회, 연결 {len(ev['connected'])}회, "
                    f"기억 {'유지' if ev['lost'] is not None else '지워짐'}")

    def user_cut():
        ev = run(fails=10_000, cut_after=0.25)
        return ev["after_cut"] == 0 and ev["disconnected"] == 0,             f"끊은 뒤 시도 {ev['after_cut']}회, 해제 알림 {ev['disconnected']}회"

    for name, fn in (("다시 연결: 기한까지 같은 간격으로 마지막 IP에 시도한 뒤 포기", give_up),
                     ("다시 연결: 도중 성공 → 끊김 기억 유지한 채 연결 알림", succeed),
                     ("다시 연결: 사용자가 끊으면 시도 중단", user_cut)):
        try:
            ok, detail = fn()
        except Exception as err:  # pylint: disable=broad-except
            ok, detail = False, f"예외: {err!r}"
        check(name, ok, detail)


def _keep_lost_cases(check: Callable[[str, bool, str], None]) -> None:
    """다시 연결 포기 뒤 같은 기기에 연결하면 끊김 기억 유지, 다른 기기면 지움 (D033 ②)."""
    # pylint: disable=protected-access
    req = MediaRequest(url="http://t/k", mime="video/mp4", title="t", duration=6000.0)
    same, other = uuid4(), uuid4()

    def fake_cast(*_a, **_kw) -> Any:
        return SimpleNamespace(wait=lambda timeout=None: None,
                               register_status_listener=lambda _l: None,
                               media_controller=SimpleNamespace(
                                   register_status_listener=lambda _l: None),
                               register_connection_listener=lambda _l: None,
                               socket_client=SimpleNamespace(host="10.0.0.9"), status=None,
                               disconnect=lambda timeout=None: None)

    def run(target, keep: bool) -> bool:
        got = threading.Event()
        cm = CastManager(CastCallbacks(on_connected=lambda _d: got.set()))
        cm._browser = SimpleNamespace(devices={
            u: SimpleNamespace(friendly_name="시험 TV", model_name=None, host="10.0.0.9")
            for u in (same, other)})
        cm._lost = mem = (req, None)            # 포기 뒤: _cast는 없고 기억만 남음
        try:
            cm.connect(target, keep_lost=keep)
            got.wait(2.0)
            return cm._lost is mem
        finally:
            cm._cast, cm._browser = None, None
            cm.shutdown(timeout=1.0)

    def late_device(appear_after: float | None) -> tuple[bool, str]:
        res: dict[str, Any] = {}
        done = threading.Event()
        cm = CastManager(CastCallbacks(
            on_connected=lambda d: (res.setdefault("ok", d), done.set()),
            on_connection_failed=lambda m: (res.setdefault("fail", m), done.set())))
        cm.FIND_WAIT = 0.6
        devs: dict = {}
        cm._browser = SimpleNamespace(devices=devs)
        try:
            t0 = time.monotonic()
            cm.connect(same)
            if appear_after is not None:
                time.sleep(appear_after)             # 다시 찾기 중 mDNS 응답이 늦게 옴
                devs[same] = SimpleNamespace(friendly_name="시험 TV", model_name=None,
                                             host="10.0.0.9")
            done.wait(2.0)
            took = time.monotonic() - t0
        finally:
            cm._cast, cm._browser = None, None
            cm.shutdown(timeout=1.0)
        if appear_after is not None:
            return "ok" in res, f"{took:.2f}초 뒤 {'연결' if 'ok' in res else res}"
        return ("fail" in res and took >= 0.55), f"{took:.2f}초 뒤 {res}"

    saved = cm_mod.pychromecast.get_chromecast_from_cast_info
    cm_mod.pychromecast.get_chromecast_from_cast_info = fake_cast
    try:
        for name, appear in (("[연결]: 목록에 없던 기기가 대기 시간 안에 나타나면 연결", 0.3),
                             ("[연결]: 대기 시간까지 안 나타나면 그때 실패", None)):
            try:
                ok, detail = late_device(appear)
                check(name, ok, detail)
            except Exception as err:  # pylint: disable=broad-except
                check(name, False, f"예외: {err!r}")
        for name, target, keep, want in (
                ("포기 뒤 연결: 같은 기기(keep_lost) → 끊김 기억 유지", same, True, True),
                ("포기 뒤 연결: 다른 기기 → 끊김 기억 지움", other, False, False)):
            try:
                kept = run(target, keep)
                check(name, kept == want, f"기억 {'유지' if kept else '지워짐'}")
            except Exception as err:  # pylint: disable=broad-except
                check(name, False, f"예외: {err!r}")
    finally:
        cm_mod.pychromecast.get_chromecast_from_cast_info = saved


def _buffering_cases(check: Callable[[str, bool, str], None]) -> None:
    def ln(t: str, msg: str) -> str:
        return f"2026-01-01 {t},000 INFO core.x: {msg}"

    lines = [
        ln("10:00:00", "재생: REMUX @0.0 → http://10.0.0.2:8765/hls/x/master.m3u8"),
        ln("10:00:05", "재생 상태: PLAYING → BUFFERING, 3.0초"),     # 불러오기 뒤 5초 → 뺌
        ln("10:05:00", "재생 상태: PLAYING → BUFFERING, 290.0초"),   # 셈
        ln("10:06:00", "탐색: 1200.0초"),
        ln("10:06:09", "재생 상태: PLAYING → BUFFERING, 9.0초"),     # 탐색 뒤 9초 → 뺌
        ln("10:07:00", "자막 싱크 반영: 1250.0초에서 다시 불러옴"),
        ln("10:07:11", "재생 상태: PLAYING → BUFFERING, 11.0초"),    # 10초 넘음 → 셈
        ln("10:08:00", "재생 상태: BUFFERING → PLAYING, 0.5초"),     # 다른 전환 → 무시
        "깨진 줄",
    ]
    try:
        counted, excluded, span = count_buffering_lines(lines)
        ok = ([t[11:19] for t, _ in counted] == ["10:05:00", "10:07:11"]
              and [why for _, why in excluded] == ["재생:", "탐색:"]
              and span == 480.0)
        detail = f"셈 {len(counted)}회, 뺌 {len(excluded)}회, 구간 {span:.0f}초"
    except Exception as err:  # pylint: disable=broad-except
        ok, detail = False, f"예외: {err!r}"
    check("버퍼링 판정: 조작 뒤 10초 안은 빼고 셈", ok, detail)
    with tempfile.TemporaryDirectory() as tmp:
        for n in ("castplayer.1.log", "castplayer.log", "castplayer.txt"):
            Path(tmp, n).write_text("", encoding="utf-8")
        names = [Path(p).name for p in gui_log_paths(Path(tmp))]
    check("버퍼링 판정: 기본 입력은 castplayer*.log를 오래된 것부터",
          names == ["castplayer.1.log", "castplayer.log"], f"{names}")


def _paths_cases(check: Callable[[str, bool, str], None]) -> None:
    saved = (paths_mod.bin_dir, os.environ.get("PATH", ""))
    with tempfile.TemporaryDirectory() as tmp:
        bin_, other = Path(tmp, "bin"), Path(tmp, "other")
        bin_.mkdir()
        other.mkdir()
        paths_mod.bin_dir = lambda: bin_
        try:
            (other / "ffmpeg.exe").write_bytes(b"")
            os.environ["PATH"] = str(other)
            p = paths_mod.ffmpeg_path()
            check("ffmpeg 찾기: bin에 없으면 PATH", p.parent == other and p.is_file(), f"{p}")
            (bin_ / "ffmpeg.exe").write_bytes(b"")
            p = paths_mod.ffmpeg_path()
            check("ffmpeg 찾기: bin이 PATH보다 먼저", p.parent == bin_, f"{p}")
            os.environ["PATH"] = ""
            p = paths_mod.ffprobe_path()
            check("ffmpeg 찾기: 둘 다 없음 → 없는 경로", not p.is_file(), f"{p}")
        finally:
            paths_mod.bin_dir, os.environ["PATH"] = saved
    icon = paths_mod.asset_path("cast.ico")
    check("배포 파일: 아이콘 경로 (소스 실행)", icon.is_file(), f"{icon.relative_to(app_dir())}")


def _log_cases(check: Callable[[str, bool, str], None]) -> None:
    """PRD F7-5~F7-8 (D070): GUI 로그 파일. 루트 로거의 수준·핸들러는 끝나면 되돌린다."""
    root = logging.getLogger()
    level = root.level
    log = logging.getLogger("cast_test.gui_log")

    def run(tmp: Path, verbose: bool, on: bool) -> str | None:
        file_log, err = main_mod.setup_logging(verbose, on, tmp / "logs", console=False)
        log.debug("DEBUG 줄")
        log.info("새 줄")
        file_log.set(False)
        return err

    try:
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run(tmp, False, False)
            found = sorted(p.name for p in tmp.rglob("castplayer*"))
            check("F7-5 로그 기록 꺼짐 → castplayer*.log 없음", not found, f"{found}")
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / "logs").mkdir()
            (tmp / "logs" / "castplayer.log").write_text("지난 줄\n", encoding="utf-8")
            (tmp / "logs" / "castplayer.1.log").write_text("지난 줄\n", encoding="utf-8")
            run(tmp, False, True)
            text = (tmp / "logs" / "castplayer.log").read_text(encoding="utf-8")
            left = sorted(p.name for p in (tmp / "logs").iterdir())
            check("F7-6 로그 기록 켬 → 지난 로그 지우고 새로 씀",
                  "새 줄" in text and "지난 줄" not in text and "DEBUG 줄" not in text
                  and left == ["castplayer.log"], f"{left}")
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            run(tmp, True, False)
            path = tmp / "logs" / "castplayer.log"
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            check("F7-7 -v → 옵션이 꺼져 있어도 DEBUG 줄 기록", "DEBUG 줄" in text,
                  f"{len(text.splitlines())}줄")
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            (tmp / "logs").write_text("", encoding="utf-8")   # 폴더 자리에 파일 → 만들 수 없음
            err = run(tmp, False, True)
            check("F7-8 쓸 수 없으면 알림 문구",
                  bool(err) and str(err).startswith("로그 파일을 만들 수 없습니다"), f"{err}")
    except Exception as err:  # pylint: disable=broad-except
        check("GUI 로그 파일", False, f"예외: {err!r}")
    finally:
        root.setLevel(level)


def _plan_style_cases(check: Callable[[str, bool, str], None]) -> None:
    """PRD F2-6·F5-6 (D069): 지금 동작을 고정."""
    v = VideoStream(0, "mpeg4", "Advanced Simple Profile", 5, 3840, 2160, "yuv420p",
                    Fraction(60), "XVID")
    info = MediaInfo(Path("movie.avi"), "avi", 600.0, v, (), ())
    plan = planner_mod.make_plan(info)
    check("F2-6 4K 60fps XviD → TRANSCODE, 30fps",
          plan.mode is Mode.TRANSCODE and plan.fps_cap == 30, f"{plan.summary}")
    st = text_style(5.0)
    want = {"backgroundColor": "#FFFFFF00", "foregroundColor": "#FFFFFFFF",
            "edgeType": "OUTLINE", "edgeColor": "#000000FF"}
    check("F5-6 자막 스타일: 투명 배경·흰 글자·검은 테두리",
          all(st.get(k) == x for k, x in want.items()), f"{st}")
    check("F5-6 자막 크기 배율 0.5~2.0으로 맞춤",
          (text_style(5.0)["fontScale"], text_style(0.1)["fontScale"]) == (2.0, 0.5),
          f"5.0→{text_style(5.0)['fontScale']}, 0.1→{text_style(0.1)['fontScale']}")


# ===================== GUI 자가검사 (화면 없는 Qt, D071) =====================
GREEN, GRAY = mw_mod.ST_OK[1], mw_mod.ST_NONE[1]


class _GuiCM(_FakeCM):
    """_FakeCM + 창이 부르는 나머지 명령(start_discovery·pause·connect 등)을 기록만 한다."""

    def __init__(self) -> None:
        super().__init__()
        self.device = None
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name: str) -> Callable[..., None]:
        return lambda *a, **_k: self.calls.append((name, a))

    def stop(self, then: Callable[[], None] | None = None) -> None:
        self.calls.append(("stop", ()))
        super().stop(then)

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


def _dev(host: str = "10.0.0.9") -> DeviceInfo:
    return DeviceInfo(uuid=uuid4(), name="시험 TV", model="시험", host=host)


def _gui(loaded: bool = False, log_error: str | None = None, cfg: AppConfig | None = None,
         set_log: Callable[[bool], str | None] = lambda _on: None
         ) -> tuple[Any, _GuiCM, PlaybackController, CastBridge]:
    """가짜 TV 연결을 붙인 실제 메인 창. loaded면 파일을 열어 재생 중인 상태로 연결까지 한다."""
    cm, bridge = _GuiCM(), CastBridge()
    if loaded:
        cm.device = _dev()                     # 재생 요청에 기기 주소가 필요
        _cm, ctrl, _ = _fresh(cm, bridge.callbacks)
    else:
        ctrl = PlaybackController(cm, _FakeServer(), None, bridge.callbacks)
    cfg = cfg or AppConfig(auto_connect=False)
    cfg.save = lambda: None                    # config.json을 건드리지 않음
    w = mw_mod.MainWindow(cfg, cm, ctrl, bridge, set_log=set_log, log_error=log_error)
    w.show()
    w.activateWindow()
    QTest.qWaitForWindowActive(w)              # 단축키는 활성 창에서만 동작
    if loaded:
        w.seek.set_duration(ctrl.info.duration if ctrl.info else 0.0)   # _on_task_ok가 하는 일
        _connect(w, cm, bridge, cm.device)
    cm.calls.clear()
    return w, cm, ctrl, bridge


def _connect(w: Any, cm: _GuiCM, bridge: CastBridge, dev: DeviceInfo | None = None) -> None:
    cm.device = dev or _dev()
    bridge.connected.emit(cm.device)
    QApplication.processEvents()


def _close(w: Any) -> None:
    w.close()
    w.deleteLater()
    QApplication.processEvents()


def _conn_cases(check: Callable[[str, bool, str], None]) -> None:
    """PRD F7-8 표시·F1-1·F1-2·F1-3·F1-5 (D071): 지금 동작을 고정."""
    msg = "로그 파일을 만들 수 없습니다: logs\\castplayer.log (시험)"
    w, *_ = _gui(log_error=msg)
    check("F7-8 시작 때 상태줄에 로그 오류 알림", w.statusBar().currentMessage() == msg,
          w.statusBar().currentMessage())
    _close(w)

    w, *_ = _gui()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(Path(tempfile.gettempdir()) / "movie.mp4"))])
    ev = QDragEnterEvent(QPoint(1, 1), Qt.DropAction.CopyAction, mime,
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    w.dragEnterEvent(ev)
    check("F1-2 연결 전 끌어다 놓기 → 안 열리고 안내",
          not ev.isAccepted() and w.statusBar().currentMessage() == "먼저 기기를 연결하세요.",
          w.statusBar().currentMessage())
    _close(w)

    dev = _dev()
    cfg = AppConfig(last_device_uuid=str(dev.uuid), last_device_name=dev.name,
                    last_device_host=dev.host)
    w, cm, _ctrl, bridge = _gui(cfg=cfg)
    bridge.devices_changed.emit([dev])
    QApplication.processEvents()
    asked = ("connect", (dev.uuid,)) in cm.calls
    _connect(w, cm, bridge, dev)
    check("F1-1 저장된 기기가 보이면 자동 연결 → ● 초록",
          asked and GREEN in w.conn_label.text(), f"연결 요청 {asked}, {w.conn_label.text()}")
    _close(w)

    saved = mw_mod.AUTO_HOST_FALLBACK_MS
    mw_mod.AUTO_HOST_FALLBACK_MS = 20          # 8초 + 8초 → 시험에서는 줄임
    try:
        w, cm, _ctrl, _bridge = _gui(cfg=AppConfig(
            last_device_uuid=str(dev.uuid), last_device_name=dev.name, last_device_host=dev.host))
        QTest.qWait(150)
        text = w.statusBar().currentMessage()
        check("F1-3 저장된 기기를 못 찾음 → 안내, ● 회색",
              text == "시험 TV을(를) 찾지 못했습니다." and GRAY in w.conn_label.text()
              and ("add_known_host", (dev.host,)) in cm.calls, f"{text}, {cm.names()}")
        _close(w)
    finally:
        mw_mod.AUTO_HOST_FALLBACK_MS = saved

    saved_ask = mw_mod.ask_ip
    mw_mod.ask_ip = lambda _parent: "192.0.2.10"
    try:
        w, cm, _ctrl, bridge = _gui()
        w.acts.add_ip.trigger()
        dev = _dev("192.0.2.10")
        bridge.devices_changed.emit([dev])
        QApplication.processEvents()
        listed = w.dev_combo.findData(dev.uuid) >= 0
        w.btn_connect.click()
        check("F1-5 IP로 기기 추가 → 저장·검색, 목록에 나타나 연결",
              w.cfg.known_hosts == ["192.0.2.10"] and ("add_known_host", ("192.0.2.10",)) in cm.calls
              and listed and ("connect", (dev.uuid,)) in cm.calls,
              f"저장 {w.cfg.known_hosts}, 목록 {listed}, {cm.names()}")
        _close(w)
    finally:
        mw_mod.ask_ip = saved_ask


class _Grab(logging.Handler):
    """with 안에서 한 로거의 INFO 메시지를 모은다 (자가검사는 ERROR만 보이므로 잠시 낮춤)."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.log = logging.getLogger(name)
        self.saved = (self.log.level, self.log.propagate)

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())

    def __enter__(self) -> list[str]:
        self.log.addHandler(self)
        self.log.setLevel(logging.INFO)
        self.log.propagate = False
        return self.lines

    def __exit__(self, *_exc: object) -> None:
        self.log.removeHandler(self)
        self.log.level, self.log.propagate = self.saved


def _key(w: Any, *keys: Qt.Key) -> None:
    for k in keys:
        QTest.keyClick(w, k)
    QApplication.processEvents()


def _wait_for(cond: Callable[[], bool], sec: float = 3.0) -> bool:
    """Qt 이벤트를 돌리며 cond가 참이 될 때까지 (PySide6에는 QTest.qWaitFor가 없음)."""
    end = time.monotonic() + sec
    while not cond() and time.monotonic() < end:
        QTest.qWait(20)
    return cond()


def _seeks(lines: list[str]) -> list[str]:
    return [x for x in lines if x.startswith("탐색:")]


def _play_cases(check: Callable[[str, bool, str], None]) -> None:
    """PRD F3-1·F3-2·F3-4·F3-5·F2-5와 pyright 정리 뒤 확인 대기 항목 (D071): 지금 동작을 고정."""
    K = Qt.Key
    wait = mw_mod.SEEK_COALESCE_MS + 150

    def status(state: str, pos: float) -> None:
        bridge.media_status.emit(PlaybackState(state, pos, 6000.0, None))

    w, cm, ctrl, bridge = _gui(loaded=True)
    status("PLAYING", 100.0)
    _key(w, K.Key_Space)
    status("PAUSED", 100.0)
    _key(w, K.Key_Space)
    check("F3-1 Space → 일시정지, 다시 Space → 재생", cm.names() == ["pause", "resume"],
          f"{cm.names()}")

    status("PLAYING", 100.0)
    cm.pos = 100.0
    with _Grab("core.player") as lines:
        _key(w, K.Key_Right, K.Key_Right, K.Key_Right)
        QTest.qWait(wait)
    check("F3-2 → 3번(0.3초 안) → 탐색 1번 +15초, 로그 `탐색:` 1줄",
          _seeks(lines) == ["탐색: 115.0초"], f"{lines}")
    cm.pos = 100.0
    with _Grab("core.player") as lines:
        _key(w, K.Key_Left)
        QTest.qWait(wait)
    check("← → 5초 뒤로 탐색", _seeks(lines) == ["탐색: 95.0초"], f"{lines}")

    cm.calls.clear()
    _key(w, K.Key_Up)
    up = w.vol.value()
    _key(w, K.Key_Down)
    check("↑/↓ → 볼륨 ±5%", up == 55 and cm.calls == [("set_volume", (0.55,)),
                                                      ("set_volume", (0.5,))], f"{cm.calls}")
    cm.calls.clear()
    _key(w, K.Key_M)
    check("M → 음소거", cm.calls == [("set_muted", (True,))] and w.btn_mute.isChecked(),
          f"{cm.calls}")

    cm.pos = 321.0
    QTest.qWait(700)
    check("재생 중 0.5초마다 위치 표시 갱신", w.pos_label.text() == "05:21", w.pos_label.text())

    with _Grab("core.player") as lines:
        w.seek.setSliderDown(True)
        w.seek.setSliderPosition(200 * w.seek.SCALE)
        dragging = w.pos_label.text()
        w.seek.setSliderDown(False)
        QApplication.processEvents()
    check("탐색 바 끌어 놓기 → 그 위치로 탐색 1번",
          _seeks(lines) == ["탐색: 200.0초"] and dragging == "03:20", f"끄는 중 {dragging}, {lines}")
    with _Grab("core.player") as lines:
        QTest.mouseClick(w.seek, Qt.MouseButton.LeftButton, pos=QPoint(w.seek.width() * 3 // 4,
                                                                      w.seek.height() // 2))
    sec = float(_seeks(lines)[0][4:-1]) if len(_seeks(lines)) == 1 else -1.0
    check("탐색 바 클릭 → 그 자리로 바로 탐색", 3000.0 < sec < 6000.0, f"{lines}")

    step = player_mod._stage(w.tasks.report, "키프레임 분석")   # pylint: disable=protected-access
    assert step is not None
    step(40)
    QApplication.processEvents()
    check("상태줄 \"키프레임 분석 N%\"", w.statusBar().currentMessage() == "키프레임 분석 40%…",
          w.statusBar().currentMessage())

    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "other.mp4"
        path.write_bytes(b"")
        asked: list[str] = []
        saved = mw_mod.confirm
        mw_mod.confirm = lambda _parent, text: asked.append(text) or False   # 취소
        try:
            cm.calls.clear()
            w._open(path)   # pylint: disable=protected-access
        finally:
            mw_mod.confirm = saved
    check("F2-5 재생 중 새 파일 → 확인 창, 취소하면 그대로",
          len(asked) == 1 and ctrl.active and "stop" not in cm.names()
          and w.file_label.text() == "파일: -" and w.tasks.busy is None,
          f"확인 {len(asked)}번, {cm.names()}, {w.file_label.text()}")

    _key(w, K.Key_S)
    check("S → 정지", "stop" in cm.names() and not ctrl.active
          and w.statusBar().currentMessage() == "정지 (TV 플레이어 종료)", f"{cm.names()}")
    _close(w)

    w, cm, ctrl, bridge = _gui(loaded=True)
    status("PLAYING", 5990.0)
    finished = bridge.callbacks.on_finished      # 수신기 IDLE/FINISHED → ctrl 정리 → 창
    assert finished is not None
    finished()
    QApplication.processEvents()
    ended = w.statusBar().currentMessage()
    w.btn_play.click()
    starts = [_start(r) for r in cm.loads]
    check("재생 완료 뒤 재생 버튼 → 처음부터 다시 불러옴",
          ended == "재생 완료" and starts == [0.0], f"{ended}, {_desc(cm)}")
    _close(w)

    w, cm, ctrl, bridge = _gui()
    _connect(w, cm, bridge)
    bridge.volume.emit(0.37, False)
    QApplication.processEvents()
    check("F3-4 연결 때 볼륨 명령 없음, 슬라이더가 TV 볼륨을 따름",
          w.vol.value() == 37 and "set_volume" not in cm.names(), f"{w.vol.value()}, {cm.names()}")
    _key(w, K.Key_S)
    check("F3-5 파일을 열지 않은 연결 → 정지 버튼 비활성, S → 정지 명령 없음",
          not w.btn_stop.isEnabled() and "stop" not in cm.names(), f"{cm.names()}")
    _close(w)


class _FakeSession:
    """HlsSession 대역: ffmpeg를 띄우지 않고 시작 위치·닫힘만 기록."""

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.closed = False

    def get(self, _name: str) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _media_cases(check: Callable[[str, bool, str], None]) -> None:
    """PRD F5-2·F5-3·F4-1 (D071): 지금 동작을 고정."""
    w, cm, ctrl, _bridge = _gui(loaded=True)
    ctrl.info = SimpleNamespace(path=Path("selftest.mkv"), duration=6000.0, audio=())
    ctrl.subs = SubtitleSet([
        SubtitleTrack("ext:selftest.srt", "selftest.srt", "ko", True, (Cue(1.0, 2.0, "시험"),),
                      track_id=1, external=True),
        SubtitleTrack("emb:3", "#1 PGS", "ko", False, note="지원 안 함")])
    ctrl._sub_id = 1   # pylint: disable=protected-access
    w._fill_tracks()   # pylint: disable=protected-access
    w._update_ui()     # pylint: disable=protected-access
    model = w.sub_combo.model()
    check("F5-2 이미지 자막(PGS) → 목록에 회색 \"지원 안 함\"",
          w.sub_combo.count() == 3 and not model.item(2).isEnabled() and model.item(1).isEnabled()
          and "지원 안 함" in w.sub_combo.itemText(2),
          f"{[w.sub_combo.itemText(i) for i in range(w.sub_combo.count())]}")

    cm.pos = 300.0
    with _Grab("core.player") as lines:
        for _ in range(3):
            w.btn_sync_up.click()
        QTest.qWait(1000)
        early = len(cm.loads)
        QTest.qWait(800)                       # 마지막 입력 1.5초 뒤
    synced = [x for x in lines if x.startswith("자막 싱크 반영")]
    check("F5-3 싱크 +0.5 3번 → 1.5초 뒤 한 번만 +1.5초로 다시 불러옴, 로그 1줄",
          early == 0 and len(cm.loads) == 1 and _start(cm.loads[0]) == 300.0 and len(synced) == 1
          and ctrl.subs.delay(1) == 1.5 and w.sync_label.text() == "+1.5초",
          f"1초 때 {early}번, {_desc(cm)}, {w.sync_label.text()}, {synced}")
    _close(w)

    v = VideoStream(0, "h264", "High", 41, 1920, 1080, "yuv420p", Fraction(24), "avc1")
    audio = tuple(AudioStream(i + 1, i, "aac", 2, lang, "", i == 0)
                  for i, lang in enumerate(("ko", "en")))
    info = MediaInfo(Path("selftest.mp4"), "mov,mp4,m4a,3gp,3g2,mj2", 6000.0, v, audio, ())
    saved = (player_mod.make_plan, player_mod.HlsSession)
    player_mod.make_plan, player_mod.HlsSession = planner_mod.make_plan, _FakeSession
    try:
        w, cm, ctrl, _bridge = _gui(loaded=True)
        ctrl.info, ctrl.plan = info, planner_mod.make_plan(info, 0)
        ctrl.timeline = player_mod.fixed_timeline(info.duration)   # 키프레임 분석 건너뜀
        ctrl.subs, ctrl._sub_id = None, None   # pylint: disable=protected-access
        w._fill_tracks()   # pylint: disable=protected-access
        before = ctrl.plan.mode
        cm.pos = 1234.0
        w.audio_combo.setCurrentIndex(1)
        w.audio_combo.activated.emit(1)
        # busy가 풀린 뒤에 완료 신호가 UI 스레드에 도착하므로 알림까지 기다림
        _wait_for(lambda: w.statusBar().currentMessage() != "")
        r = cm.loads[-1] if cm.loads else None
        check("F4-1 음성 2개 mp4를 1번으로 재생 중 2번 → 현재 위치에서 REMUX로 다시 불러옴",
              before is Mode.DIRECT and ctrl.plan is not None and ctrl.plan.mode is Mode.REMUX
              and len(cm.loads) == 1 and r is not None and _start(r) == 1234.0
              and r.url.endswith("/master.m3u8")
              and w.statusBar().currentMessage() == "음성 트랙을 바꿨습니다.",
              f"{before.value} → {ctrl.plan.mode.value if ctrl.plan else '-'}, {_desc(cm)}, "
              f"{w.statusBar().currentMessage()}")
        _close(w)
    finally:
        player_mod.make_plan, player_mod.HlsSession = saved


def _lost_cases(check: Callable[[str, bool, str], None]) -> None:
    """PRD F6-1·F6-2·F6-4 창 경로 (D071): 지금 동작을 고정."""
    w, cm, ctrl, bridge = _gui(loaded=True)
    dev = cm.device
    bridge.media_status.emit(PlaybackState("PLAYING", 1000.0, 6000.0, None))
    cm.drop(1000.0, False)
    bridge.connection_lost.emit(dev)           # pychromecast가 스스로 다시 붙는 끊김
    QApplication.processEvents()
    lost = mw_mod.ST_LOST[1] in w.conn_label.text()
    _connect(w, cm, bridge, dev)
    cm.answer(False)                           # 수신기 세션 없음
    r = cm.loads[-1] if cm.loads else None
    check("F6-1 재생 중 끊겼다 다시 연결 → 끊긴 위치·재생 상태로 다시 불러옴",
          lost and len(cm.loads) == 1 and r is not None and _start(r) == 1000.0 and r.autoplay
          and w.statusBar().currentMessage() == "다시 연결됨. 끊긴 위치부터 이어 갑니다.",
          f"끊김 표시 {lost}, {_desc(cm)}, {w.statusBar().currentMessage()}")
    _close(w)

    w, cm, ctrl, bridge = _gui(loaded=True)
    dev = cm.device
    w.cfg.last_device_uuid = str(dev.uuid)
    bridge.media_status.emit(PlaybackState("PAUSED", 500.0, 6000.0, None))
    cm.drop(500.0, True)
    bridge.connection_lost.emit(dev)
    cm.device = None
    bridge.disconnected.emit()                 # 다시 붙지 못해 연결 해제됨 → 창이 다시 찾음
    bridge.devices_changed.emit([dev])
    QApplication.processEvents()
    asked = ("connect", (dev.uuid,)) in cm.calls and ctrl.active
    _connect(w, cm, bridge, dev)
    cm.answer(False)
    r = cm.loads[-1] if cm.loads else None
    check("F6-2 일시정지 중 끊김 → 목록에 다시 나타나면 연결, 일시정지로 다시 불러옴",
          asked and len(cm.loads) == 1 and r is not None and _start(r) == 500.0 and not r.autoplay,
          f"송출 유지·연결 요청 {asked}, {_desc(cm)}")
    _close(w)

    saved = mw_mod.RECONNECT_WINDOW
    mw_mod.RECONNECT_WINDOW = 0.05             # 30초 → 시험에서는 줄임
    try:
        w, cm, ctrl, bridge = _gui(loaded=True)
        route = ctrl._route   # pylint: disable=protected-access
        cm.device = None
        bridge.disconnected.emit()
        QTest.qWait(250)
        text = w.statusBar().currentMessage()
        check("F6-4 재연결 시간이 지나면 안내 뒤 송출 정리",
              text == "기기에 다시 연결하지 못했습니다. [연결]을 눌러 주세요." and not ctrl.active
              and route in ctrl.server.unregistered and GRAY in w.conn_label.text(),
              f"{text}, 송출 {'유지' if ctrl.active else '정리'}")
        _close(w)
    finally:
        mw_mod.RECONNECT_WINDOW = saved


def _log_slow_close_cases(check: Callable[[str, bool, str], None]) -> None:
    """PRD F7-9·F7-4·F3-6 (D071): 지금 동작을 고정."""
    root = logging.getLogger()
    level = root.level
    try:
        with tempfile.TemporaryDirectory() as t:
            logs = Path(t) / "logs"
            file_log, _err = main_mod.setup_logging(False, False, logs, console=False)
            w, *_ = _gui(set_log=file_log.set)
            before = (logs / "castplayer.log").exists()
            w.acts.log_file.trigger()          # 옵션 메뉴 "로그 기록" 켬
            logging.getLogger("cast_test.gui_log").info("켠 뒤 줄")
            file_log.set(False)
            path = logs / "castplayer.log"
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            check("F7-9 실행 중 \"로그 기록\"을 켜면 다시 시작하지 않아도 INFO 줄 기록",
                  not before and "켠 뒤 줄" in text and w.cfg.log_file
                  and w.statusBar().currentMessage() == "로그 기록 켬",
                  f"켜기 전 파일 {before}, {len(text.splitlines())}줄")
            _close(w)
    finally:
        root.setLevel(level)

    server = MediaServer(port=0, bind="127.0.0.1")
    saved = ms_mod.SLOW_SEND
    try:
        server.start()
        httpd = server._httpd                  # pylint: disable=protected-access
        assert httpd is not None
        server.port = httpd.server_address[1]  # 0번으로 열어 빈 포트를 받음
        route = server.register(HlsResource(lambda name: (b"x" * 1000, "video/mp4")), prefix="hls")
        url = server.url_for(route, "127.0.0.1")
        result = []
        for slow in (0.0, 5.0):               # 0초 기준이면 어떤 조각도 느림
            ms_mod.SLOW_SEND = slow
            with _Grab("core.media_server") as lines:
                for name in ("seg_1.m4s", "master.m3u8"):
                    with urllib.request.urlopen(f"{url}/{name}", timeout=5) as resp:
                        resp.read()
                _wait_for(lambda: any(x.startswith("전송:") for x in lines), 1.0)
            result.append([x for x in lines if "← 느림" in x])
        check("F7-4 조각 전송이 기준 시간을 넘으면 \"← 느림\" 줄 (조각만, 넘지 않으면 없음)",
              len(result[0]) == 1 and "seg_1.m4s" in result[0][0] and not result[1], f"{result}")
    finally:
        ms_mod.SLOW_SEND = saved
        server.stop()

    gcm = _GuiCM()
    gcm.device = _dev()
    cm, ctrl, srv = _fresh(gcm)
    session, route = _FakeSession(), ctrl._route   # pylint: disable=protected-access
    ctrl._session = session                        # pylint: disable=protected-access
    stopped: list[bool] = []
    main_mod.cleanup(cm, ctrl, SimpleNamespace(stop=lambda: stopped.append(True)))
    check("F3-6 창을 닫은 뒤 정리 → 수신 앱 종료·HLS 세션 닫기·경로 해제·서버 종료",
          cm.names() == ["shutdown"] and session.closed and route in srv.unregistered
          and not ctrl.active and stopped == [True],
          f"{cm.names()}, 세션 {'닫힘' if session.closed else '열림'}, 서버 {stopped}")


def _gui_cases(check: Callable[[str, bool, str], None]) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # 창을 화면에 띄우지 않음
    _app = QApplication.instance() or QApplication([])
    for fn in (_conn_cases, _play_cases, _media_cases, _lost_cases, _log_slow_close_cases):
        try:
            fn(check)
        except Exception as err:  # pylint: disable=broad-except
            check(f"GUI {fn.__name__}", False, f"예외: {err!r}")


def selftest() -> int:
    oks: list[bool] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        oks.append(bool(ok))
        print(f"  [{'통과' if ok else '실패'}] {name}" + (f" — {detail}" if detail else ""))

    saved = (player_mod.local_ip_for, player_mod.make_plan)
    player_mod.local_ip_for = lambda _host: "10.0.0.2"
    player_mod.make_plan = lambda _info, order: _fake_plan(order or 0)
    try:
        print("[자가검사] player.py — 끊김·복구 순서")
        for name, fn in _PLAYER_CASES:
            try:
                ok, detail = fn()
            except Exception as err:  # pylint: disable=broad-except
                ok, detail = False, f"예외: {err!r}"
            check(name, ok, detail)
        print("[자가검사] cast_manager.py — 세션 판정·끊긴 위치 기록")
        _manager_cases(check)
        print("[자가검사] cast_manager.py — 마지막 IP로 다시 연결 (90초)")
        _reconnect_cases(check)
        _keep_lost_cases(check)
        print("[자가검사] --count-buffering — 버퍼링 횟수 판정 (D050)")
        _buffering_cases(check)
        print("[자가검사] paths.py — ffmpeg·ffprobe 찾기 (bin → PATH)")
        _paths_cases(check)
        print("[자가검사] planner.py·subtitles.py — 4K fps 절반, 자막 스타일 (D069)")
        _plan_style_cases(check)
        print("[자가검사] main.py — GUI 로그 기록 옵션 (D070)")
        _log_cases(check)
        print("[자가검사] main_window.py — 화면 없는 창 + 가짜 TV (D071)")
        _gui_cases(check)
    finally:
        player_mod.local_ip_for, player_mod.make_plan = saved
    print(f"[자가검사] {len(oks)}개 중 {sum(oks)}개 통과")
    return 0 if all(oks) else 1


# ===================== 버퍼링 판정 (D050) =====================
BUFFER_EVENT = "재생 상태: PLAYING → BUFFERING"
BUFFER_GRACE = 10.0     # 이 조작들 뒤 이 시간(초) 안의 버퍼링은 세지 않음
BUFFER_TRIGGERS = ("재생:", "탐색:", "음성 변경:", "자막 싱크 반영:")


def count_buffering_lines(lines) -> tuple[list[tuple[str, str]], list[tuple[str, str]], float]:
    """GUI 로그 줄 → (센 것 [(시각, 줄)], 뺀 것 [(시각, 조작)], 첫 줄~끝 줄 초)."""
    counted: list[tuple[str, str]] = []
    excluded: list[tuple[str, str]] = []
    first = last = None
    op: tuple[datetime, str] | None = None
    for line in lines:
        try:
            t = datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
        except ValueError:
            continue                          # 여러 줄 traceback 등
        first, last = first or t, t
        msg = line.split(": ", 1)[1] if ": " in line[24:] else ""
        trig = next((p for p in BUFFER_TRIGGERS if msg.startswith(p)), None)
        if trig:
            op = (t, trig)
        elif msg.startswith(BUFFER_EVENT):
            if op and (t - op[0]).total_seconds() <= BUFFER_GRACE:
                excluded.append((line[:23], op[1]))
            else:
                counted.append((line[:23], msg))
    span = (last - first).total_seconds() if first and last else 0.0
    return counted, excluded, span


def gui_log_paths(logs: Path) -> list[str]:
    """회전된 GUI 로그를 오래된 것부터 (castplayer.3.log … castplayer.log)."""
    return [str(p) for p in (logs / f"castplayer.{n}.log" for n in (3, 2, 1))
            if p.is_file()] + [str(logs / "castplayer.log")]


def count_buffering(paths: list[str]) -> int:
    if not paths:
        paths = gui_log_paths(app_dir() / "logs")
    lines: list[str] = []
    for p in paths:
        lines += Path(p).read_text(encoding="utf-8", errors="replace").splitlines()
    counted, excluded, span = count_buffering_lines(lines)
    print("로그:", ", ".join(Path(p).name for p in paths))
    print(f"구간: {span / 60:.1f}분")
    for t, why in excluded:
        print(f"  뺌  {t}  ({why} 뒤 {BUFFER_GRACE:.0f}초 안)")
    for t, msg in counted:
        print(f"  셈  {t}  {msg}")
    print(f"버퍼링 {len(counted)}회 (뺀 것 {len(excluded)}회)")
    return 0


# ===================== 실행 =====================
def main() -> int:   # 인자 해석·로그 준비만 하고 본 실행은 run()
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--host", action="append", default=[], help="크롬캐스트 IP(반복 가능)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--audio", type=int, help="음성 트랙 번호(1부터)")
    ap.add_argument("--sub", type=int, help="자막 번호(1부터, 0=끄기). 없으면 자동 선택")
    ap.add_argument("--start", type=float, default=0.0, help="시작 위치(초)")
    ap.add_argument("--selftest", action="store_true", help="TV 없이 끊김·복구 자가검사")
    ap.add_argument("--droptest", action="store_true", help="실기기 연결 끊김 시험 (3장면 자동)")
    ap.add_argument("--count-buffering", nargs="*", metavar="로그",
                    help="GUI 로그에서 PLAYING→BUFFERING 횟수 판정 (D050). "
                         "생략 시 logs/castplayer*.log")
    ap.add_argument("--log", nargs="?", const="", metavar="파일",
                    help="화면 출력·로그·입력 명령을 UTF-8 파일에도 기록 (이어 쓰기). "
                         "파일 생략 시 logs/cast_test_날짜_시각.log, "
                         "확장자 생략 시 .log")
    ap.add_argument("-v", "--verbose", action="count", default=0,
                    help="-v=DEBUG(압축)  -vv=DEBUG 원본 전부")
    args = ap.parse_args()

    sink = open_log(args.log) if args.log is not None else None
    setup_logging(args.verbose, args.selftest, sink)    # 화면 핸들러가 원래 stderr를 잡은 뒤에
    if sink:
        sys.stdout = _Tee(sys.stdout, sink)             # type: ignore[assignment]
        sys.stderr = _Tee(sys.stderr, sink)             # traceback도 파일로
        print("로그 파일:", sink.path)
    code: int | str = "예외"
    try:
        code = run(args, ap)
        return code
    finally:
        if sink:
            sys.stdout.flush()
            sink.raw(f"===== 종료 {datetime.now():%Y-%m-%d %H:%M:%S} (코드 {code}) =====")


def run(args: argparse.Namespace, ap: argparse.ArgumentParser) -> int:
    if args.selftest:
        return selftest()
    if args.count_buffering is not None:
        return count_buffering(args.count_buffering)
    if not args.file:
        ap.error("파일을 지정하세요 (또는 --selftest)")

    for p in (ffmpeg_path(), ffprobe_path()):
        if not p.is_file():
            print("파일 없음:", p)
            return 2
    path = clean_path(args.file).resolve()
    if not path.is_file():
        print("파일이 없습니다:", path)
        return 2

    detector = EncoderDetector(ffmpeg_path())
    detector.start()

    found, connected = threading.Event(), threading.Event()
    mon, ui = Monitor(), UiQueue()
    flags = {"lost": False, "closing": False}
    ctrl: PlaybackController | None = None

    def on_status(s) -> None:
        dur = f"{s.duration:.3f}" if s.duration else "?"
        print(f"[상태] {s.player_state} {s.position:.1f}/{dur} {s.idle_reason or ''}")
        mon.add("state", s.player_state)

    def on_connected(d) -> None:
        print(f"[연결] {d.name} ({d.host})")
        connected.set()
        if flags["lost"]:                 # GUI _on_connected: 끊긴 기기에 다시 연결됨
            flags["lost"] = False
            mon.add("reconnected")
            assert ctrl is not None
            ui.post(ctrl.recover)

    def on_lost(d) -> None:
        print(f"[연결 끊김] {d.name} — pychromecast가 다시 연결을 시도합니다")
        flags["lost"] = True
        mon.add("lost")

        def job() -> None:                # GUI _on_lost
            assert ctrl is not None
            ctrl.mark_lost()
            mon.add("marked")
            hook, mon.lost_hook = mon.lost_hook, None
            if hook:
                hook()
        ui.post(job)

    def on_disconnected() -> None:
        print("[연결 해제]")
        if flags["lost"] and not flags["closing"]:
            print("[재연결 포기] 송출을 정리합니다 (GUI는 30초 동안 다시 찾아 이어 갑니다)")
            assert ctrl is not None
            ui.post(ctrl.shutdown)

    def on_load_failed(c, n) -> None:
        print(f"[로드 실패] {c} {n}")
        mon.add("load_failed", f"{c} {n}")

    def on_error(m) -> None:
        print("[오류]", m)
        mon.add("error", m)

    cb = CastCallbacks(
        on_devices_changed=lambda d: found.set() if d else None,
        on_connected=on_connected,
        on_connection_failed=lambda m: print("[연결 실패]", m),
        on_disconnected=on_disconnected,
        on_volume=lambda v, m: print(f"[볼륨] {v:.2f}{' (음소거)' if m else ''}"),
        on_media_status=on_status,
        on_finished=lambda: print("[재생 완료] (연속재생 훅)"),
        on_load_failed=on_load_failed,
        on_app_closed=lambda: print("[수신 앱 종료됨]"),
        on_error=on_error,
        on_connection_lost=on_lost,
    )

    cfg = AppConfig.load()   # 자막 크기만 사용
    server = MediaServer(port=args.port)
    server.start()
    cm = CastManager(cb, known_hosts=args.host)
    ctrl = PlaybackController(cm, server, detector, cb, subtitle_scale=cfg.subtitle_scale)
    instrument(cm, mon)
    try:
        audio = args.audio - 1 if args.audio else None
        info = ctrl.load(PlaylistItem(path, audio_stream=audio), on_progress=progress)
        if args.sub is not None:
            try:
                ctrl.select_subtitle(args.sub)
            except PlanError as err:
                print("[자막 선택 실패]", err)
        print_info(info)
        print_subs(ctrl)
        if audio is None and len(info.audio) > 1 and not args.droptest:
            sel = ask("음성 트랙 번호 [기본]: ").strip()
            if sel:
                ctrl.set_audio(int(sel) - 1, on_progress=progress)
        print_plan(ctrl)

        cm.start_discovery()
        print("기기 검색 중... (최대 10초)")
        found.wait(10)
        time.sleep(1.0)  # 다른 기기도 잡히도록 잠시 대기
        devs = cm.devices()
        if not devs:
            print("기기를 찾지 못했습니다. --host <IP> 로 지정해 보세요.")
            return 1
        for i, d in enumerate(devs):
            print(f"  [{i}] {d.name} ({d.model}, {d.host})")
        idx = int(ask("기기 번호 [0]: ") or 0) if len(devs) > 1 else 0
        cm.connect(devs[idx].uuid)
        if not connected.wait(20):
            print("연결 시간 초과")
            return 1

        ctrl.play(args.start)
        if args.droptest:
            print("[끊김 시험] 3장면을 자동으로 진행합니다 (약 3~5분). 화면을 지켜보실 필요는 없습니다.")
            return 0 if droptest(cm, ctrl, mon) else 1

        print(HELP)
        while True:
            cmd, arg = parse_cmd(ask("> "))
            if cmd is None:
                continue
            try:
                if cmd == "p":
                    cm.pause()
                elif cmd == "r":
                    cm.resume()
                elif cmd == "s":
                    ctrl.stop()
                elif cmd == "o":
                    ctrl.play(0.0)
                elif cmd == "g" and arg:
                    ctrl.seek(float(arg))
                elif cmd == "a" and arg:
                    ctrl.set_audio(int(arg) - 1, on_progress=progress)
                    print_plan(ctrl)
                elif cmd == "t":
                    print_info(info)
                    print_subs(ctrl)
                elif cmd == "c" and arg:
                    t = ctrl.select_subtitle(int(arg))
                    print("[자막]", t.display if t else "끔")
                elif cmd == "y" and arg:
                    d = ctrl.adjust_subtitle_delay(float(arg))
                    print(f"[자막 싱크] {d:+.2f}초 (+는 늦춤)")
                elif cmd == "z" and arg:
                    print(f"[자막 크기] {ctrl.set_subtitle_scale(float(arg)):.2f}")
                elif cmd == "v" and arg:
                    cm.set_volume(float(arg))
                elif cmd == "m" and arg in ("on", "off"):
                    cm.set_muted(arg == "on")
                elif cmd == "i":
                    print(f"위치: {cm.position():.1f}초")
                elif cmd == "x":
                    err = drop_connection(cm)
                    print("[끊김 시험]", err or "연결을 끊었습니다. pychromecast가 다시 연결합니다.")
                elif cmd == "q":
                    break
                else:
                    print(HELP)
            except (ValueError, PlanError) as err:
                print("[입력 오류]", err)
    except (ProbeError, PlanError) as err:
        print("[분석 실패]", err)
        return 1
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        flags["closing"] = True
        print("종료 처리 중... (정지 → 수신 앱 종료 → ffmpeg 정리 → 연결 해제)")
        cm.shutdown()
        ctrl.shutdown()
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
