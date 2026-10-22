"""Product-type classification on top of embeddings, and the benchmark that compares embedders."""
import time
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

from maxicalc.catalog.schema import Product
from maxicalc.ml.embed import Embedder, product_text
from maxicalc.ml.synth import SynthItem


@dataclass
class EmbeddingClassifier:
    embedder: Embedder
    model: LogisticRegression

    def predict(self, products: list[Product]) -> list[str]:
        x = self.embedder.encode([product_text(p) for p in products])
        return [str(c) for c in self.model.predict(x)]

    def predict_proba(self, products: list[Product]) -> tuple[list[str], np.ndarray]:
        x = self.embedder.encode([product_text(p) for p in products])
        return [str(c) for c in self.model.classes_], self.model.predict_proba(x)


def fit_embedding_classifier(
    embedder: Embedder, products: list[Product], labels: list[str]
) -> EmbeddingClassifier:
    x = embedder.encode([product_text(p) for p in products])
    clf = LogisticRegression(max_iter=1000, C=10.0)
    clf.fit(x, labels)
    return EmbeddingClassifier(embedder, clf)


@dataclass(frozen=True)
class EmbedReport:
    macro_f1: float
    accuracy: float
    n_test: int
    seconds: float


def benchmark(
    embedders: dict[str, Embedder], train: list[SynthItem], test: list[SynthItem]
) -> dict[str, EmbedReport]:
    """Macro-F1 of the product-type classifier per embedder (train on `train`, score on `test`)."""
    out: dict[str, EmbedReport] = {}
    y_tr = [i.gold.calc for i in train]
    y_te = [i.gold.calc for i in test]
    for name, emb in embedders.items():
        t0 = time.perf_counter()
        clf = fit_embedding_classifier(emb, [i.product for i in train], y_tr)
        pred = clf.predict([i.product for i in test])
        out[name] = EmbedReport(
            float(f1_score(y_te, pred, average="macro", zero_division=0)),
            float(accuracy_score(y_te, pred)), len(test), round(time.perf_counter() - t0, 2))
    return out
