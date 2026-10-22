"""Ingest any supported catalog file and print a validation + extraction-coverage report.

    uv run python scripts/ingest_catalog.py path/to/catalog.csv [--out products.jsonl]
"""
import argparse
import json
import sys
import time
from collections import Counter

from maxicalc.catalog.adapters import load_catalog
from maxicalc.ml.extract import extract


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--out", help="write products + extracted attrs as JSONL")
    args = ap.parse_args()

    t0 = time.perf_counter()
    items, rep = load_catalog(args.path)
    t1 = time.perf_counter()
    cover: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    out = open(args.out, "w", encoding="utf-8") if args.out else None  # noqa: SIM115
    for p in items:
        r = extract(p)
        cover.update(r.attrs.keys())
        rejected.update(x.name for x in r.rejected)
        if out:
            row = p.model_dump(mode="json")
            row["attrs"] = {
                k: {"value": str(a.value), "source": a.source, "confidence": a.confidence}
                for k, a in r.attrs.items()
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    t2 = time.perf_counter()
    print(f"read {rep.read}, loaded {rep.loaded}, skipped {rep.skipped}, "
          f"issues {rep.issues_total}  (ingest {t1 - t0:.2f}s, extract {t2 - t1:.2f}s)")
    for i in rep.issues[:20]:
        print("  -", i)
    n = max(len(items), 1)
    print("attribute coverage (share of products with the attribute):")
    for k, v in cover.most_common():
        print(f"  {k:32s} {v:6d}  {100 * v / n:5.1f}%")
    if rejected:
        print("rejected (implausible) values:", dict(rejected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
