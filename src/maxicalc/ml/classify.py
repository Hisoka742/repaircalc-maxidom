"""Trainable multi-label classifier + calibration. Implements the `Scorer` protocol.

Training labels are WEAK (rules over the store's category path / name); dev labels are GOLD and
are used only to calibrate probabilities and to pick per-label acceptance thresholds (target
precision, default 0.95). Never tune on the test split.
"""
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from maxicalc.catalog.schema import Product
from maxicalc.ml.calibrate import Calibrator, pick_threshold
from maxicalc.ml.extract import extract
from maxicalc.ml.match import ModelScores
from maxicalc.ml.rules import apply_rules
from maxicalc.ml.synth import Labels
from maxicalc.ml.taxonomy import load_taxonomy

MULTI = ("work_categories", "room_types", "properties")
ALL_HEADS = (*MULTI, "calc_template")


def weak_labels(products: list[Product]) -> tuple[list[Product], list[Labels]]:
    """Rule-derived labels. Rule-silent and conflicting items are skipped (unlabelled)."""
    kept: list[Product] = []
    out: list[Labels] = []
    for p in products:
        r = apply_rules(p)
        if r.calc_template is None or r.conflict:
            continue
        kept.append(p)
        out.append(Labels(set(r.work_categories), set(r.room_types), set(r.properties),
                          r.calc_template.label))
    return kept, out


def _attr_tokens(p: Product) -> str:
    toks: list[str] = []
    for k, a in extract(p).attrs.items():
        toks.append(f"a_{k}")
        if isinstance(a.value, int | str):
            toks.append(f"a_{k}_{a.value}")
    return " ".join(toks)


class _Features:
    """Name/description char n-grams, category-path words and parsed-attribute tokens."""

    def __init__(self) -> None:
        self.name = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)
        self.cat = TfidfVectorizer(analyzer="word", ngram_range=(1, 2))
        self.attr = TfidfVectorizer(analyzer="word", token_pattern=r"\S+", lowercase=False)

    @staticmethod
    def _texts(ps: list[Product]) -> tuple[list[str], list[str], list[str]]:
        return (
            [f"{p.name} {p.description[:200]}" for p in ps],
            [" ".join(p.category_path) or "_" for p in ps],
            [_attr_tokens(p) or "_" for p in ps],
        )

    def fit_transform(self, ps: list[Product]) -> csr_matrix:
        n, c, a = self._texts(ps)
        return hstack([self.name.fit_transform(n), self.cat.fit_transform(c),
                       self.attr.fit_transform(a)]).tocsr()

    def transform(self, ps: list[Product]) -> csr_matrix:
        n, c, a = self._texts(ps)
        return hstack([self.name.transform(n), self.cat.transform(c),
                       self.attr.transform(a)]).tocsr()


def _with_stripped(
    products: list[Product], labels: list[Labels]
) -> tuple[list[Product], list[Labels]]:
    """Each item plus a copy without its category path (same labels)."""
    stripped = [p.model_copy(update={"category_path": []}) for p in products]
    return [*products, *stripped], [*labels, *labels]


def _label_set(lab: Labels, head: str) -> set[str]:
    s = {"work_categories": lab.work, "room_types": lab.rooms, "properties": lab.props}[head]
    return s - {"any"}  # 'any' is a default applied by the Matcher, never predicted


class MatchModel:
    def __init__(
        self, target_precision: float = 0.95, min_support: int = 5,
        augment_missing_category: bool = True,
    ) -> None:
        self.target_precision = target_precision
        self.min_support = min_support
        # Train AND calibrate on a mix of items with / without the store category path, so the
        # acceptance thresholds stay valid for catalogs whose categories are missing or wrong.
        self.augment_missing_category = augment_missing_category
        self.feat = _Features()
        self.clfs: dict[str, dict[str, LogisticRegression]] = {h: {} for h in MULTI}
        self.cals: dict[str, dict[str, Calibrator]] = {h: {} for h in MULTI}
        self.tau: dict[str, dict[str, float | None]] = {h: {} for h in ALL_HEADS}
        self.calc_clf: LogisticRegression | None = None
        self.calc_cal = Calibrator()

    def fit(
        self, train: list[Product], train_labels: list[Labels],
        dev: list[Product], dev_labels: list[Labels],
    ) -> "MatchModel":
        tax = load_taxonomy()
        if self.augment_missing_category:
            train, train_labels = _with_stripped(train, train_labels)
            dev, dev_labels = _with_stripped(dev, dev_labels)
        x_tr = self.feat.fit_transform(train)
        x_dev = self.feat.transform(dev)
        universe = {"work_categories": tax.work_categories, "room_types": tax.room_types,
                    "properties": tax.properties}
        for head in MULTI:
            for lab in universe[head]:
                if lab == "any":
                    continue
                y = np.array([lab in _label_set(t, head) for t in train_labels], dtype=int)
                if y.sum() < 2 or y.sum() == len(y):
                    continue
                clf = LogisticRegression(C=10.0, class_weight="balanced", max_iter=2000,
                                         solver="liblinear")
                clf.fit(x_tr, y)
                self.clfs[head][lab] = clf
                raw = clf.predict_proba(x_dev)[:, 1]
                y_dev = np.array([lab in _label_set(d, head) for d in dev_labels], dtype=int)
                cal = Calibrator().fit(raw, y_dev)
                self.cals[head][lab] = cal
                self.tau[head][lab] = pick_threshold(
                    cal.transform(raw), y_dev, self.target_precision, self.min_support)

        if len({t.calc for t in train_labels}) >= 2:
            self.calc_clf = LogisticRegression(C=10.0, max_iter=3000)
            self.calc_clf.fit(x_tr, [t.calc for t in train_labels])
            probs = self.calc_clf.predict_proba(x_dev)
            top = probs.max(axis=1)
            pred = self.calc_clf.classes_[probs.argmax(axis=1)]
            correct = (pred == np.array([d.calc for d in dev_labels])).astype(int)
            self.calc_cal.fit(top, correct)
            tau = pick_threshold(self.calc_cal.transform(top), correct, self.target_precision,
                                 self.min_support)
            self.tau["calc_template"] = {str(c): tau for c in self.calc_clf.classes_}
        return self

    def score(self, products: list[Product]) -> list[ModelScores]:
        if not products:
            return []
        x = self.feat.transform(products)
        n = len(products)
        probs: list[dict[str, dict[str, float]]] = [
            {h: {} for h in ALL_HEADS} for _ in range(n)]
        for head in MULTI:
            for lab, clf in self.clfs[head].items():
                cal = self.cals[head][lab].transform(clf.predict_proba(x)[:, 1])
                for i in range(n):
                    probs[i][head][lab] = float(cal[i])
        if self.calc_clf is not None:
            raw = self.calc_clf.predict_proba(x)
            top = raw.max(axis=1)
            cal_top = self.calc_cal.transform(top)
            for i in range(n):
                j = int(raw[i].argmax())
                # keep the other classes' proportions, rescaled to the calibrated remainder
                scale = (1 - cal_top[i]) / max(1 - top[i], 1e-9)
                for k, c in enumerate(self.calc_clf.classes_):
                    probs[i]["calc_template"][str(c)] = (
                        float(cal_top[i]) if k == j else float(min(raw[i][k] * scale, 1.0)))
        return [ModelScores(p, self.tau) for p in probs]

    def save(self, path: Path) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path) -> "MatchModel":
        obj: Any = joblib.load(path)
        if not isinstance(obj, MatchModel):
            raise ValueError("не файл модели MatchModel")
        return obj
