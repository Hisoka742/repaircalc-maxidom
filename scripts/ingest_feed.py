"""Fetch (or reuse) the Maxidom YML feed, normalise it, and write the ingest report.

    uv run python scripts/ingest_feed.py                      # download a dated snapshot, report
    uv run python scripts/ingest_feed.py --file data/feed/latest.xml.gz   # no download
    uv run python scripts/ingest_feed.py --url <feed url>

Output: data/feed/export_yandex_spb_<date>.xml.gz, data/feed/latest.xml.gz (the default catalog,
CATALOG_PATH in .env.example), data/feed/REPORT.md. The feed is the default data source; the
Bagisto stand and the HTML scraper stay as optional adapters.
"""
import argparse
import sys
import time
from pathlib import Path

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.adapters.yml_feed import feed_date
from maxicalc.catalog.feed import FEED_URL, feed_report, fetch_snapshot, report_markdown


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default=FEED_URL)
    ap.add_argument("--file", default=None, help="use this snapshot instead of downloading")
    ap.add_argument("--out-dir", default="data/feed")
    a = ap.parse_args()
    out = Path(a.out_dir)
    t0 = time.perf_counter()
    if a.file:
        path = Path(a.file)
    else:
        print(f"скачивание {a.url} ...")
        path = fetch_snapshot(a.url, out)
        size = path.stat().st_size / 1e6
        print(f"снимок: {path} ({size:.1f} МБ, {time.perf_counter() - t0:.0f} с)")
    t1 = time.perf_counter()
    products, ingest = load_catalog(path)
    seconds = time.perf_counter() - t1
    rep = feed_report(products, seconds, feed_date(path))
    md = report_markdown(rep)
    out.mkdir(parents=True, exist_ok=True)
    (out / "REPORT.md").write_text(md, encoding="utf-8")
    print(f"offers {rep.offers}, ремонт {rep.repair} ({100 * rep.repair_share:.1f}%), "
          f"пропущено {ingest.skipped}, замечаний {ingest.issues_total}; "
          f"разбор {seconds:.1f} с -> {out / 'REPORT.md'}")
    return 0 if rep.offers else 2


if __name__ == "__main__":
    sys.exit(main())
