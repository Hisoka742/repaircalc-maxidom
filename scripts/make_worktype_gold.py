"""Build the labeling sheets for the work-type gold set (4 annotators, shared overlap rows).

    uv run python scripts/make_worktype_gold.py [--catalog data/feed/latest.xml.gz]
        [--model data/models/worktypes.joblib] [--n 640] [--ambiguous 90] [--overlap 60]
        [--annotators 4] [--out eval/gold/worktype] [--seed 7]

* STRATIFIED part: `--n` REPAIR products (scope from knowledge/category_work_map.csv) drawn by
  second-level category, quota proportional to sqrt(category size) (every category is
  represented, big ones do not swamp small ones);
* NEGATIVE part: `--negatives` products from out-of-repair departments (garden, kitchenware,
  clothes...), same sqrt stratification over departments: the matcher must say "none" for them;
* AMBIGUOUS part: `--ambiguous` extra products picked by an ambiguity score (many works across
  stages, mixed-purpose categories, rule/model disagreement, name keyword of a work the rules do
  not give, rules without a name keyword), at most 4 per third-level category;
* `--overlap` rows (2/3 stratified, 1/3 ambiguous) are given to EVERY annotator WITHOUT suggestions,
  so agreement is not inflated by anchoring; the other rows are split between annotators with
  the rule suggestion prefilled (confirm with "=", or write the work-type ids, or "none");
* dev / test split by a hash of the SKU (40 % test): the test rows are never used for tuning.

Output: <out>_annotator1.csv ... , <out>_manifest.csv (all rows, who labels what), and the guide
`eval/gold/work_types_guide.csv`.
"""
import argparse
import csv
import hashlib
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import joblib
import yaml

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.feed import is_repair
from maxicalc.catalog.schema import Product
from maxicalc.ml.category_baseline import table as category_table
from maxicalc.ml.worktype_eval import name_has_keyword
from maxicalc.ml.worktypes import KNOW, WorkMatcher, rule_labels

TEST_SHARE = 40
# product families the brief names as ambiguous (screws, primers, tile corners, assembly glue...)
AMBIGUOUS_WORDS = ("саморез|грунт|уголок для плитки|уголки для плитки|клей монтажн|профил|"
                    "пена монтажн|герметик|скотч|лента|дюбел|крепеж|шпагат|нож|шпатель")
# forced quotas: the families the organisers called ambiguous, so they are always in the gold set
FORCED_FAMILIES = {
    "саморез": ("саморез", 9), "грунт": ("грунт", 9),
    "уголки для плитки": ("уголок для плитки|уголки для плитки|уголок.{0,30}плитк", 7),
    "клей монтажный": ("клей монтажн|жидкие гвозди", 9), "профиль": ("профил", 9),
    "пена/герметик": ("пена монтажн|герметик", 8), "дюбель/крепёж": ("дюбел|анкер", 5),
}
MIXED = ("метизы|профили|расходные материалы|клей|герметики|гипсокартон|комплектующие|"
         "инструмент|аксессуары|строительные смеси|пиломатериалы|древесно")
COLUMNS = ["sku", "name", "category", "description", "params", "suggested", "work_types",
           "group", "split", "overlap"]


def in_repair(p: Product) -> bool:
    row = category_table().get(p.characteristics.get("category_id", ""))
    return row.scope == "repair" if row else is_repair(p.category_path)


def split_of(sku: str) -> str:
    h = int(hashlib.sha1(sku.encode(), usedforsecurity=False).hexdigest(), 16) % 100
    return "test" if h < TEST_SHARE else "dev"


def stratified(products: list[Product], n: int, rnd: random.Random,
               repair: bool = True) -> list[int]:
    by: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(products):
        if in_repair(p) is repair:
            by[" > ".join(p.category_path[:2]) or "(без категории)"].append(i)
    weights = {c: math.sqrt(len(v)) for c, v in by.items()}
    total = sum(weights.values())
    chosen: list[int] = []
    for c, idx in sorted(by.items()):
        q = max(1, round(n * weights[c] / total))
        rnd.shuffle(idx)
        chosen += idx[:q]
    rnd.shuffle(chosen)
    return chosen[:n] if len(chosen) > n else chosen


def ambiguity(p: Product, rl: dict, model_set: set[str] | None) -> float:  # type: ignore[type-arg]
    import re

    works = set(rl)
    score = 0.0
    stages = {w for w in works}
    if len(stages) >= 4:
        score += 2
    cat = " > ".join(p.category_path).lower()
    if re.search(MIXED, cat):
        score += 1
    if model_set is not None and model_set != works:
        score += 2
    from maxicalc.ml.worktypes import work_type_ids

    if any(name_has_keyword(p, w) and w not in works for w in work_type_ids()):
        score += 1.5
    if works and not any(name_has_keyword(p, w) for w in works):
        score += 0.5
    if re.search(AMBIGUOUS_WORDS, p.name.lower()):
        score += 1
    return score


