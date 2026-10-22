import math
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LabelScore:
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def support(self) -> int:
        return self.tp + self.fn


@dataclass
class MultilabelScores:
    per_label: dict[str, LabelScore] = field(default_factory=dict)

    @property
    def macro_f1(self) -> float:
        """Mean F1 over labels that occur in gold or predictions."""
        f = [s.f1 for s in self.per_label.values()]
        return sum(f) / len(f) if f else 1.0

    @property
    def micro_f1(self) -> float:
        tp = sum(s.tp for s in self.per_label.values())
        fp = sum(s.fp for s in self.per_label.values())
        fn = sum(s.fn for s in self.per_label.values())
        return LabelScore(tp, fp, fn).f1 if tp + fp + fn else 1.0


def multilabel_scores(gold: Sequence[set[str]], pred: Sequence[set[str]]) -> MultilabelScores:
    if len(gold) != len(pred):
        raise ValueError("gold и pred разной длины")
    labels = set().union(*gold, *pred) if gold else set()
    out = MultilabelScores()
    for lab in sorted(labels):
        tp = sum(lab in g and lab in p for g, p in zip(gold, pred, strict=True))
        fp = sum(lab not in g and lab in p for g, p in zip(gold, pred, strict=True))
        fn = sum(lab in g and lab not in p for g, p in zip(gold, pred, strict=True))
        out.per_label[lab] = LabelScore(tp, fp, fn)
    return out


def coverage_at_precision(auto: Sequence[bool], correct: Sequence[bool]) -> tuple[float, float]:
    """(share auto-accepted, precision among auto-accepted)."""
    n = len(auto)
    accepted = [c for a, c in zip(auto, correct, strict=True) if a]
    cov = len(accepted) / n if n else 0.0
    prec = sum(accepted) / len(accepted) if accepted else 1.0
    return cov, prec


def ndcg_at_k(ranked: Sequence[float], all_relevances: Sequence[float], k: int) -> float:
    """nDCG@k with linear gain. `all_relevances` = relevance of every candidate that exists
    (defines the ideal ranking). Returns 1.0 when nothing relevant exists."""
    def dcg(rels: Sequence[float]) -> float:
        return sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))

    ideal = dcg(sorted(all_relevances, reverse=True))
    return dcg(list(ranked)) / ideal if ideal > 0 else 1.0
