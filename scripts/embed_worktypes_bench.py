"""Benchmark embedding models for the work-type task on CPU (held-out categories, silver labels).

    PYTHONPATH=data/stlibs uv run python scripts/embed_worktypes_bench.py \
        st:intfloat/multilingual-e5-small st:intfloat/multilingual-e5-base st:BAAI/bge-m3 \
        [--n 12000] [--out out/embed_worktypes.json]

For each model: encode a stratified subsample (seconds, products/s, peak RAM), train a one-vs-rest
logistic regression on the embeddings alone and on embeddings + TF-IDF, score micro-F1 on
categories held out of training. Labels are the rule labels (SILVER); the point is to compare
models and to choose what the laptop can afford, not to certify accuracy.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.feed import is_repair
from maxicalc.ml.embed import Embedder, SentenceTransformerEmbedder
from maxicalc.ml.worktype_eval import evaluate_sets
from maxicalc.ml.worktypes import WorkModel, product_text, weak_labels, work_type_ids
from maxicalc.resources import Stage, machine


def build(spec: str) -> Embedder:
    if spec.startswith("st:"):
        name = spec[3:]
        prefix = "passage: " if "e5" in name else None
        return SentenceTransformerEmbedder(name, prefix=prefix)
    raise ValueError(f"неизвестный эмбеддер {spec}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--catalog", default="data/feed/latest.xml.gz")
    ap.add_argument("--n", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="out/embed_worktypes.json")
    a = ap.parse_args()
    products, _ = load_catalog(a.catalog)
    rnd = random.Random(a.seed)
    idx = [i for i, p in enumerate(products) if is_repair(p.category_path)]
    rnd.shuffle(idx)
    idx = idx[: a.n]
    leaves = sorted({" > ".join(products[i].category_path[:3]) for i in idx})
    rnd.shuffle(leaves)
    held = set(leaves[: int(len(leaves) * 0.2)])
    tr = [i for i in idx if " > ".join(products[i].category_path[:3]) not in held]
    te = [i for i in idx if " > ".join(products[i].category_path[:3]) in held]
    labels = weak_labels(products)
    classes = [w for w in work_type_ids() if any(w in labels[i] for i in tr)]
    ytr = np.array([[w in labels[i] for w in classes] for i in tr], dtype=np.int8)
    gold = [labels[i] for i in te]
    print(f"{len(tr)} train / {len(te)} held-out products, {len(held)} held-out categories")

    def fit_eval(xtr, xte):  # type: ignore[no-untyped-def]
        clf = OneVsRestClassifier(LogisticRegression(C=10, solver="liblinear",
                                                     class_weight="balanced"),
                                  n_jobs=4).fit(xtr, ytr)
        pr = clf.predict_proba(xte)
        return evaluate_sets(gold, [{w for j, w in enumerate(classes) if pr[k, j] >= 0.5}
                                    for k in range(len(te))]).micro_f1

    tfidf = WorkModel()
    xtr_t = tfidf._x([products[i] for i in tr], fit=True)
    xte_t = tfidf._x([products[i] for i in te])
    xtr_t.sum_duplicates(); xtr_t.sort_indices()            # noqa: E702
    results: dict[str, dict] = {"tfidf": {"micro_f1": fit_eval(xtr_t, xte_t)}}  # type: ignore[type-arg]
    print(f"{'tfidf':45} micro-F1 {results['tfidf']['micro_f1']:.3f}")
    for spec in a.models:
        try:
            emb = build(spec)
            texts = [". ".join(product_text(products[i])) for i in tr + te]
            with Stage(spec) as st:
                m = emb.encode(texts)
            st.items = len(texts)
        except Exception as e:
            print(f"{spec:45} пропущена: {str(e)[:80]}")
            results[spec] = {"error": str(e)[:200]}
            continue
        mtr, mte = m[: len(tr)], m[len(tr):]
        f_emb = fit_eval(mtr, mte)
        f_both = fit_eval(hstack([xtr_t, csr_matrix(mtr)]).tocsr(),
                          hstack([xte_t, csr_matrix(mte)]).tocsr())
        results[spec] = {"micro_f1_embedding": f_emb, "micro_f1_embedding_plus_tfidf": f_both,
                         "encode_seconds": st.seconds,
                         "products_per_second": len(texts) / st.seconds,
                         "peak_rss_mb": st.peak_rss_mb, "dim": int(m.shape[1])}
        print(f"{spec:45} emb {f_emb:.3f}  emb+tfidf {f_both:.3f}  "
              f"{len(texts) / st.seconds:6.1f} шт/с  RAM {st.peak_rss_mb:.0f} МБ")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"machine": machine(), "n_train": len(tr), "n_test": len(te),
                                       "results": results}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
