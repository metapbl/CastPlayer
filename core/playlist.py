"""재생 목록. 1단계는 단일 항목, 연속재생 확장 대비 구조."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PlaylistItem:
    path: Path
    audio_stream: int | None = None   # 2단계: 선택한 음성 트랙 (ffprobe 순번)
    subtitle_key: str | None = None   # 3단계: 선택한 자막 식별자
    title: str = ""

    def __post_init__(self) -> None:
        if not self.title:
            self.title = self.path.stem


class Playlist:
    def __init__(self) -> None:
        self._items: list[PlaylistItem] = []
        self._index = -1

    def set_single(self, item: PlaylistItem) -> None:
        self._items = [item]
        self._index = 0

    def add(self, item: PlaylistItem) -> None:
        self._items.append(item)
        if self._index < 0:
            self._index = 0

    def current(self) -> PlaylistItem | None:
        return self._items[self._index] if 0 <= self._index < len(self._items) else None

    def has_next(self) -> bool:
        return self._index + 1 < len(self._items)

    def next(self) -> PlaylistItem | None:
        if not self.has_next():
            return None
        self._index += 1
        return self._items[self._index]

    def clear(self) -> None:
        self._items.clear()
        self._index = -1
