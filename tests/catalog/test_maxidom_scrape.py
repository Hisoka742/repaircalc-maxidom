"""The maxidom.ru scraper: parser on a trimmed REAL page, robots/delay, cache, planning. Offline."""
from decimal import Decimal as D
from pathlib import Path

import httpx

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.maxidom_scrape import (
    Crawler,
    group_of,
    iter_products,
    parse_product,
    plan_urls,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "maxidom_laminat.html"
URL = "https://www.maxidom.ru/catalog/laminat-33-klassa/1001099534/"
ROBOTS = "User-agent: *\nDisallow: /search/\nDisallow: /bitrix/\nCrawl-delay: 3\n"


def test_parser_reads_a_real_product_card() -> None:
    item = parse_product(FIX.read_text(encoding="utf-8"), URL)
    assert item is not None
    assert item["id"] == 1001099534 and item["sku"] == "DYPV252"
    assert item["cod_good"] == "1001099534"
    assert item["name"].startswith("ламинат MAXWOOD Dynamic 33кл")
    assert item["result_price"] == 2504.0
    assert item["brand"]["name"] == "MAXWOOD"
    assert item["package_area"] == 1.596 and item["quantity_in_package"] == 7
    assert item["in_stock"] is False
    chars = {c["name"]: c["value"] for c in item["characteristics"]}
    assert chars["Износостойкость"] == "33класс" and chars["Влагостойкость"] == "нет"
    assert item["categories_tree"][0]["name"]            # the section name was found


def test_the_item_loads_through_the_stand_adapter(tmp_path: Path) -> None:
    import json

    item = parse_product(FIX.read_text(encoding="utf-8"), URL)
    f = tmp_path / "m.jsonl"
    f.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")
    products, rep = load_catalog(f)
    p = products[0]
    assert rep.loaded == 1 and p.product_id == "1001099534" and p.sku == "DYPV252"
    assert p.price == D("2504") and p.package_area_m2 == D("1.596")
    assert p.characteristics["Площадь упаковки"] == "1.596 м2"


def test_a_non_product_page_is_not_a_product() -> None:
    assert parse_product("<html><h1>Каталог</h1></html>",
                         "https://www.maxidom.ru/catalog/laminat-33-klassa/") is None
    assert parse_product("<html></html>", URL) is None      # no name


def test_repair_slugs_are_kept_and_look_alikes_dropped() -> None:
    assert group_of("laminat-33-klassa") == "flooring"
    assert group_of("keramogranit-napolnyy") == "tile"
    assert group_of("oboi-pod-pokrasku") == "wallpaper"
    assert group_of("kashpo-gorshki-dlya-komnatnyh-rasteniy") is None
    assert group_of("gotovye-pochvogrunty") is None
    assert group_of("udobreniya") is None


def test_plan_interleaves_categories_so_any_prefix_covers_every_type() -> None:
    def xml(slug: str, n: int) -> str:
        return "".join(f"<loc>https://www.maxidom.ru/catalog/{slug}/{i}/</loc>" for i in range(n))

    p = plan_urls([xml("oboi", 50), xml("laminat-33-klassa", 5), xml("udobreniya", 9)])
    slugs = [u.split("/")[4] for u in p.urls]
    assert "udobreniya" not in slugs and len(p.urls) == 55
    assert set(slugs[:4]) == {"oboi", "laminat-33-klassa"}   # alternates from the start
    assert p.by_group == {"wallpaper": 50, "flooring": 5}


def make_crawler(
    tmp_path: Path, hits: list[str], delay: float = 0.0
) -> tuple[Crawler, list[float]]:
    slept: list[float] = []
    now = [0.0]

    def handler(req: httpx.Request) -> httpx.Response:
        hits.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return httpx.Response(200, text="<html><h1>x</h1></html>")

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    def clock() -> float:
        return now[0]

    c = Crawler(tmp_path / "raw", delay,
                httpx.Client(transport=httpx.MockTransport(handler)), sleep, clock)
    c.load_robots()
    return c, slept


def test_robots_delay_and_disallow_are_obeyed(tmp_path: Path) -> None:
    hits: list[str] = []
    c, slept = make_crawler(tmp_path, hits, delay=1.0)
    assert c.crawl_delay == 3.0                      # robots' Crawl-delay beats our minimum
    assert c.get("https://www.maxidom.ru/search/?q=x") is None
    assert "/search/" not in "".join(hits)           # never even requested
    c.get("https://www.maxidom.ru/catalog/a/1/")
    c.get("https://www.maxidom.ru/catalog/a/2/")
    assert slept and sum(slept) >= 3.0               # the second request waited


def test_cache_means_no_second_request(tmp_path: Path) -> None:
    hits: list[str] = []
    c, _ = make_crawler(tmp_path, hits)
    u = "https://www.maxidom.ru/catalog/a/1/"
    c.get(u)
    n = len(hits)
    c2, _ = make_crawler(tmp_path, hits)             # a new process, same cache directory
    n2 = len(hits)
    assert c2.get(u) is not None
    assert len(hits) == n2 and c2.cache_hits == 1 and n2 > n - 1


def test_iter_products_stops_at_the_limit(tmp_path: Path) -> None:
    page = FIX.read_text(encoding="utf-8")
    hits: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hits.append(str(req.url))
        return httpx.Response(200, text=ROBOTS if req.url.path == "/robots.txt" else page)

    c = Crawler(tmp_path / "raw", 0.0, httpx.Client(transport=httpx.MockTransport(handler)),
                lambda s: None, lambda: 0.0)
    c.load_robots()
    urls = [f"https://www.maxidom.ru/catalog/laminat-33-klassa/{i}/" for i in range(1, 9)]
    got = list(iter_products(c, urls, limit=3))
    assert len(got) == 3 and c.requests == 3
