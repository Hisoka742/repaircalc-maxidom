"""Draft knowledge/category_work_map.csv: every leaf category of the dump -> work types.

Draft = the category-level subset of the rules (rules without a name condition), scoped by
knowledge/feed_scope.yaml on the lifted path. Rows a person confirmed (`reviewed-human`)
keep their `scope`, `works`, `status` and `note`, so re-running never destroys human review work.
"""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.feed import is_repair
from maxicalc.ml.worktypes import load_rules, rule_labels

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src/maxicalc/knowledge/category_work_map.csv"
REVIEW = ROOT / "src/maxicalc/knowledge/category_map_review.yaml"
COLS = ["category_id", "leaf", "path", "n", "scope", "works", "rules", "status", "note"]


def main() -> int:
    products, _ = load_catalog(ROOT / "data/raw/products_final.json")
    cats: dict[str, list] = {}
    for p in products:
        cats.setdefault(p.characteristics["category_id"], []).append(p)
    old: dict[str, dict[str, str]] = {}
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as f:
            old = {r["category_id"]: r for r in csv.DictReader(f, delimiter=";")}
    review = [(re.compile(e["path"]), e["works"], e.get("note", ""), bool(e.get("rescope")))
              for e in yaml.safe_load(REVIEW.read_text(encoding="utf-8"))["entries"]]
    cat_rules = {r.id for r in load_rules() if r.name is None}
    rows = []
    for cid, ps in sorted(cats.items(), key=lambda x: -len(x[1])):
        rep = ps[0]
        probe = rep.model_copy(update={"name": ""})   # category-level only
        labels = {w: v for w, v in rule_labels(probe, refine=False).items()
                  if set(v[1]) & cat_rules}
        row = {"category_id": cid, "leaf": rep.category_path[-1],
               "path": " > ".join(rep.category_path), "n": str(len(ps)),
               "scope": "repair" if is_repair(rep.category_path) else "none",
               "works": ";".join(f"{w}:{role}" for w, (role, _) in sorted(labels.items())),
               "rules": ",".join(sorted({r for _, rr in labels.values() for r in rr})),
               "status": "auto", "note": ""}
        if not row["works"]:
            low = row["path"].lower().replace("ё", "е")
            for rx, works, note, rescope in review:
                if rescope != (row["scope"] == "none"):
                    continue
                if rx.search(low):
                    if rescope:
                        row["scope"] = "repair"
                    row["works"] = ";".join(f"{w}:{r}" for w, r in works.items())
                    row["status"] = "reviewed-llm"
                    row["note"] = note or ("" if works else "проверено: вне видов работ")
                    break
        prev = old.get(cid)
        if prev and prev["status"] == "reviewed-human":
            row.update({k: prev[k] for k in ("scope", "works", "status", "note")})
        rows.append(row)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    c = Counter((r["scope"], bool(r["works"])) for r in rows)
    print(f"{len(rows)} categories", dict(c), file=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
