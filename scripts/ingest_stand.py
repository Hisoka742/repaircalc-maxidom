"""Full ingest from the catalog stand: fetch -> normalize -> extract -> match -> quality report.

    uv run python scripts/ingest_stand.py [--out data/stand] [--model data/demo_model.joblib]
                                          [--limit 5000] [--per-page 100]

The stand comes from STAND_BASE_URL (+ STAND_TOKEN) in .env: point it at the mock
(`make mock-stand`, http://127.0.0.1:9000) or at the real stand; nothing else changes. Responses
are cached on disk (STAND_CACHE_DIR), so a repeated run only pays for what changed; delete the
cache directory to force a refresh.
"""
import argparse
import sys
from pathlib import Path

from maxicalc.catalog.ingest_job import run_ingest
from maxicalc.catalog.stand_client import StandClient, StandError
from maxicalc.config import settings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", default="data/stand")
    ap.add_argument("--model", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--root", type=int, default=1)
    a = ap.parse_args()
    if not settings.stand_base_url:
        print("ОШИБКА: задайте STAND_BASE_URL в .env (mock: http://127.0.0.1:9000)")
        return 2
    client = StandClient(settings.stand_base_url, settings.stand_token,
                         cache_dir=settings.stand_cache_dir,
                         min_interval_s=settings.stand_min_interval_s)
    try:
        res = run_ingest(client, Path(a.out), a.per_page, a.root,
                         Path(a.model) if a.model else None, a.limit)
    except (StandError, ValueError) as e:
        print(f"ОШИБКА: {e}")
        return 2
    s, q = res.stats, res.quality
    print(f"Получено {res.fetched} товаров ({s.categories} категорий, {s.pages} страниц, "
          f"{s.cards} карточек, из кэша {s.cache_hits}), загружено {res.loaded}, "
          f"авто {res.auto}, на проверку {res.review}, {res.seconds} с")
    cov = q.coverage
    print(f"Цена у {cov['price'] * 100:.0f}%, описание у {cov['description'] * 100:.0f}%, "
          f"единица продажи распознана у {q.unit_parse_rate * 100:.0f}%, "
          f"фасовка известна у {q.pack_info_rate * 100:.0f}%")
    for p in s.problems[:10]:
        print("  !", p)
    print(f"Отчёты: {res.out_dir / 'quality.md'}, {res.out_dir / 'report.md'}")
    return 0 if res.loaded else 2


if __name__ == "__main__":
    sys.exit(main())
