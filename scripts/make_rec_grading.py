"""Export recommendation queries for human grading (0-3), and score the graded file.

    uv run python scripts/make_rec_grading.py data/scrape/maxidom_products.jsonl \
        --out data/rec_grading.csv [--model data/demo_model.joblib] [--top-k 8]
    uv run python scripts/make_rec_grading.py --score data/rec_grading.csv

Fill the `grade` column (0 wrong / 1 acceptable / 2 good / 3 best for this room). Only queries
with every row graded are scored. With the graded file at eval/gold/rec_grades.csv, `make eval`
reports the human nDCG@5 next to the rubric one.
"""
import argparse
import sys
from pathlib import Path

from maxicalc.catalog.adapters import load_catalog
from maxicalc.ml.classify import MatchModel
from maxicalc.ml.match import Matcher
from maxicalc.recommend.human_grades import (
    entries_from_results,
    export_queries,
    ndcg_from_grades,
    write_csv,
)
from maxicalc.recommend.recommend_eval import QUERY_CALCS, ROOMS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("catalog", nargs="?")
    ap.add_argument("--out", default="data/rec_grading.csv")
    ap.add_argument("--model", default=None)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--score", default=None, help="graded CSV to score instead of exporting")
    a = ap.parse_args()
    if a.score:
        h = ndcg_from_grades(Path(a.score))
        print(f"Запросов {h.queries_total}, полностью оценено {h.queries_graded} "
              f"({h.graded_rows} строк); nDCG@5 по оценкам людей {h.mean_ndcg:.3f}; "
              f"средняя оценка топ-1 {h.mean_grade_top1:.2f}/3")
        return 0
    if not a.catalog:
        ap.error("нужен каталог или --score")
    products, _ = load_catalog(a.catalog)
    matcher = Matcher(MatchModel.load(Path(a.model)) if a.model else None)
    entries = entries_from_results(products, matcher.match(products))
    rows = export_queries(entries, ROOMS, QUERY_CALCS, a.top_k)
    write_csv(rows, Path(a.out))
    print(f"{len({r.query_id for r in rows})} запросов, {len(rows)} строк -> {a.out}; "
          f"заполните столбец grade (0-3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
