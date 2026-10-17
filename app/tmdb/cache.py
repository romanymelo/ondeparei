import time
from collections import OrderedDict
from collections.abc import Callable, Hashable, Mapping
from typing import Any


def make_key(path: str, params: Mapping[str, Any]) -> tuple:
    return (path, tuple(sorted(params.items())))


class TTLCache:
    """Cache em memória com prazo de validade por entrada e descarte LRU."""

    def __init__(self, max_entries: int = 1000, clock: Callable[[], float] = time.monotonic) -> None:
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()

    def get(self, key: Hashable) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._entries[key]
            return None
        self._entries.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any, ttl: float) -> None:
        self._entries[key] = (self._clock() + ttl, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)
