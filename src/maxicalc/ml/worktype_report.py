"""Evaluate the work-type matcher on the human gold set and write the markdown section.

Systems compared on the TEST split (thresholds are tuned on DEV only): rules, model alone, and
rules + model (the product). Also: ambiguous subset, "semantic not literal" pairs, per-work
ranking (AP@k / nDCG@k over the gold pool), and the dev score for information.
"""
import csv
from dataclasses import dataclass
from pathlib import Path

from maxicalc.catalog.schema import Product
from maxicalc.ml.category_baseline import baseline_works
from maxicalc.ml.worktype_eval import (
    MultiLabelReport,
    evaluate_sets,
    non_literal_pairs,
    ranking_report,
    to_markdown,
)
from maxicalc.ml.worktypes import WorkMatcher, WorkModel, work_type_ids


@dataclass
class GoldItem:
    product: Product
    works: set[str]
    split: str
    group: str


def load_gold(path: Path, by_sku: dict[str, Product]) -> list[GoldItem]:
    out = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r.get("adjudicate") and not r.get("work_types_final"):
                continue                          # a tie nobody has resolved yet
            p = by_sku.get(r["sku"])
            if p is None:
                continue
            raw = r.get("work_types_final") or r["works"]
            works = set() if raw in ("", "none") else set(raw.split(";"))
            out.append(GoldItem(p, works & set(work_type_ids()), r["split"], r["group"]))
    return out


CATEGORY_BASELINE = "категория (baseline)"


def predict_sets(matcher: WorkMatcher | None, items: list[GoldItem]) -> list[set[str]]:
    """matcher=None is the category baseline: work types of the product's leaf category."""
    if matcher is None:
        return [baseline_works(i.product) for i in items]
    return [pr.works for pr in matcher.predict([i.product for i in items])]


@dataclass
class GoldEval:
    n_test: int
    n_dev: int
    n_ambiguous: int
    systems: dict[str, MultiLabelReport]
    ambiguous: MultiLabelReport | None
    ambiguous_baseline: MultiLabelReport | None
    negatives: dict[str, float]     # share of non-repair products that got a work type, per system
    non_literal: dict[str, float]
    ranking: dict[str, float]
    dev_micro_f1: dict[str, float]


def run_gold_eval(items: list[GoldItem], model: WorkModel | None) -> GoldEval:
    dev = [i for i in items if i.split == "dev"]
    test = [i for i in items if i.split == "test"]
    if model is not None and dev:
        model.tune_thresholds([i.product for i in dev], [i.works for i in dev])   # DEV only
    systems: dict[str, WorkMatcher | None] = {
        CATEGORY_BASELINE: None, "правила": WorkMatcher(None),
        "модель": WorkMatcher(model, use_rules=False), "правила + модель": WorkMatcher(model)}
    if model is None:
        systems = {CATEGORY_BASELINE: None, "правила": systems["правила"]}
    reports: dict[str, MultiLabelReport] = {}
    dev_f1: dict[str, float] = {}
    for name, m in systems.items():
        reports[name] = evaluate_sets([i.works for i in test], predict_sets(m, test))
        if dev:
            dev_f1[name] = evaluate_sets([i.works for i in dev], predict_sets(m, dev)).micro_f1
    main = systems["правила + модель"] if model else systems["правила"]
    amb = [i for i in items if i.group == "ambiguous"]
    amb_rep = evaluate_sets([i.works for i in amb], predict_sets(main, amb)) if amb else None
    amb_base = (evaluate_sets([i.works for i in amb], predict_sets(None, amb)) if amb else None)
    neg = [i for i in items if i.group == "negative"]
    neg_fp = {name: (sum(1 for s_ in predict_sets(m, neg) if s_) / len(neg)) if neg else 0.0
              for name, m in systems.items()}
    nl = non_literal_pairs([i.product for i in test], [i.works for i in test],
                           predict_sets(main, test))
    sc = main.scores([i.product for i in test])
    rk = ranking_report([i.works for i in test], sc, k=10)
    return GoldEval(len(test), len(dev), len(amb), reports, amb_rep, amb_base, neg_fp,
                    {"precision": nl.precision, "recall": nl.recall, "f1": nl.f1,
                     "pairs": float(nl.support)},
                    {"map10": rk.map_at_k, "ndcg10": rk.ndcg_at_k,
                     "works": float(len(rk.per_work))},
                    dev_f1)


def markdown(ev: GoldEval, pilot: bool = False) -> list[str]:
    best = ev.systems.get("правила + модель") or next(iter(ev.systems.values()))
    title = ("## Work types on a PILOT set (single labeller = LLM, NOT human; development use "
             "only)" if pilot else "## Work types on the HUMAN gold set (REAL labels)")
    L = [title, "",
         f"- Test split n={ev.n_test} (never used for tuning); dev n={ev.n_dev}; "
         f"ambiguous rows n={ev.n_ambiguous}", "",
         "| system | micro-F1 | macro-F1 | samples-F1 | Hamming loss | exact match "
         "| dev micro-F1 |",
         "|---|---|---|---|---|---|---|"]
    for name, r in ev.systems.items():
        L.append(f"| {name} | {r.micro_f1:.3f} | {r.macro_f1:.3f} | {r.samples_f1:.3f} | "
                 f"{r.hamming_loss:.4f} | {r.exact_match:.3f} | "
                 f"{ev.dev_micro_f1.get(name, float('nan')):.3f} |")
    verdict = "reached" if best.micro_f1 >= 0.8 else "NOT reached"
    L += ["", f"- Target micro-F1 >= 0.8 (aim 0.9): **{verdict}** ({best.micro_f1:.3f})", ""]
    if ev.ambiguous:
        a = ev.ambiguous
        L += [f"- Ambiguous subset (n={a.n}): micro-F1 {a.micro_f1:.3f}, "
              f"macro-F1 {a.macro_f1:.3f}, exact match {a.exact_match:.3f}"]
        if ev.ambiguous_baseline:
            b = ev.ambiguous_baseline
            L += [f"- Same ambiguous rows, CATEGORY BASELINE: micro-F1 {b.micro_f1:.3f}, "
                  f"macro-F1 {b.macro_f1:.3f}, exact match {b.exact_match:.3f}; product-level "
                  f"matcher gains {a.micro_f1 - b.micro_f1:+.3f} micro-F1 "
                  f"(\"semantic, not literal\" proof)"]
    if any(ev.negatives.values()):
        L += ["- Non-repair negatives that wrongly received a work type: "
              + ", ".join(f"{k} {v * 100:.1f}%" for k, v in ev.negatives.items())]
    nl = ev.non_literal
    L += [f"- Semantic, not literal (name has no keyword of the work; {int(nl['pairs'])} pairs): "
          f"P {nl['precision']:.3f}, R {nl['recall']:.3f}, F1 {nl['f1']:.3f}",
          f"- Ranking per work type (k=10, {int(ev.ranking['works'])} works with >=3 "
          f"positives): MAP@10 {ev.ranking['map10']:.3f}, nDCG@10 {ev.ranking['ndcg10']:.3f}", ""]
    L += to_markdown("Per work type, rules + model, test split", best)
    return L
