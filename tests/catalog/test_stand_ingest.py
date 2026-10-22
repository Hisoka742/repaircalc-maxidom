"""Checklist B1/B3/B4/B5: disk cache, rate limit, region default, special price, ingest job."""
import time
from datetime import datetime
from decimal import Decimal as D
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from maxicalc.catalog.adapters.maxidom_api import item_to_product
from maxicalc.catalog.ingest_job import run_ingest
from maxicalc.catalog.quality import quality_report
from maxicalc.catalog.schema import Product
from maxicalc.catalog.stand_client import StandClient
from maxicalc.stand_mock import build_stand_app


def products(n: int = 12) -> list[Product]:
    return [Product(
        sku=f"A-{i}", name=f"Ламинат Tarkett LM{i} 32 класс", brand="Tarkett",
        price=D(1500 + i), description="В упаковке 2,131 м2",
        category_path=["Напольные покрытия", "Ламинат"]) for i in range(n)]


class Counting(httpx.BaseTransport):
    """Counts the requests that really reach the stand."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self.inner = inner
        self.count = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.count += 1
        return self.inner.handle_request(request)


def counting_client(n: int = 12) -> tuple[httpx.Client, Counting]:
    app = TestClient(build_stand_app(products(n)), base_url="http://stand")
    c = Counting(app._transport)  # type: ignore[attr-defined]
    return httpx.Client(transport=c, base_url="http://stand"), c


def test_second_run_is_served_from_the_disk_cache(tmp_path: Path) -> None:
    http, count = counting_client()
    first = StandClient(client=http, cache_dir=tmp_path, backoff_s=0)
    items = first.fetch_all(per_page=5)
    n = count.count
    assert n > 10 and len(items) == 12

    again = StandClient(client=http, cache_dir=tmp_path, backoff_s=0)
    assert len(again.fetch_all(per_page=5)) == 12
    assert count.count == n                       # nothing new hit the stand
    assert again.stats.cache_hits >= n


def test_rate_limit_spaces_requests() -> None:
    http, _ = counting_client(3)
    c = StandClient(client=http, min_interval_s=0.05, backoff_s=0)
    t0 = time.perf_counter()
    for _ in range(4):
        c.regions()
    assert time.perf_counter() - t0 >= 0.15       # 3 gaps of 50 ms


def test_default_region_comes_from_the_regions_list() -> None:
    http, _ = counting_client(2)
    assert StandClient(client=http, backoff_s=0).default_region_id() == "1"


def test_categories_endpoint_is_read_too() -> None:
    http, _ = counting_client(4)
    cats = StandClient(client=http, backoff_s=0).categories(parent_id=1, depth_level=3)
    assert cats and {"id", "name", "depth_level"} <= set(cats[0])


def item(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {"id": 1, "sku": "S", "name": "Плитка", "price": 1800,
                               "result_price": 1650, "special_price": 1500}
    base.update(kw)
    return base


NOW = datetime(2026, 9, 15, 12, 0)


def test_special_price_applies_only_when_active_and_inside_its_period() -> None:
    ok = item_to_product(item(special_price_active=True, special_price_from="2026-09-01 00:00:00",
                              special_price_to="2026-09-30 23:59:00"), now=NOW)
    assert ok is not None and ok.special_price == D("1500")
    assert ok.price == D("1650")                  # the displayed price is still result_price
    off = item_to_product(item(special_price_active=False), now=NOW)
    assert off is not None and off.special_price is None
    expired = item_to_product(
        item(special_price_active=True, special_price_to="2026-09-01 00:00:00"), now=NOW)
    assert expired is not None and expired.special_price is None
    early = item_to_product(
        item(special_price_active=True, special_price_from="2026-10-01 00:00:00"), now=NOW)
    assert early is not None and early.special_price is None


def test_quality_report_counts_coverage_and_unit_parse_rate() -> None:
    ps = [
        Product(sku="1", name="Ламинат 32 класс", description="В упаковке 2,131 м2",
                characteristics={"Площадь упаковки": "2.131 м2"}, price=D(100), unit="упак.",
                category_path=["Пол"], package_area_m2=D("2.131")),
        Product(sku="2", name="Что-то", price=None),
    ]
    q = quality_report(ps)
    assert q.total == 2
    assert q.coverage["price"] == 0.5 and q.coverage["description"] == 0.5
    assert q.coverage["characteristics"] == 0.5 and q.coverage["category"] == 0.5
    assert q.unit_parse_rate == 0.5               # 1 of 2 has a parseable sale unit
    assert q.pack_info_rate == 0.5


def test_ingest_job_runs_the_whole_chain_against_the_mock(tmp_path: Path) -> None:
    http, _ = counting_client(30)
    client = StandClient(client=http, cache_dir=tmp_path / "cache", backoff_s=0)
    res = run_ingest(client, tmp_path / "out", per_page=10)
    assert res.fetched == 30 and res.loaded == 30 and res.skipped == 0
    assert (tmp_path / "out" / "stand.jsonl").exists()
    assert (tmp_path / "out" / "quality.md").exists()
    assert res.quality.total == 30 and res.quality.coverage["price"] == 1.0
    assert res.seconds < 60                       # the < 15 min target has huge slack on the mock
    assert res.auto + res.review == 30
