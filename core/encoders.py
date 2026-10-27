"""사용 가능한 H.264 인코더 탐지 (하드웨어 우선, libx264 대체)."""
from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .proc import NO_WINDOW

_LOGGER = logging.getLogger(__name__)
_CANDIDATES = ("h264_nvenc", "h264_qsv", "h264_amf", "libx264")
_PIX_FMT = {"h264_qsv": "nv12"}


@dataclass(frozen=True)
class EncoderProfile:
    name: str
    pix_fmt: str

    def video_args(self, maxrate_k: int, gop: int) -> list[str]:
        mr, bs, avg = f"{maxrate_k}k", f"{maxrate_k * 2}k", f"{maxrate_k // 2}k"
        g = ["-g", str(gop)]
        if self.name == "h264_nvenc":
            return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21",
                    "-b:v", "0", "-maxrate", mr, "-bufsize", bs,
                    "-profile:v", "high", *g]
        if self.name == "h264_qsv":
            return ["-c:v", "h264_qsv", "-preset", "faster", "-b:v", avg,
                    "-maxrate", mr, "-bufsize", bs, "-profile:v", "high", *g]
        if self.name == "h264_amf":
            return ["-c:v", "h264_amf", "-quality", "speed", "-rc", "vbr_peak",
                    "-b:v", avg, "-maxrate", mr, "-bufsize", bs,
                    "-profile:v", "high", *g]
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-maxrate", mr, "-bufsize", bs, "-profile:v", "high",
                "-level:v", "5.1", *g]


class EncoderDetector:
    def __init__(self, ffmpeg: Path) -> None:
        self._ffmpeg = str(ffmpeg)
        self._done = threading.Event()
        self._result: EncoderProfile | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="enc-detect",
                                            daemon=True)
            self._thread.start()

    def get(self, timeout: float = 60.0) -> EncoderProfile | None:
        self.start()
        self._done.wait(timeout)
        return self._result

    def _run(self) -> None:
        try:
            for name in _CANDIDATES:
                pix = _PIX_FMT.get(name, "yuv420p")
                if self._test(name, pix):
                    self._result = EncoderProfile(name, pix)
                    _LOGGER.info("인코더 선택: %s", name)
                    return
            _LOGGER.error("사용 가능한 H.264 인코더가 없습니다.")
        finally:
            self._done.set()

    def _test(self, name: str, pix: str) -> bool:
        cmd = [self._ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
               "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30", "-t", "0.5",
               "-vf", f"format={pix}", "-c:v", name, "-f", "null", "-"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=20,
                               creationflags=NO_WINDOW, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        _LOGGER.debug("인코더 %s 테스트: %s", name, r.returncode)
        return r.returncode == 0
