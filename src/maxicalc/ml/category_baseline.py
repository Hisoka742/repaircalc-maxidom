"""Category -> work types lookup: the BASELINE the product-level matcher must beat.

knowledge/category_work_map.csv has one row per leaf category of the official dump
(category_id; leaf; path; n; scope; works; rules; status; note). `works` is `id:role;id:role`,
empty = the category is not part of repair ("none"). The table is a draft (rules + model
assisted) plus human review; `status` says which rows a person confirmed.
"""
import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from maxicalc.catalog.schema import Product

FILE = Path(__file__).resolve().parents[1] / "knowledge" / "category_work_map.csv"


@dataclass(frozen=True)
class CategoryRow:
    category_id: str
    leaf: str
    path: str
    n: int
    scope: str            # repair | none
    works: dict[str, str]  # work id -> role
    rules: str
    status: str           # auto | reviewed-llm | reviewed-human
    note: str


def _parse_works(s: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in filter(None, (x.strip() for x in s.split(";"))):
        w, _, role = part.partition(":")
        out[w] = role or "m"
    return out


@cache
def table() -> dict[str, CategoryRow]:
    out: dict[str, CategoryRow] = {}
    with FILE.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            out[r["category_id"]] = CategoryRow(
                r["category_id"], r["leaf"], r["path"], int(r["n"] or 0), r["scope"],
                _parse_works(r["works"]), r["rules"], r["status"], r["note"])
    return out


def baseline_works(p: Product) -> set[str]:
    """Work types of the product's category (empty set = not repair)."""
    row = table().get(p.characteristics.get("category_id", ""))
    return set(row.works) if row else set()
