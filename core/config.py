"""config.json 로드/저장."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields

from .paths import config_path

_LOGGER = logging.getLogger(__name__)


@dataclass
class AppConfig:
    server_port: int = 8765
    last_device_uuid: str | None = None
    known_hosts: list[str] = field(default_factory=list)  # 수동 입력 IP
    volume: float = 0.5
    subtitle_scale: float = 1.0   # 3단계: 자막 글자 크기 (0.5~2.0)
    last_device_name: str | None = None   # 4단계: 안내 문구용
    last_device_host: str | None = None   # 4단계: mDNS로 못 찾을 때 시도할 IP (힌트)
    auto_connect: bool = True             # 4단계: 시작 시 마지막 기기 자동 연결
    debug_log: bool = False               # 4단계: DEBUG 로그 (-v는 이 값을 바꾸지 않음)

    @classmethod
    def load(cls) -> "AppConfig":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _LOGGER.warning("config.json 읽기 실패, 기본값 사용", exc_info=True)
            return cls()
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def save(self) -> None:
        try:
            config_path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            _LOGGER.warning("config.json 저장 실패", exc_info=True)
