"""크롬캐스트용 경량 HTTP 서버.

- FileResource  : 로컬 파일, Range(206) 지원 → 크롬캐스트 자체 seek 가능
- BytesResource : 메모리 데이터 (WebVTT 자막 등)
- StreamResource: 길이 미정 실시간 스트림 (사용처 없음)
- HlsResource   : /hls/<token>/<name> 하위 요청 처리 (HLS VOD)
모든 응답에 CORS 헤더 포함 (자막 요구사항).
"""
from __future__ import annotations

import logging
import os
import re
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import BinaryIO, Callable
from urllib.parse import parse_qs, urlsplit

_LOGGER = logging.getLogger(__name__)

CHUNK = 256 * 1024
SLOW_SEND = 5.0   # 조각 전송이 이 시간(초) 이상 걸리면 -v 없이도 기록
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


@dataclass(frozen=True)
class FileResource:
    path: Path
    mime: str


@dataclass(frozen=True)
class BytesResource:
    data: bytes
    mime: str


@dataclass(frozen=True)
class StreamResource:
    """open_stream(query) -> read()/close()를 가진 바이너리 스트림."""
    open_stream: Callable[[dict[str, str]], BinaryIO]
    mime: str


@dataclass(frozen=True)
class HlsResource:
    """경로 아래 이름(master.m3u8, seg_3.m4s 등)을 get(name)으로 처리.
    get은 (data, mime) 또는 None(404)을 반환하며, 조각 생성을 기다리느라 블로킹될 수 있음."""
    get: Callable[[str], tuple[bytes, str] | None]


Resource = FileResource | BytesResource | StreamResource | HlsResource


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows의 SO_REUSEADDR는 포트 중복 바인딩을 허용하므로 끈다.
    allow_reuse_address = os.name != "nt"

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], _CLIENT_GONE):
            return  # 크롬캐스트가 seek 등으로 연결을 끊는 것은 정상
        super().handle_error(request, client_address)


def _parse_range(header: str, size: int) -> tuple[int, int] | None | bool:
    """(start, end) | None(만족 불가→416) | False(형식 불일치→Range 무시)."""
    m = _RANGE_RE.match(header.strip())
    if not m:
        return False
    s, e = m.groups()
    if size == 0 or (s == "" and e == ""):
        return None
    if s == "":  # suffix: bytes=-N
        n = int(e)
        return None if n == 0 else (max(0, size - n), size - 1)
    start = int(s)
    if start >= size:
        return None
    end = size - 1 if e == "" else min(int(e), size - 1)
    return None if end < start else (start, end)


class MediaServer:
    def __init__(self, port: int, bind: str = "0.0.0.0") -> None:
        self.port = port
        self._bind = bind
        self._resources: dict[str, Resource] = {}
        self._lock = threading.Lock()
        self._httpd: _Server | None = None
        self._thread: threading.Thread | None = None

    # ---- 수명 ----
    def start(self) -> None:
        if self._httpd:
            return
        try:
            self._httpd = _Server((self._bind, self.port), _make_handler(self))
        except OSError as err:
            raise RuntimeError(f"포트 {self.port}를 열 수 없습니다: {err}") from err
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.5},
            name="media-server", daemon=True,
        )
        self._thread.start()
        _LOGGER.info("미디어 서버 시작 :%d", self.port)

    def stop(self) -> None:
        if not self._httpd:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
        self.clear()
        _LOGGER.info("미디어 서버 종료")

    # ---- 리소스 등록 ----
    def register(self, resource: Resource, prefix: str = "media") -> str:
        route = f"/{prefix}/{secrets.token_urlsafe(16)}"
        with self._lock:
            self._resources[route] = resource
        return route

    def unregister(self, route: str) -> None:
        with self._lock:
            self._resources.pop(route, None)

    def clear(self) -> None:
        with self._lock:
            self._resources.clear()

    def lookup(self, route: str) -> Resource | None:
        with self._lock:
            return self._resources.get(route)

    def url_for(self, route: str, host_ip: str) -> str:
        return f"http://{host_ip}:{self.port}{route}"


