"""Human relevance grades (0-3) for recommendation queries, and nDCG computed from them.

The rubric-based nDCG in `recommend_eval` checks label-error propagation on the synthetic
catalog. This module is the real thing: `export_queries` runs the pipeline on a real catalog and
writes one row per (query, returned product) for the team to grade; `ndcg_from_grades` reads the
graded CSV. The ideal ranking is the pooled judgments (everything graded for that query), the
usual TREC-style caveat: a relevant product nobody retrieved is not counted.

Grades: 0 = wrong type / wrong room / violates a rule; 1 = acceptable; 2 = good; 3 = the best
choice for this room.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

from maxicalc.catalog.schema import Product
from maxicalc.ml.match import MatchResult
from maxicalc.ml.metrics import ndcg_at_k
from maxicalc.recommend.select import CatalogEntry, recommend

COLUMNS = ["query_id", "room", "calc", "rank", "sku", "name", "price", "score", "grade", "note"]


def entries_from_results(products: list[Product], results: list[MatchResult]) -> list[CatalogEntry]:
    out: list[CatalogEntry] = []
    for p, r in zip(products, results, strict=True):
        calc = r.calc_template
        out.append(CatalogEntry(
            p, r.accepted("work_categories"), r.accepted("room_types") or {"any"},
            r.accepted("properties"), calc.label if calc and calc.accepted else "none", r.status))
    return out


@dataclass(frozen=True)
class QueryRow:
    query_id: str
    room: str
    calc: str
    rank: int
    sku: str
    name: str
    price: str
    score: str


def export_queries(
    entries: list[CatalogEntry], rooms: tuple[str, ...], calcs: tuple[str, ...], top_k: int = 8
) -> list[QueryRow]:
    """Top-k of the real pipeline for every (room, calc) that returns anything."""
    rows: list[QueryRow] = []
    for room in rooms:
        for calc in calcs:
            res = recommend(entries, room, calc=calc, top_k=top_k)
            for i, c in enumerate(res.items, 1):
                rows.append(QueryRow(f"{room}:{calc}", room, calc, i, c.entry.product.sku,
                                     c.entry.product.name, str(c.entry.product.price),
                                     f"{c.score:.3f}"))
    return rows


def write_csv(rows: list[QueryRow], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([r.query_id, r.room, r.calc, r.rank, r.sku, r.name, r.price, r.score,
                        "", ""])


@dataclass(frozen=True)
class HumanNdcg:
    queries_total: int
    queries_graded: int
    graded_rows: int
    mean_ndcg: float
    mean_grade_top1: float


def ndcg_from_grades(path: Path, k: int = 5) -> HumanNdcg:
    """nDCG@k of the pipeline's order against the humans' grades (fully graded queries only)."""
    text = path.read_text(encoding="utf-8-sig")
    delim = ";" if text.split("\n", 1)[0].count(";") else ","
    rows = list(csv.DictReader(text.splitlines(), delimiter=delim))
    by_q: dict[str, list[tuple[int, int | None]]] = {}
    for r in rows:
        g = (r.get("grade") or "").strip()
        grade = int(g) if g.isdigit() and 0 <= int(g) <= 3 else None
        by_q.setdefault(r["query_id"], []).append((int(r["rank"]), grade))
    scores: list[float] = []
    top1: list[int] = []
    graded_rows = 0
    for items in by_q.values():
        items.sort(key=lambda t: t[0])
        graded = [g for _, g in items if g is not None]
        graded_rows += len(graded)
        if not graded or len(graded) < len(items):
            continue
        rels = [float(g) for g in graded]
        scores.append(ndcg_at_k(rels, rels, k))
        top1.append(graded[0])
    return HumanNdcg(len(by_q), len(scores), graded_rows,
                     sum(scores) / len(scores) if scores else 0.0,
                     sum(top1) / len(top1) if top1 else 0.0)
