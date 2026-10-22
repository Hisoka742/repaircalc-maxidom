"""Draw the stratified sample the team verifies by hand (checklist G2).

    uv run python scripts/make_gold_sample.py data/stand/stand.jsonl --n 800 \
        --out data/gold_todo.csv
        [--model data/demo_model.joblib]

The CSV has the prediction pre-filled (`predicted_calc`); a human fills `verified_calc` and the
`split` column says dev or test (never tune on test). Score it with scripts/score_gold.py.
"""
import argparse
import sys
from pathlib import Path

from maxicalc.catalog.adapters import load_catalog
from maxicalc.ml.classify import MatchModel
from maxicalc.ml.gold import sample_for_labeling, write_labeling_csv
from maxicalc.ml.match import Matcher


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("catalog")
    ap.add_argument("--n", type=int, default=800)
    ap.add_argument("--out", default="data/gold_todo.csv")
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    products, _ = load_catalog(a.catalog)
    matcher = Matcher(MatchModel.load(Path(a.model)) if a.model else None)
    pred = {p.sku: (r.calc_template.label if r.calc_template else "none")
            for p, r in zip(products, matcher.match(products), strict=True)}
    rows = sample_for_labeling(products, lambda p: pred[p.sku], a.n, a.seed)
    write_labeling_csv(rows, Path(a.out))
    dev = sum(1 for r in rows if r.split == "dev")
    print(f"{len(rows)} товаров -> {a.out} (dev {dev}, test {len(rows) - dev}); "
          f"заполните столбец verified_calc")
    return 0


if __name__ == "__main__":
    sys.exit(main())
