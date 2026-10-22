"""Human grading export and nDCG from the graded CSV."""
import csv
from pathlib import Path

from maxicalc.recommend.human_grades import COLUMNS, ndcg_from_grades


def _write(path: Path, rows: list[tuple[str, int, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUMNS)
        for q, rank, grade in rows:
            room, calc = q.split(":")
            w.writerow([q, room, calc, rank, f"s{rank}", "n", "1", "0.5", grade, ""])


def test_perfect_order_scores_one_and_inverted_scores_less(tmp_path: Path) -> None:
    f = tmp_path / "g.csv"
    _write(f, [("bathroom:tile", 1, "3"), ("bathroom:tile", 2, "2"), ("bathroom:tile", 3, "0")])
    h = ndcg_from_grades(f)
    assert h.queries_graded == 1 and h.mean_ndcg == 1.0 and h.mean_grade_top1 == 3.0
    _write(f, [("bathroom:tile", 1, "0"), ("bathroom:tile", 2, "2"), ("bathroom:tile", 3, "3")])
    assert 0 < ndcg_from_grades(f).mean_ndcg < 1.0


def test_partly_graded_queries_are_not_scored(tmp_path: Path) -> None:
    f = tmp_path / "g.csv"
    _write(f, [("kitchen:paint", 1, "2"), ("kitchen:paint", 2, ""),
               ("hallway:paint", 1, "3"), ("hallway:paint", 2, "1")])
    h = ndcg_from_grades(f)
    assert h.queries_total == 2 and h.queries_graded == 1 and h.graded_rows == 3
