"""Work-type matching (multi-label): which repair processes does a product serve, in which role.

Two layers:
  * rules (`knowledge/work_rules.yaml`): category path + name -> work types with a role
    (material / tool / consumable). High precision, no learning;
  * a learned model (TF-IDF over name, category, parameters -> one-vs-rest logistic regression),
    trained on the rule labels (weak supervision) and, when it exists, on the human gold set.
    It generalises to products the rules do not cover and to products whose name does not contain
    the work keyword ("semantic, not literal").

`WorkMatcher.predict` returns, per product, every work type with a confidence and the evidence
(rule id or model probability); anything the system is not sure about goes to the review queue.
"""
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier

from maxicalc.catalog.schema import Product

KNOW = Path(__file__).resolve().parents[1] / "knowledge"
ROLES = {"m": "material", "t": "tool", "c": "consumable"}
RULE_CONFIDENCE = 0.97
REVIEW_BAND = (0.30, 0.70)      # model probability band that is sent to a human


@cache
def work_type_ids() -> tuple[str, ...]:
    return tuple(yaml.safe_load((KNOW / "taxonomy.yaml").read_text(encoding="utf-8"))["work_types"])


@cache
def work_type_names() -> dict[str, str]:
    raw = yaml.safe_load((KNOW / "taxonomy.yaml").read_text(encoding="utf-8"))["work_types"]
    return {k: v["ru"] for k, v in raw.items()}


@dataclass(frozen=True)
class Rule:
    id: str
    cat: re.Pattern[str]
    name: re.Pattern[str] | None
    not_name: re.Pattern[str] | None
    works: dict[str, str]
    text: re.Pattern[str] | None = None        # regex over name + description + card values
    not_text: re.Pattern[str] | None = None


@cache
def load_rules(file: str = "work_rules.yaml") -> tuple[Rule, ...]:
    raw = yaml.safe_load((KNOW / file).read_text(encoding="utf-8"))["rules"]
    ids = set(work_type_ids())
    out = []
    for r in raw:
        bad = set(r["works"]) - ids
        if bad or not set(r["works"].values()) <= set(ROLES):
            raise ValueError(f"правило {r['id']}: неизвестный вид работ или роль: {bad}")
        out.append(Rule(r["id"], re.compile(r["cat"]),
                        re.compile(r["name"]) if r.get("name") else None,
                        re.compile(r["not_name"]) if r.get("not_name") else None, r["works"],
                        re.compile(r["text"]) if r.get("text") else None,
                        re.compile(r["not_text"]) if r.get("not_text") else None))
    return tuple(out)


def _norm(s: str) -> str:
    return s.lower().replace("ё", "е")


@dataclass
class WorkHit:
    work: str
    role: str                 # material | tool | consumable
    confidence: float
    source: str               # rule | model
    evidence: str             # rule id(s) or "p=0.83"


@dataclass
class WorkPrediction:
    sku: str
    hits: dict[str, WorkHit] = field(default_factory=dict)
    review: bool = False
    review_reason: str = ""

    @property
    def works(self) -> set[str]:
        return set(self.hits)


def _apply(rules: tuple[Rule, ...], cat: str, name: str, text: str = "",
           matched: list[str] | None = None) -> dict[str, tuple[str, list[str]]]:
    found: dict[str, tuple[str, list[str]]] = {}
    order = {"m": 0, "t": 1, "c": 2}
    for r in rules:
        if not r.cat.search(cat):
            continue
        if r.name is not None and not r.name.search(name):
            continue
        if r.not_name is not None and r.not_name.search(name):
            continue
        if r.text is not None and not r.text.search(text):
            continue
        if r.not_text is not None and r.not_text.search(text):
            continue
        if matched is not None:
            matched.append(r.id)
        for w, role in r.works.items():
            cur = found.get(w)
            if cur is None:
                found[w] = (role, [r.id])
            else:
                best = min((cur[0], role), key=lambda x: order[x])
                found[w] = (best, [*cur[1], r.id])
    return found


def rule_labels(p: Product, refine: bool = True) -> dict[str, tuple[str, list[str]]]:
    """work -> (role, [rule ids]) for one product. Role priority: material > tool > consumable.

    Category rules give the union over matching rules; when a PRODUCT-LEVEL refinement matches
    (knowledge/work_refine.yaml) it is exclusive: only the refinement's works are returned."""
    cat = _norm(" > ".join(p.category_path))
    name = _norm(p.name)
    text = _norm(" ".join([p.name, p.description, *p.characteristics.values()]))
    if refine:
        hit: list[str] = []
        refined = _apply(load_rules("work_refine.yaml"), cat, name, text, hit)
        if hit:           # a refinement may deliberately say "no work" (works: {})
            return refined
    found = _apply(load_rules(), cat, name, text)
    if not found and refine:
        # no rule: fall back to the reviewed category map (never below the category baseline)
        from maxicalc.ml.category_baseline import table

        row = table().get(p.characteristics.get("category_id", ""))
        if row and row.status.startswith("reviewed"):
            return {w: (r, ["catmap"]) for w, r in row.works.items()}
    return found


_PARAM_KEEP = 12


def product_text(p: Product) -> tuple[str, str]:
    """(free text, structured text): name+description, and category / parameter names."""
    chars = [f"{k}={v}" for k, v in list(p.characteristics.items())[:_PARAM_KEEP]
             if len(v) < 40 and k not in ("Артикул",)]
    struct = " ".join([" ".join(p.category_path), " ".join(chars)])
    return _norm(f"{p.name} {p.brand or ''}"), _norm(struct)


