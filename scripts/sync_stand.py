"""Pull the whole catalog from the organisers' stand API into a JSONL dump.

    uv run python scripts/sync_stand.py --url https://stand.example --out data/stand.jsonl
        [--token T] [--root 1] [--per-page 100] [--no-cards] [--limit 5000]

Then run it through the usual pipeline:
    uv run python scripts/dayof.py run data/stand.jsonl
    CATALOG_PATH=data/stand.jsonl uv run uvicorn maxicalc.api.main:app

Reads every page of every category (meta.last_page), then the full card of every product
(description and characteristics are not in the list), de-duplicating by `id`.
"""
import argparse
import sys

from maxicalc.catalog.stand_client import StandClient, StandError
from maxicalc.config import settings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default=settings.stand_base_url,
                    help="base URL of the stand (default: STAND_BASE_URL from .env)")
    ap.add_argument("--out", default="data/stand.jsonl")
    ap.add_argument("--token", default=settings.stand_token)
    ap.add_argument("--root", type=int, default=1, help="root category id")
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--no-cards", action="store_true", help="list data only (no descriptions)")
    ap.add_argument("--limit", type=int, default=None, help="stop after about N products")
    a = ap.parse_args()
    if not a.url:
        print("ОШИБКА: укажите --url или STAND_BASE_URL в .env (mock: http://127.0.0.1:9000)")
        return 2
    client = StandClient(a.url, a.token, cache_dir=settings.stand_cache_dir,
                         min_interval_s=settings.stand_min_interval_s)
    try:
        items = client.fetch_all(a.root, a.per_page, not a.no_cards, a.limit)
    except StandError as e:
        print(f"ОШИБКА: {e}")
        return 2
    n = StandClient.dump(items, a.out)
    s = client.stats
    print(f"Категорий: {s.categories}, страниц: {s.pages}, товаров: {s.products}, "
          f"карточек: {s.cards} (ошибок {s.card_errors}), повторов запросов: {s.retries}, "
          f"{s.seconds} с -> {a.out} ({n} строк)")
    for p in s.problems[:20]:
        print("  !", p)
    return 0 if s.products else 2


if __name__ == "__main__":
    sys.exit(main())
