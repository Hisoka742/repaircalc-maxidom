"""Multi-label evaluation for the work-type matcher.

Metrics (sets of work types per product, gold vs predicted):
  micro-F1 (main), macro-F1, per-work-type P/R/F1, sample-based F1, Hamming loss, exact match;
  the same on the ambiguous subset; ranking quality per work type (AP@k, nDCG@k: "which products
  does work X need"); and the "semantic, not literal" subset: gold pairs (product, work) where the
  product NAME contains no keyword of that work (knowledge/work_keywords.yaml).
"""
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import cache

import yaml

from maxicalc.catalog.schema import Product
from maxicalc.ml.worktypes import KNOW, work_type_ids


@dataclass
class ClassScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        d = 2 * self.tp + self.fp + self.fn
        return 2 * self.tp / d if d else 0.0

    @property
    def support(self) -> int:
        return self.tp + self.fn


@dataclass
class MultiLabelReport:
    n: int
    micro_f1: float
    micro_p: float
    micro_r: float
    macro_f1: float
    samples_f1: float
    hamming_loss: float
    exact_match: float
    per_class: dict[str, ClassScore] = field(default_factory=dict)


def evaluate_sets(
    gold: Sequence[set[str]], pred: Sequence[set[str]], classes: Sequence[str] | None = None
) -> MultiLabelReport:
    classes = list(classes or work_type_ids())
    per = {w: ClassScore() for w in classes}
    samples = []
    wrong_cells = 0
    exact = 0
    for g, p in zip(gold, pred, strict=True):
        for w in classes:
            if w in g and w in p:
                per[w].tp += 1
            elif w in p:
                per[w].fp += 1
                wrong_cells += 1
            elif w in g:
                per[w].fn += 1
                wrong_cells += 1
        gi, pi = g & set(classes), p & set(classes)
        d = len(gi) + len(pi)
        samples.append(1.0 if d == 0 else 2 * len(gi & pi) / d)
        exact += gi == pi
    tp = sum(c.tp for c in per.values())
    fp = sum(c.fp for c in per.values())
    fn = sum(c.fn for c in per.values())
    present = [c for c in per.values() if c.support > 0]
    n = len(gold)
    return MultiLabelReport(
        n=n, micro_f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        micro_p=tp / (tp + fp) if tp + fp else 0.0, micro_r=tp / (tp + fn) if tp + fn else 0.0,
        macro_f1=sum(c.f1 for c in present) / len(present) if present else 0.0,
        samples_f1=sum(samples) / n if n else 0.0,
        hamming_loss=wrong_cells / (n * len(classes)) if n else 0.0,
        exact_match=exact / n if n else 0.0, per_class=per)


@cache
def keywords() -> dict[str, tuple[str, ...]]:
    raw = yaml.safe_load((KNOW / "work_keywords.yaml").read_text(encoding="utf-8"))
    return {k: tuple(v) for k, v in raw.items()}


def name_has_keyword(p: Product, work: str) -> bool:
    name = p.name.lower().replace("ё", "е")
    return any(k in name for k in keywords().get(work, ()))


def non_literal_pairs(
    products: Sequence[Product], gold: Sequence[set[str]], pred: Sequence[set[str]]
) -> ClassScore:
    """Pooled TP / FP / FN over (product, work) pairs where the NAME lacks the work's keyword."""
    s = ClassScore()
    for p, g, q in zip(products, gold, pred, strict=True):
        for w in g | q:
            if name_has_keyword(p, w):
                continue
            if w in g and w in q:
                s.tp += 1
            elif w in q:
                s.fp += 1
            else:
                s.fn += 1
    return s


# ------------------------------------------------------------------------------ ranking
def average_precision(relevant: Sequence[bool], k: int) -> float:
    hits = 0
    total = 0.0
    for i, r in enumerate(relevant[:k], 1):
        if r:
            hits += 1
            total += hits / i
    denom = min(sum(relevant), k)
    return total / denom if denom else 0.0


def ndcg(relevant: Sequence[bool], k: int, n_relevant: int) -> float:
    dcg = sum(1 / math.log2(i + 1) for i, r in enumerate(relevant[:k], 1) if r)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(n_relevant, k) + 1))
    return dcg / ideal if ideal else 0.0


@dataclass
class RankingReport:
    k: int
    map_at_k: float
    ndcg_at_k: float
    per_work: dict[str, tuple[float, float]]    # work -> (AP@k, nDCG@k)


def ranking_report(
    gold: Sequence[set[str]], scores: dict[str, list[float]], k: int = 10, min_pos: int = 3
) -> RankingReport:
    """`scores[w][i]` = the matcher's score of product i for work w (higher = needed more)."""
    per: dict[str, tuple[float, float]] = {}
    for w, sc in scores.items():
        rel_all = [w in g for g in gold]
        npos = sum(rel_all)
        if npos < min_pos:
            continue
        order = sorted(range(len(sc)), key=lambda i: -sc[i])
        rel = [rel_all[i] for i in order]
        per[w] = (average_precision(rel, k), ndcg(rel, k, npos))
    n = len(per)
    return RankingReport(k, sum(a for a, _ in per.values()) / n if n else 0.0,
                         sum(b for _, b in per.values()) / n if n else 0.0, per)


def to_markdown(title: str, rep: MultiLabelReport, top_classes: int = 45) -> list[str]:
    L = [f"### {title} (n={rep.n})", "",
         f"- micro-F1 **{rep.micro_f1:.3f}** (P {rep.micro_p:.3f}, R {rep.micro_r:.3f}); "
         f"macro-F1 {rep.macro_f1:.3f}; sample-based F1 {rep.samples_f1:.3f}; "
         f"Hamming loss {rep.hamming_loss:.4f}; exact match {rep.exact_match:.3f}", "",
         "| work type | P | R | F1 | support |", "|---|---|---|---|---|"]
    rows = sorted(rep.per_class.items(), key=lambda kv: -kv[1].support)[:top_classes]
    L += [f"| {w} | {c.precision:.2f} | {c.recall:.2f} | {c.f1:.2f} | {c.support} |"
          for w, c in rows if c.support or c.fp]
    return L