def _make_handler(server: MediaServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "CastPlayer/0.1"

        def log_message(self, fmt, *args):
            _LOGGER.debug("%s %s", self.address_string(), fmt % args)

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
            self.send_header("Access-Control-Expose-Headers",
                             "Content-Length, Content-Range, Accept-Ranges")

        def _empty(self, code: int, extra: dict[str, str] | None = None) -> None:
            self.send_response(code)
            self._cors()
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_OPTIONS(self):
            self._empty(204)

        def do_HEAD(self):
            self._handle(head=True)

        def do_GET(self):
            self._handle(head=False)

        def _handle(self, head: bool) -> None:
            parts = urlsplit(self.path)
            res = server.lookup(parts.path)
            sub = ""
            if res is None:  # HLS: /hls/<token>/<name>
                parent, _, sub = parts.path.rpartition("/")
                res = server.lookup(parent)
                if not isinstance(res, HlsResource):
                    res = None
            if res is None:
                self._empty(404)
                return
            try:
                if isinstance(res, FileResource):
                    self._serve_file(res, head)
                elif isinstance(res, BytesResource):
                    self._serve_bytes(res, head)
                elif isinstance(res, HlsResource):
                    self._serve_hls(res, sub, head)
                else:
                    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
                    self._serve_stream(res, head, query)
            except _CLIENT_GONE:
                _LOGGER.debug("클라이언트 연결 종료: %s", parts.path)
                self.close_connection = True

        def _serve_file(self, res: FileResource, head: bool) -> None:
            try:
                f = open(res.path, "rb")
            except OSError:
                self._empty(404)
                return
            with f:
                size = os.fstat(f.fileno()).st_size
                start, end, status = 0, size - 1, 200
                header = self.headers.get("Range")
                if header:
                    parsed = _parse_range(header, size)
                    if parsed is None:
                        self._empty(416, {"Content-Range": f"bytes */{size}"})
                        return
                    if parsed is not False:
                        start, end = parsed
                        status = 206
                length = max(0, end - start + 1)

                self.send_response(status)
                self._cors()
                self.send_header("Content-Type", res.mime)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                if head:
                    return

                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(CHUNK, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _serve_bytes(self, res: BytesResource, head: bool) -> None:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", res.mime)
            self.send_header("Content-Length", str(len(res.data)))
            self.end_headers()
            if not head:
                self.wfile.write(res.data)

        def _serve_hls(self, res: HlsResource, name: str, head: bool) -> None:
            """조각 전송 계측: 준비(생산 대기)·전송 시간, 속도, 전송 중 끊김.
            전송 시간은 데이터를 OS에 넘긴 시점 기준이라 실제보다 약간 짧게 나올 수 있다."""
            t0 = time.monotonic()
            result = res.get(name)
            if result is None:
                self._empty(404)
                return
            data, mime = result
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if head:
                return
            seg = name.endswith(".m4s")          # 재생 목록·init·자막은 계측하지 않음
            t1 = time.monotonic()
            view, size, sent = memoryview(data), len(data), 0
            try:
                while sent < size:
                    n = min(CHUNK, size - sent)
                    self.wfile.write(view[sent:sent + n])
                    sent += n
            except _CLIENT_GONE:
                if seg:
                    _LOGGER.info("전송 중 끊김: %s %.1f/%.1fMB, %.1f초 만에 (준비 %.1f초)",
                                 name, sent / 1e6, size / 1e6, time.monotonic() - t1, t1 - t0)
                raise
            if seg:
                dt = time.monotonic() - t1
                slow = dt >= SLOW_SEND
                _LOGGER.log(logging.INFO if slow else logging.DEBUG,
                            "전송: %s %.1fMB, 준비 %.2f초 + 전송 %.2f초 (%.1fMbps)%s",
                            name, size / 1e6, t1 - t0, dt, size * 8 / 1e6 / max(dt, 1e-3),
                            " ← 느림" if slow else "")

        def _serve_stream(self, res: StreamResource, head: bool,
                          query: dict[str, str]) -> None:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", res.mime)
            self.send_header("Connection", "close")  # 길이 미정 → 연결 종료로 끝 표시
            self.end_headers()
            self.close_connection = True
            if head:
                return
            stream = res.open_stream(query)
            try:
                while chunk := stream.read(CHUNK):
                    self.wfile.write(chunk)
            finally:
                stream.close()

    return Handler
