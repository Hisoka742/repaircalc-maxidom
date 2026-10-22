"""Eval entrypoint: golden calculations, attribute extraction, catalog matching, recommendation.

Writes eval/REPORT.md (human-readable) and eval/results.json (consumed by
scripts/pitch_metrics.py -> docs/PITCH_METRICS.md). Exit code 1 on any golden deviation,
extraction error, or hard-rule violation on gold labels.
"""
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from maxicalc.golden import load_cases, run_all
from maxicalc.ml.extract_eval import run as run_extraction
from maxicalc.ml.match_eval import run as run_matching
from maxicalc.ml.match_eval import to_markdown as matching_markdown
from maxicalc.recommend import recommend_eval

HERE = Path(__file__).parent
REPORT = HERE / "REPORT.md"
RESULTS = HERE / "results.json"


def _worktype_section() -> list[str]:
    """Work-type matching: REAL numbers only from the human gold set; the held-out-category
    check (labels = rules) is SILVER and is labelled as such."""
    out = ["", "## Work types (multi-label matching of products to repair processes)", ""]
    gold = HERE / "WORKTYPES.md"
    if gold.exists():
        out += gold.read_text(encoding="utf-8").splitlines()
    else:
        out += ["- Human gold set: **not measured** (eval/gold/worktype_gold.csv absent; label the "
                "sheets, run scripts/merge_worktype_gold.py and scripts/eval_worktypes.py)."]
    pilot = HERE / "WORKTYPES_PILOT_c.md"
    if pilot.exists():
        out += ["", "### PILOT: an LLM as the only labeller (NOT human), fresh set C, "
                "category baseline vs product-level matcher (docs/CATEGORY_MAP.md)", ""]
        out += [ln for ln in pilot.read_text(encoding="utf-8").splitlines()[:16]]
    rep = HERE.parent / "out" / "train_worktypes_dump.json"
    if not rep.exists():
        rep = HERE.parent / "out" / "train_worktypes.json"
    if rep.exists():
        import json as _json

        h = _json.loads(rep.read_text(encoding="utf-8"))["holdout"]
        out += ["", f"- SILVER held-out categories ({h['held_categories']} categories never seen "
                f"in training; labels = rules): micro-F1 {h['micro_f1']:.3f}, macro-F1 "
                f"{h['macro_f1']:.3f}, sample-F1 {h['samples_f1']:.3f}, Hamming loss "
                f"{h['hamming_loss']:.4f}; name without the work keyword: F1 "
                f"{h['non_literal']['f1']:.3f} ({int(h['non_literal']['pairs'])} pairs)"]
    else:
        out += ["- Held-out-category check not run (`make reproduce`)."]
    return out


