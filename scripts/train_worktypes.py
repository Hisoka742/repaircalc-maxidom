"""Train the work-type model on the feed and run the HELD-OUT-CATEGORY reproducibility check.

    uv run python scripts/train_worktypes.py [--catalog data/feed/latest.xml.gz]
        [--out data/models/worktypes.joblib] [--holdout 0.15] [--seed 0] [--report out/train.json]

Steps (each timed, with RAM / CPU): load -> rule labels (weak supervision) -> split by CATEGORY
(a share of leaf categories is held out: the model never sees those categories) -> train ->
evaluate on the held-out categories -> retrain on everything -> save.

The labels here are the RULE labels, so the held-out score is SILVER: it shows that the learned
model reproduces the rules on categories it has never seen (it does not need the rule's keyword),
not that the rules are right. Human gold numbers come from scripts/eval_worktypes.py.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import joblib

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.feed import is_repair
from maxicalc.ml.worktype_eval import evaluate_sets, non_literal_pairs
from maxicalc.ml.worktypes import WorkMatcher, WorkModel, weak_labels
from maxicalc.resources import Stage, machine


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--catalog", default="data/feed/latest.xml.gz")
    ap.add_argument("--out", default="data/models/worktypes.joblib")
    ap.add_argument("--holdout", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--negatives", type=int, default=8000, help="out-of-scope products to include")
    ap.add_argument("--report", default="out/train_worktypes.json")
    a = ap.parse_args()
    stages: dict[str, dict] = {}  # type: ignore[type-arg]

    with Stage("load") as st:
        products, _ = load_catalog(a.catalog)
    st.items = len(products)
    stages["load"] = vars(st).copy()
    with Stage("rules") as st:
        labels = weak_labels(products)
    st.items = len(products)
    stages["rules"] = vars(st).copy()

    rnd = random.Random(a.seed)
    repair_idx = [i for i, p in enumerate(products) if is_repair(p.category_path)]
    other_idx = [i for i, p in enumerate(products) if not is_repair(p.category_path)]
    rnd.shuffle(other_idx)
    keep = repair_idx + other_idx[: a.negatives]

    def leaf(i: int) -> str:
        return " > ".join(products[i].category_path[:3])

    leaves = sorted({leaf(i) for i in keep})
    rnd.shuffle(leaves)
    held = set(leaves[: int(len(leaves) * a.holdout)])
    train_idx = [i for i in keep if leaf(i) not in held]
    test_idx = [i for i in keep if leaf(i) in held]
    print(f"train {len(train_idx)} / held-out {len(test_idx)} products, "
          f"{len(held)} held-out categories of {len(leaves)}")

    with Stage("train_holdout") as st:
        m = WorkModel().fit([products[i] for i in train_idx], [labels[i] for i in train_idx])
    st.items = len(train_idx)
    stages["train_holdout"] = vars(st).copy()
    tp = [products[i] for i in test_idx]
    gold = [labels[i] for i in test_idx]
    with Stage("predict_holdout") as st:
        probs = m.proba(tp)
    st.items = len(tp)
    stages["predict_holdout"] = vars(st).copy()
    pred = [{w for j, w in enumerate(m.classes) if probs[k, j] >= 0.5} for k in range(len(tp))]
    rep = evaluate_sets(gold, pred)
    nl = non_literal_pairs(tp, gold, pred)
    held_result = {
        "micro_f1": rep.micro_f1, "macro_f1": rep.macro_f1, "samples_f1": rep.samples_f1,
        "hamming_loss": rep.hamming_loss, "n": rep.n, "held_categories": len(held),
        "non_literal": {"f1": nl.f1, "precision": nl.precision, "recall": nl.recall,
                        "pairs": nl.support},
        "kind": "SILVER (labels = rules)"}
    print(json.dumps(held_result, ensure_ascii=False, indent=2))

    with Stage("train_full") as st:
        full = WorkModel().fit([products[i] for i in keep], [labels[i] for i in keep])
    st.items = len(keep)
    stages["train_full"] = vars(st).copy()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(full, out)
    with Stage("match_all") as st:
        WorkMatcher(full).predict(products[:5000])
    st.items = 5000
    stages["match_5000"] = vars(st).copy()
    size = out.stat().st_size / 2**20
    report = {"machine": machine(), "stages": {k: {kk: v for kk, v in s.items()
                                                    if not kk.startswith("_")}
                                               for k, s in stages.items()},
              "holdout": held_result, "model_mb": round(size, 1), "products": len(products)}
    Path(a.report).parent.mkdir(parents=True, exist_ok=True)
    Path(a.report).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                              encoding="utf-8")
    print(f"модель {size:.1f} МБ -> {out}; отчёт {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
