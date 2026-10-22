"""Collect repair products from maxidom.ru into the stand's Bagisto schema (JSONL).

    uv run python scripts/scrape_maxidom.py --out data/scrape --limit 6000
        [--delay 3] [--per-slug-cap 400] [--plan-only]

Polite by construction: robots.txt is fetched and obeyed (disallowed URLs skipped; the delay is
at least its Crawl-delay, 3 s at the time of writing), raw pages are cached under
`data/scrape/raw/` (gzip), and the run is RESUMABLE: re-running skips cached pages, so it can be
stopped (Ctrl+C) and continued, on this machine or another. 6000 pages at 3 s is about 5 hours;
the cache and `maxidom_products.jsonl` grow as it goes, and the JSONL is rewritten from the cache
at the end (and every 200 items).

The result is loadable by the service: CATALOG_PATH=data/scrape/maxidom_products.jsonl, and
servable by the stand mock: STAND_MOCK_CATALOG=data/scrape/maxidom_products.jsonl.
"""
import argparse
import json
import sys
from pathlib import Path

from maxicalc.catalog.maxidom_scrape import BASE, Crawler, iter_products, plan_urls


def write_jsonl(items: list[dict], path: Path) -> None:  # type: ignore[type-arg]
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", default="data/scrape")
    ap.add_argument("--limit", type=int, default=6000, help="stop after N parsed products")
    ap.add_argument("--delay", type=float, default=3.0, help="minimum seconds between requests")
    ap.add_argument("--per-slug-cap", type=int, default=None)
    ap.add_argument("--plan-only", action="store_true", help="only print the crawl plan")
    a = ap.parse_args()
    out = Path(a.out)
    raw = out / "raw"
    crawler = Crawler(raw, a.delay)
    try:
        crawler.load_robots()
    except Exception as e:
        print(f"ОШИБКА: не удалось прочитать robots.txt ({e}); без него не продолжаю")
        return 2
    print(f"robots.txt: задержка между запросами {crawler.crawl_delay} с")
    index = crawler.get(f"{BASE}/sitemap/sitemap.xml")
    if index is None:
        print("ОШИБКА: sitemap недоступен")
        return 2
    import re

    parts = re.findall(r"<loc>([^<]+)</loc>", index)
    texts = [t for p in parts if (t := crawler.get(p)) is not None]
    plan = plan_urls(texts, a.per_slug_cap)
    print(f"В sitemap подходящих товаров: {len(plan.urls)} в {len(plan.by_slug)} категориях")
    for g, n in sorted(plan.by_group.items(), key=lambda kv: -kv[1]):
        print(f"  {g}: {n}")
    if a.plan_only:
        return 0
    items: list[dict] = []  # type: ignore[type-arg]
    jsonl = out / "maxidom_products.jsonl"
    try:
        for it in iter_products(crawler, plan.urls, a.limit):
            items.append(it)
            if len(items) % 200 == 0:
                write_jsonl(items, jsonl)
                print(f"  {len(items)} товаров (запросов {crawler.requests}, из кэша "
                      f"{crawler.cache_hits})", flush=True)
    except KeyboardInterrupt:
        print("Остановлено: кэш сохранён, повторный запуск продолжит с этого места")
    write_jsonl(items, jsonl)
    print(f"Готово: {len(items)} товаров -> {jsonl} (запросов {crawler.requests}, "
          f"из кэша {crawler.cache_hits})")
    return 0 if items else 2


if __name__ == "__main__":
    sys.exit(main())
