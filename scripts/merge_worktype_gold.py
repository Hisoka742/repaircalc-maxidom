"""Merge the annotators' sheets into the gold set and compute inter-annotator agreement.

    uv run python scripts/merge_worktype_gold.py [--dir eval/gold] [--prefix worktype]

Cell syntax in `work_types`: ids separated by ";" (e.g. `tile_laying;grouting`), `none` = no work
type applies, `=` = accept the prefilled suggestion, empty = not labelled yet.
Overlap rows (labelled by everybody, no suggestions shown) give the agreement: pairwise Cohen's
kappa (pooled and per work type) and Krippendorff's alpha; their gold label is the strict majority
vote, an exact tie on a work type marks the row `adjudicate` (a human decides, the row stays out of
the gold set until `work_types_final` is filled in the output file).
Writes <dir>/<prefix>_gold.csv and <dir>/AGREEMENT.md.
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from maxicalc.ml.agreement import (
    krippendorff_alpha,
    majority_vote,
    pairwise_kappa,
    per_class_kappa,
)
from maxicalc.ml.worktypes import work_type_ids


def parse_cell(cell: str, suggested: str, valid: set[str]) -> tuple[set[str] | None, str]:
    c = cell.strip().lower().replace(",", ";")
    if not c:
        return None, ""
    if c == "none":
        return set(), ""
    if c == "=":
        return (set() if suggested in ("", "none") else set(suggested.split(";"))), ""
    ids = {x.strip() for x in c.split(";") if x.strip()}
    bad = ids - valid
    return ids - bad, (f"неизвестные виды работ: {sorted(bad)}" if bad else "")


def read_sheet(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dir", default="eval/gold")
    ap.add_argument("--prefix", default="worktype")
    a = ap.parse_args()
    d = Path(a.dir)
    valid = set(work_type_ids())
    sheets = sorted(d.glob(f"{a.prefix}_annotator*.csv"))
    if not sheets:
        print("нет файлов разметчиков")
        return 2
    labels: dict[str, dict[str, set[str]]] = defaultdict(dict)   # sku -> annotator -> set
    meta: dict[str, dict[str, str]] = {}
    problems: list[str] = []
    unlabelled = 0
    for sh in sheets:
        who = sh.stem.split("annotator")[-1]
        for r in read_sheet(sh):
            meta.setdefault(r["sku"], r)
            got, err = parse_cell(r["work_types"], r["suggested"], valid)
            if err:
                problems.append(f"{sh.name} {r['sku']}: {err}")
            if got is None:
                unlabelled += 1
                continue
            labels[r["sku"]][who] = got
    overlap = [s for s, m in meta.items() if m["overlap"] == "1"]
    annotators = sorted({a for v in labels.values() for a in v})
    full_overlap = [s for s in overlap if set(labels[s]) == set(annotators)]
    classes = sorted(valid)
    gold_rows: list[dict[str, str]] = []
    adjudicate = 0
    for sku, m in meta.items():
        votes = list(labels.get(sku, {}).values())
        if not votes:
            continue
        if m["overlap"] == "1":
            if sku not in full_overlap:
                continue
            chosen, ties = majority_vote(votes, classes)
        else:
            chosen, ties = votes[0], set()
        if ties:
            adjudicate += 1
        gold_rows.append({"sku": sku, "works": ";".join(sorted(chosen)) or "none",
                          "split": m["split"], "group": m["group"], "overlap": m["overlap"],
                          "adjudicate": ";".join(sorted(ties)), "work_types_final": ""})
    out = d / f"{a.prefix}_gold.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sku", "works", "split", "group", "overlap",
                                          "adjudicate", "work_types_final"], delimiter=";")
        w.writeheader()
        w.writerows(gold_rows)
    L = ["# Согласованность разметчиков", "",
         f"- Разметчиков: {len(annotators)}; общих строк: {len(overlap)}, размечено всеми: "
         f"{len(full_overlap)}; не заполнено ячеек: {unlabelled}",
         f"- Строк в золотом наборе: {len(gold_rows)}; требуют решения (ничья): {adjudicate}"]
    if len(full_overlap) >= 10 and len(annotators) >= 2:
        sets = {an: [labels[s][an] for s in full_overlap] for an in annotators}
        pk = pairwise_kappa(sets, classes)
        mean_k = sum(pk.values()) / len(pk)
        alpha = krippendorff_alpha(sets, classes)
        pc = per_class_kappa(sets, classes)
        L += [f"- Cohen's kappa (по парам, по всем ячейках): среднее **{mean_k:.3f}** "
              f"(min {min(pk.values()):.3f}, max {max(pk.values()):.3f})",
              f"- Krippendorff's alpha: **{alpha:.3f}**",
              "- Ориентир: >= 0.8 надёжно, 0.67–0.8 условно; ниже — доработать правила разметки.",
              "", "| вид работ | kappa |", "|---|---|"]
        L += [f"| {w} | {k:.2f} |" for w, k in sorted(pc.items(), key=lambda kv: kv[1])]
    else:
        L.append("- Согласованность **не измерена**: нужно >= 10 общих строк, размеченных всеми.")
    if problems:
        L += ["", "## Ошибки в ячейках", *[f"- {p}" for p in problems[:50]]]
    (d / "AGREEMENT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:8]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
