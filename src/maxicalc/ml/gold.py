"""Gold-set tooling (checklist G2): stratified sample to label, stable dev/test split, scoring.

The gold set is hand-verified by the team: `sample_for_labeling` produces the CSV with the
prediction pre-filled (so a human only confirms or corrects), `score_gold` turns the verified
CSV into per-class precision/recall/F1. Never tune thresholds on the `test` rows.
"""
import csv
import hashlib
import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from maxicalc.catalog.schema import Product

TEST_SHARE_PCT = 40


def split_of(sku: str) -> str:
    """Stable split from the SKU alone: the same product is always in the same part."""
    h = int(hashlib.sha1(sku.encode(), usedforsecurity=False).hexdigest(), 16) % 100
    return "test" if h < TEST_SHARE_PCT else "dev"


@dataclass(frozen=True)
class GoldRow:
    sku: str
    name: str
    category: str
    predicted_calc: str
    split: str


def sample_for_labeling(
    products: list[Product], predict: Callable[[Product], str], n: int = 800, seed: int = 0
) -> list[GoldRow]:
    """Stratified by predicted type: every type gets a fair share, big types do not swamp small."""
    rnd = random.Random(seed)
    by: dict[str, list[Product]] = defaultdict(list)
    for p in products:
        by[predict(p)].append(p)
    for v in by.values():
        rnd.shuffle(v)
    chosen: list[tuple[str, Product]] = []
    quota = max(1, n // max(1, len(by)))
    for cls, lst in sorted(by.items()):
        chosen += [(cls, p) for p in lst[:quota]]
    # top up from the leftovers, largest classes first, until n
    left = [(cls, p) for cls, lst in sorted(by.items()) for p in lst[quota:]]
    rnd.shuffle(left)
    chosen += left[: max(0, n - len(chosen))]
    return [GoldRow(p.sku, p.name, " > ".join(p.category_path), cls, split_of(p.sku))
            for cls, p in chosen[:n]]


def write_labeling_csv(rows: list[GoldRow], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["sku", "name", "category", "predicted_calc", "verified_calc", "split"])
        for r in rows:
            w.writerow([r.sku, r.name, r.category, r.predicted_calc, "", r.split])


@dataclass(frozen=True)
class ClassScore:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class GoldReport:
    verified: int
    skipped: int
    accuracy: float
    macro_f1: float
    per_class: dict[str, ClassScore]


def score_gold(path: Path, delimiter: str | None = None) -> GoldReport:
    text = path.read_text(encoding="utf-8-sig")
    delim = delimiter or (";" if text.split("\n", 1)[0].count(";") else ",")
    rows = list(csv.DictReader(text.splitlines(), delimiter=delim))
    pairs = [(r["predicted_calc"].strip(), r["verified_calc"].strip()) for r in rows
             if r.get("verified_calc", "").strip()]
    skipped = len(rows) - len(pairs)
    classes = sorted({t for _, t in pairs} | {p for p, _ in pairs})
    per: dict[str, ClassScore] = {}
    for c in classes:
        tp = sum(1 for p, t in pairs if p == c and t == c)
        fp = sum(1 for p, t in pairs if p == c and t != c)
        fn = sum(1 for p, t in pairs if p != c and t == c)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        per[c] = ClassScore(pr, rc, f1, tp + fn)
    supported = [s.f1 for s in per.values() if s.support > 0]
    acc = sum(1 for p, t in pairs if p == t) / len(pairs) if pairs else 0.0
    return GoldReport(len(pairs), skipped, acc,
                      sum(supported) / len(supported) if supported else 0.0, per)