def row_of(p: Product, suggested: str, group: str, overlap: bool) -> dict[str, str]:
    desc = p.description.replace("\n", " ")
    params = "; ".join(f"{k}={v}" for k, v in list(p.characteristics.items())[:12])
    return {"sku": p.sku, "name": p.name, "category": " > ".join(p.category_path),
            "description": desc[:300], "params": params[:300],
            "suggested": suggested, "work_types": "", "group": group,
            "split": split_of(p.sku), "overlap": "1" if overlap else "0"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--catalog", default="data/raw/products_final.json")
    ap.add_argument("--model", default=None)
    ap.add_argument("--n", type=int, default=640)
    ap.add_argument("--ambiguous", type=int, default=90)
    ap.add_argument("--negatives", type=int, default=110)
    ap.add_argument("--overlap", type=int, default=60)
    ap.add_argument("--annotators", type=int, default=4)
    ap.add_argument("--out", default="eval/gold/worktype")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    products, _ = load_catalog(a.catalog)
    rl_all = [rule_labels(p) for p in products]
    matcher = WorkMatcher(joblib.load(a.model)) if a.model else None
    strata = stratified(products, a.n, rnd)
    negs = stratified(products, a.negatives, rnd, repair=False)
    taken = set(strata) | set(negs)

    cand = [i for i in range(len(products)) if i not in taken and in_repair(products[i])]
    model_sets: dict[int, set[str]] = {}
    if matcher:
        pool = rnd.sample(cand, min(len(cand), 12000))
        preds = matcher.predict([products[i] for i in pool])
        model_sets = {i: pr.works for i, pr in zip(pool, preds, strict=True)}
        cand = pool
    import re as _re

    forced: list[int] = []
    for _, (rx, quota) in FORCED_FAMILIES.items():
        pool_f = [i for i in cand if _re.search(rx, products[i].name.lower())
                  and i not in forced]
        rnd.shuffle(pool_f)
        forced += pool_f[:quota]
    scored = sorted(cand, key=lambda i: (-ambiguity(products[i], rl_all[i], model_sets.get(i)),
                                         rnd.random()))
    amb: list[int] = list(forced)
    per_leaf: dict[str, int] = defaultdict(int)
    for i in scored:
        if i in forced:
            continue
        leaf = " > ".join(products[i].category_path[:3])
        if per_leaf[leaf] >= 4:
            continue
        per_leaf[leaf] += 1
        amb.append(i)
        if len(amb) >= a.ambiguous:
            break

    strat_rows = [(i, "stratified") for i in strata]
    amb_rows = [(i, "ambiguous") for i in amb]
    neg_rows = [(i, "negative") for i in negs]
    n_amb_ov, n_neg_ov = a.overlap // 4, a.overlap // 6
    ov = (rnd.sample(strat_rows, a.overlap - n_amb_ov - n_neg_ov)
          + rnd.sample(amb_rows, n_amb_ov) + rnd.sample(neg_rows, n_neg_ov))
    ov_ids = {i for i, _ in ov}
    rest = [r for r in strat_rows + amb_rows + neg_rows if r[0] not in ov_ids]
    rnd.shuffle(rest)

    def sugg(i: int) -> str:
        return ";".join(sorted(rl_all[i])) if rl_all[i] else "none"

    sheets: dict[int, list[dict[str, str]]] = {k: [] for k in range(1, a.annotators + 1)}
    manifest: list[dict[str, str]] = []
    for i, g in ov:
        for k in sheets:
            sheets[k].append(row_of(products[i], "", g, True))
        manifest.append({**row_of(products[i], "", g, True), "annotators": "all"})
    for n, (i, g) in enumerate(rest):
        k = n % a.annotators + 1
        sheets[k].append(row_of(products[i], sugg(i), g, False))
        manifest.append({**row_of(products[i], sugg(i), g, False), "annotators": str(k)})
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    for k, rows in sheets.items():
        rnd.shuffle(rows)
        f = out.with_name(f"{out.name}_annotator{k}.csv")
        with f.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
    mf = out.with_name(f"{out.name}_manifest.csv")
    with mf.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[*COLUMNS, "annotators"], delimiter=";")
        w.writeheader()
        w.writerows(manifest)
    tax = yaml.safe_load((KNOW / "taxonomy.yaml").read_text(encoding="utf-8"))
    guide = out.parent / "work_types_guide.csv"
    with guide.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["id", "название", "этап"])
        for wid, v in tax["work_types"].items():
            w.writerow([wid, v["ru"], tax["stages"][v["stage"]]])
    uniq = len({r["sku"] for r in manifest})
    print(f"уникальных товаров {uniq}: stratified {len(strat_rows)} (ремонт), "
          f"ambiguous {len(amb_rows)}, negative {len(neg_rows)}, общих {len(ov)}; на разметчика "
          f"{len(next(iter(sheets.values())))} строк -> {out.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
