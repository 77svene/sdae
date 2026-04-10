"""
HotCache — in-memory LRU. Sub-millisecond reads.
Evicts least-recently-used when full. Max 500 entries.
"""
from __future__ import annotations
from collections import OrderedDict


class HotCache:
    def __init__(self, max_size: int = 500):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max = max_size

    def get(self, key: str) -> str | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: str):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)

    def delete(self, key: str):
        self._cache.pop(key, None)

    def clear(self):
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


HOT = HotCache()
