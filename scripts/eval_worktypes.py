"""Evaluate the work-type matcher on the human gold set (the one-command check for organisers).

    uv run python scripts/eval_worktypes.py --gold eval/gold/worktype_gold.csv
        [--catalog data/feed/latest.xml.gz | any catalog the gold SKUs come from]
        [--model data/models/worktypes.joblib] [--out eval/WORKTYPES.md]

A gold file has `sku;works;split;group` (works = work-type ids separated by ";" or "none"); to run
the check on YOUR OWN products, give --catalog (CSV/XLSX/JSON/YML) and a gold file in that format.
Thresholds are tuned on the dev split only; the numbers reported are the test split.
"""
import argparse
import sys
from pathlib import Path

import joblib

from maxicalc.catalog.adapters import load_catalog
from maxicalc.ml.worktype_report import load_gold, markdown, run_gold_eval


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--gold", default="eval/gold/worktype_gold.csv")
    ap.add_argument("--catalog", default="data/feed/latest.xml.gz")
    ap.add_argument("--model", default="data/models/worktypes.joblib")
    ap.add_argument("--out", default="eval/WORKTYPES.md")
    a = ap.parse_args()
    if not Path(a.gold).exists():
        print(f"нет золотого набора {a.gold}: сначала разметка (scripts/make_worktype_gold.py, "
              "merge_worktype_gold.py)")
        return 2
    products, _ = load_catalog(a.catalog)
    items = load_gold(Path(a.gold), {p.sku: p for p in products})
    model = joblib.load(a.model) if Path(a.model).exists() else None
    ev = run_gold_eval(items, model)
    md = "\n".join(markdown(ev, pilot="pilot" in Path(a.gold).name.lower())) + "\n"
    Path(a.out).write_text(md, encoding="utf-8")
    print(md[:1800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