def main() -> int:
    cases = {c["id"]: c for c in load_cases()}
    results = run_all()
    packs = [r for r in results if r.kind == "pack"]
    cont = [r for r in results if r.kind == "continuous"]
    verified = sum(1 for c in cases.values() if c.get("verified"))
    split: dict[str, dict[str, float | int]] = {}
    for label, want in (("manufacturer_verified", True), ("rederived", False)):
        grp = [r for r in results if bool(cases[r.id].get("verified")) is want]
        pk = [r for r in grp if r.kind == "pack" and r.actual is not None]
        ct = [r for r in grp if r.kind == "continuous" and r.actual is not None
              and r.expected != 0]
        split[label] = {
            "cases": len(grp), "packs": len(pk),
            "pack_exact": sum(r.passed for r in pk),
            "mae_packs": float(sum(abs(r.actual - r.expected) for r in pk) / len(pk))  # type: ignore[operator]
            if pk else 0.0,
            "mape_pct": float(sum(abs(r.actual - r.expected) / r.expected for r in ct)  # type: ignore[operator]
                              / len(ct) * 100) if ct else 0.0}
    mape_terms = [abs(r.actual - r.expected) / r.expected
                  for r in cont if r.actual is not None and r.expected != 0]
    mape = float(sum(mape_terms) / len(mape_terms) * 100) if mape_terms else 0.0
    exact = sum(r.passed for r in packs)
    # the brief's accuracy metric: MAE of quantities against reference estimates, in packs
    pack_err = [abs(r.actual - r.expected) for r in packs if r.actual is not None]
    mae_packs = float(sum(pack_err) / len(pack_err)) if pack_err else 0.0
    max_err = float(max(pack_err)) if pack_err else 0.0
    by_calc: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_calc[r.calc].append(r.passed)
    failed = [r for r in results if not r.passed]

    lines = ["# Eval report", "", "## Golden calculation suite", "",
             f"- Cases: {len(results)} (verified against external source: {verified})",
             f"- Pack-count exact match: {exact}/{len(packs)}",
             f"- MAE of pack counts: {mae_packs:.3f} packs (max error {max_err:.0f})",
             f"- MAPE on continuous quantities: {mape:.3f}%",
             "- Split (quote only the first on stage):"]
    for label, s in split.items():
        lines.append(f"  - {label}: {s['cases']} cases; pack exact {s['pack_exact']}/{s['packs']}; "
                     f"MAE {s['mae_packs']:.3f} packs; MAPE {s['mape_pct']:.3f}%")
    lines += [
             "",
             "| calc | passed | total |", "|---|---|---|"]
    lines += [f"| {k} | {sum(v)} | {len(v)} |" for k, v in sorted(by_calc.items())]
    if failed:
        lines += ["", "### Failures"] + [
            f"- {r.id}: expected {r.expected}, got {r.actual} {r.error or ''}" for r in failed]

    ex = run_extraction()
    prec, rec = ex.micro()
    lines += ["", "## Attribute extraction (regex layer)", "",
              f"- Gold cases: {ex.cases} (SYNTHETIC, team-written; not real catalog rows)",
              f"- Micro precision: {prec:.3f}, micro recall: {rec:.3f}", "",
              "| field | precision | recall | tp | wrong | fp | fn |",
              "|---|---|---|---|---|---|---|"]
    lines += [
        f"| {k} | {v.precision:.2f} | {v.recall:.2f} | {v.tp} | {v.wrong} | {v.fp} | {v.fn} |"
        for k, v in sorted(ex.fields.items())
    ]
    if ex.errors:
        lines += ["", "### Extraction errors"] + [f"- {e}" for e in ex.errors]

    matching = run_matching()
    lines += matching_markdown(matching)
    gold_rec, pred_rec = recommend_eval.run()
    lines += recommend_eval.to_markdown(gold_rec, pred_rec)

    lines += recommend_eval.ablation_markdown(recommend_eval.run_ablation())

    lines += _worktype_section()

    graded = HERE / "gold" / "rec_grades.csv"
    if graded.exists():
        from maxicalc.recommend.human_grades import ndcg_from_grades

        hn = ndcg_from_grades(graded)
        lines += ["", "## Recommendation (HUMAN grades 0-3, real catalog)", "",
                  f"- Queries graded in full: {hn.queries_graded}/{hn.queries_total} "
                  f"({hn.graded_rows} rows)",
                  f"- nDCG@5 from human grades: {hn.mean_ndcg:.3f}; mean top-1 grade "
                  f"{hn.mean_grade_top1:.2f}/3"]
    else:
        lines += ["", "## Recommendation (HUMAN grades)", "",
                  "- No graded file at eval/gold/rec_grades.csv: human nDCG not measured"]

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    data = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "golden": {"cases": len(results), "verified": verified, "pack_exact": [exact, len(packs)],
                   "mape_pct": round(mape, 4), "mae_packs": round(mae_packs, 4),
                   "max_pack_error": round(max_err, 4), "failures": len(failed),
                   "split": split},
        "extraction": {"cases": ex.cases, "precision": round(prec, 4), "recall": round(rec, 4),
                       "errors": len(ex.errors)},
        "matching": {
            "items": matching.n_items, "test": matching.n_test,
            "scenarios": [{"name": r.name, "calc_p_at_1": round(r.calc_p_at_1, 4),
                           "coverage": round(r.coverage, 4),
                           "auto_precision": round(r.auto_precision, 4),
                           "work_macro_f1": round(r.macro_f1["work_categories"], 4)}
                          for r in matching.reports]},
        "recommendation": {
            "queries": gold_rec.queries,
            "gold": {"ndcg5": round(gold_rec.mean_ndcg5, 4), "violations": gold_rec.violations,
                     "recommended": gold_rec.returned},
            "pipeline": {"ndcg5": round(pred_rec.mean_ndcg5, 4),
                         "violations": pred_rec.violations, "recommended": pred_rec.returned}},
    }
    RESULTS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(lines))
    # a hard-rule violation on gold labels is a logic bug; fail the eval
    return 1 if failed or ex.errors or gold_rec.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
