"""One ingest job: categories -> products -> full cards -> normalize -> extract -> match -> report.

    run_ingest(StandClient(base_url, token), out_dir)

Writes `stand.jsonl` (the raw merged cards), `quality.md` (field coverage, unit parse rate) and
everything `dayof` writes (matched.jsonl, review_queue.csv, readiness, report.md). The base URL is
the only thing that differs between the mock stand and the real one.
"""
import time
from dataclasses import dataclass
from pathlib import Path

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.quality import Quality, quality_report
from maxicalc.catalog.stand_client import FetchStats, StandClient
from maxicalc.dayof import run_dayof


@dataclass
class IngestResult:
    out_dir: Path
    fetched: int
    loaded: int
    skipped: int
    auto: int
    review: int
    quality: Quality
    stats: FetchStats
    seconds: float


def run_ingest(
    client: StandClient, out_dir: Path, per_page: int = 100, root_category: int = 1,
    model: Path | None = None, limit: int | None = None,
) -> IngestResult:
    t0 = time.perf_counter()
    out_dir.mkdir(parents=True, exist_ok=True)
    items = client.fetch_all(root_category, per_page, with_cards=True, max_products=limit)
    dump = out_dir / "stand.jsonl"
    StandClient.dump(items, dump)
    products, _ = load_catalog(dump)
    q = quality_report(products)
    (out_dir / "quality.md").write_text(q.to_markdown() + "\n", encoding="utf-8")
    res = run_dayof(dump, out_dir, model)
    return IngestResult(out_dir, len(items), res.loaded, res.skipped, res.auto, res.review, q,
                        client.stats, round(time.perf_counter() - t0, 2))
