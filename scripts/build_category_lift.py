"""Leaf category name -> full path, lifted from the YML feed's category tree.

The official dump has exactly one leaf name per product and no tree, but the rules, the scope file
and the taxonomy all speak in paths. The feed (same shop) has the tree: this writes
src/maxicalc/knowledge/category_lift.json = {leaf name (lower): {"path": [...], "ambiguous": n}}.
A name that sits under several parents takes the parent with the most offers in the feed.
"""
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cats: dict[str, tuple[str, str | None]] = {}
    offers: Counter[str] = Counter()
    with gzip.open(ROOT / "data/feed/latest.xml.gz", "rb") as f:
        for _, el in etree.iterparse(f, tag=("category", "offer"), recover=True, huge_tree=True):
            if el.tag == "category":
                cats[el.get("id")] = ((el.text or "").strip(), el.get("parentId"))
            else:
                cid = el.findtext("categoryId")
                if cid:
                    offers[cid] += 1
            el.clear()

    def path(i: str) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        while i and i in cats and i not in seen:
            seen.add(i)
            out.append(cats[i][0])
            i = cats[i][1]
        return out[::-1]

    by_name: dict[str, list[str]] = defaultdict(list)
    for i, (name, _) in cats.items():
        by_name[name.lower()].append(i)
    lift = {}
    for name, ids in by_name.items():
        best = max(ids, key=lambda i: (offers[i], -int(i) if i.isdigit() else 0))
        lift[name] = {"path": path(best), "ambiguous": len(ids) - 1}
    out = ROOT / "src/maxicalc/knowledge/category_lift.json"
    out.write_text(json.dumps(lift, ensure_ascii=False, indent=0, sort_keys=True),
                   encoding="utf-8")
    amb = sum(1 for v in lift.values() if v["ambiguous"])
    print(f"{len(lift)} names, {amb} ambiguous -> {out}")


if __name__ == "__main__":
    main()
