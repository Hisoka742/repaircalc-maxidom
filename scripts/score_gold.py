"""Score a hand-verified gold CSV: per-class precision/recall/F1 and macro-F1 (checklist G5).

    uv run python scripts/score_gold.py data/gold_todo.csv [--split test]

Case target: F1 >= 0.8 on the top categories (aim >= 0.9). Rows with an empty verified_calc are
ignored and counted.
"""
import argparse
import csv
import sys
import tempfile
from pathlib import Path

from maxicalc.ml.gold import score_gold


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--split", choices=["dev", "test"], default=None)
    a = ap.parse_args()
    src = Path(a.csv)
    if a.split:
        with src.open(encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f, delimiter=";") if r.get("split") == a.split]
        tmp = Path(tempfile.mkdtemp()) / "g.csv"
        with tmp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["sku"], delimiter=";")
            w.writeheader()
            w.writerows(rows)
        src = tmp
    rep = score_gold(src)
    print(f"Проверено {rep.verified} (не заполнено {rep.skipped}); accuracy {rep.accuracy:.3f}, "
          f"macro-F1 {rep.macro_f1:.3f}")
    print(f"{'класс':20} {'P':>6} {'R':>6} {'F1':>6} {'n':>5}")
    for k, s in sorted(rep.per_class.items(), key=lambda kv: -kv[1].support):
        flag = "" if s.f1 >= 0.8 or s.support < 5 else "  <- ниже 0.8"
        print(f"{k:20} {s.precision:6.2f} {s.recall:6.2f} {s.f1:6.2f} {s.support:5d}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
