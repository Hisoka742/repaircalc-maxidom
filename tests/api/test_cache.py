from maxicalc.api.cache import MemoryCache, RedisCache, make_cache


def test_memory_cache_lru_eviction() -> None:
    c = MemoryCache(max_items=2)
    c.set("a", "1")
    c.set("b", "2")
    assert c.get("a") == "1"        # touch a -> b is now least recently used
    c.set("c", "3")
    assert c.get("b") is None and c.get("a") == "1" and c.get("c") == "3"


def test_memory_cache_ttl() -> None:
    # negative TTL = already expired; avoids sleeping (Windows monotonic clock is ~15 ms coarse)
    c = MemoryCache(ttl_s=-1)
    c.set("a", "1")
    assert c.get("a") is None
    fresh = MemoryCache(ttl_s=60)
    fresh.set("a", "1")
    assert fresh.get("a") == "1"


class FakeRedis:
    def __init__(self) -> None:
        self.d: dict[str, bytes] = {}
        self.broken = False

    def get(self, k: str) -> bytes | None:
        if self.broken:
            raise ConnectionError("down")
        return self.d.get(k)

    def set(self, k: str, v: str, ex: int | None = None) -> None:
        if self.broken:
            raise ConnectionError("down")
        self.d[k] = v.encode()


def test_redis_cache_roundtrip_and_prefix() -> None:
    fake = FakeRedis()
    c = RedisCache(fake)
    c.set("k", "v")
    assert c.get("k") == "v" and "maxicalc:k" in fake.d and c.get("zz") is None


def test_redis_outage_degrades_to_miss_not_error() -> None:
    fake = FakeRedis()
    c = RedisCache(fake)
    c.set("k", "v")
    fake.broken = True
    assert c.get("k") is None      # miss -> the estimate is simply recomputed
    c.set("k2", "v2")              # must not raise


def test_make_cache_falls_back_to_memory_when_redis_is_unreachable() -> None:
    c = make_cache("redis://127.0.0.1:1/0", 10, 10)
    assert c.name == "memory"
    assert make_cache(None, 10, 10).name == "memory"