class WorkModel:
    """TF-IDF + one-vs-rest logistic regression with per-class thresholds."""

    def __init__(self, c: float = 20.0) -> None:
        self.c = c
        self.vec_name = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3,
                                        max_features=250_000, sublinear_tf=True)
        self.vec_word = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2,
                                        max_features=150_000, sublinear_tf=True,
                                        token_pattern=r"(?u)\b[\w=/\.,+-]{2,}\b")
        self.clf: OneVsRestClassifier | None = None
        self.classes: list[str] = []
        self.thresholds: dict[str, float] = {}

    def _x(self, products: list[Product], fit: bool = False) -> Any:
        texts = [product_text(p) for p in products]
        a = [t[0] for t in texts]
        b = [t[1] for t in texts]
        if fit:
            return hstack([self.vec_name.fit_transform(a), self.vec_word.fit_transform(b)]).tocsr()
        return hstack([self.vec_name.transform(a), self.vec_word.transform(b)]).tocsr()

    def fit(self, products: list[Product], labels: list[set[str]]) -> "WorkModel":
        self.classes = [w for w in work_type_ids() if any(w in s for s in labels)]
        y = np.array([[w in s for w in self.classes] for s in labels], dtype=np.int8)
        x = self._x(products, fit=True)
        x.sum_duplicates()
        x.sort_indices()        # joblib memory-maps x read-only: it must already be canonical
        self.clf = OneVsRestClassifier(
            LogisticRegression(C=self.c, solver="liblinear", class_weight="balanced"),
            n_jobs=-1).fit(x, y)
        self.thresholds = {w: 0.5 for w in self.classes}
        return self

    def proba(self, products: list[Product]) -> np.ndarray:
        assert self.clf is not None
        return np.asarray(self.clf.predict_proba(self._x(products)))

    def tune_thresholds(self, products: list[Product], labels: list[set[str]]) -> None:
        """Per-class threshold maximising F1 on a DEV set (never on test)."""
        pr = self.proba(products)
        for j, w in enumerate(self.classes):
            y = np.array([w in s for s in labels])
            if y.sum() < 3:
                continue
            best_t, best_f = self.thresholds[w], -1.0
            for t in np.arange(0.2, 0.91, 0.05):
                pred = pr[:, j] >= t
                tp = int((pred & y).sum())
                f = 2 * tp / max(1, int(pred.sum()) + int(y.sum()))
                if f > best_f:
                    best_t, best_f = float(t), f
            self.thresholds[w] = best_t


class WorkMatcher:
    """`use_rules=False` gives the model alone (an ablation); `model=None` the rules alone;
    `fill_gaps_only=False` restores "rules + everything the model adds"."""

    def __init__(self, model: WorkModel | None = None, use_rules: bool = True,
                 fill_gaps_only: bool = True) -> None:
        self.model = model
        self.use_rules = use_rules
        # a rule match is trusted: the model then only flags disagreement for review and adds
        # nothing; it supplies the work types of products no rule covers
        self.fill_gaps_only = fill_gaps_only

    def scores(self, products: list[Product]) -> dict[str, list[float]]:
        """Score of every work type for every product (rule = 0.97, else model probability)."""
        n = len(products)
        out: dict[str, list[float]] = {w: [0.0] * n for w in work_type_ids()}
        if self.model is not None:
            pr = self.model.proba(products)
            for j, w in enumerate(self.model.classes):
                out[w] = [float(v) for v in pr[:, j]]
        if self.use_rules:
            for i, p in enumerate(products):
                for w in rule_labels(p):
                    out[w][i] = max(out[w][i], RULE_CONFIDENCE)
        return out

    def predict(self, products: list[Product]) -> list[WorkPrediction]:
        probs = self.model.proba(products) if self.model else None
        out: list[WorkPrediction] = []
        for i, p in enumerate(products):
            pred = WorkPrediction(p.sku)
            rl = rule_labels(p) if self.use_rules else {}
            for w, (role, ids) in rl.items():
                pred.hits[w] = WorkHit(w, ROLES[role], RULE_CONFIDENCE, "rule", ",".join(ids))
            if probs is not None and self.model is not None:
                for j, w in enumerate(self.model.classes):
                    pr = float(probs[i, j])
                    thr = self.model.thresholds.get(w, 0.5)
                    if rl and self.fill_gaps_only:
                        break
                    if w not in pred.hits and pr >= thr:
                        pred.hits[w] = WorkHit(w, "material", pr, "model", f"p={pr:.2f}")
                lo, hi = REVIEW_BAND
                if not rl:
                    top = float(probs[i].max())
                    if lo <= top < hi or (top >= hi and pred.hits):
                        pred.review = True
                        pred.review_reason = f"нет правила, уверенность модели {top:.2f}"
                else:
                    miss = [w for w in rl if w in self.model.classes
                            and probs[i, self.model.classes.index(w)] < 0.10]
                    if len(miss) >= max(2, len(rl) // 2):
                        pred.review = True
                        pred.review_reason = "правило и модель расходятся"
            out.append(pred)
        return out


def weak_labels(products: list[Product]) -> list[set[str]]:
    return [set(rule_labels(p)) for p in products]
