"""Estimate cache. In-memory LRU by default; Redis when REDIS_URL is set and reachable.

Values are JSON strings. A cache miss is never an error: the estimate is recomputed
(calculations are deterministic and idempotent), so a cache outage degrades speed only.
"""
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Protocol

import structlog

log = structlog.get_logger()


class Cache(Protocol):
    name: str

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...


class MemoryCache:
    name = "memory"

    def __init__(self, max_items: int = 5000, ttl_s: int = 86400) -> None:
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._max = max_items
        self._ttl = ttl_s
        self._lock = Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if expires < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + self._ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)


class RedisCache:
    name = "redis"

    def __init__(self, client: Any, ttl_s: int = 86400, prefix: str = "maxicalc:") -> None:
        self._r = client
        self._ttl = ttl_s
        self._prefix = prefix

    def get(self, key: str) -> str | None:
        try:
            v = self._r.get(self._prefix + key)
        except Exception as e:  # cache outage must not break the API
            log.warning("redis_get_failed", error=str(e))
            return None
        if v is None:
            return None
        return v.decode("utf-8") if isinstance(v, bytes) else str(v)

    def set(self, key: str, value: str) -> None:
        try:
            self._r.set(self._prefix + key, value, ex=self._ttl)
        except Exception as e:
            log.warning("redis_set_failed", error=str(e))


def make_cache(redis_url: str | None, max_items: int, ttl_s: int) -> Cache:
    if redis_url:
        try:
            import redis

            client = redis.Redis.from_url(redis_url, socket_connect_timeout=0.5,
                                          socket_timeout=0.5)
            client.ping()
            return RedisCache(client, ttl_s)
        except Exception as e:
            log.warning("redis_unavailable_using_memory_cache", error=str(e))
    return MemoryCache(max_items, ttl_s)
