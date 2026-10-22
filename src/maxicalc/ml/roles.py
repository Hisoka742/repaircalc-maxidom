"""Product role head: main / accessory / tool / consumable / ppe / other.

Deterministic rules from knowledge/product_roles.yaml (category path + name). Used to keep
accessories (profiles, corners, crosses, fasteners) out of the MAIN product pool of a calculator,
to offer them and protective gear as companions, and to count calculator readiness over main
products only.
"""
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from maxicalc.catalog.schema import Product

FILE = Path(__file__).resolve().parents[1] / "knowledge" / "product_roles.yaml"
ROLES = ("main", "accessory", "tool", "consumable", "ppe", "other")


@dataclass(frozen=True)
class RoleResult:
    role: str
    reason: str


@cache
def _load() -> tuple[list[str], dict[str, list[tuple[re.Pattern[str] | None,
                                                   re.Pattern[str] | None]]], frozenset[str]]:
    raw: dict[str, Any] = yaml.safe_load(FILE.read_text(encoding="utf-8"))
    rules = {}
    for role in raw["order"]:
        rules[role] = [(re.compile(r["cat"]) if r.get("cat") else None,
                        re.compile(r["name"]) if r.get("name") else None) for r in raw[role]]
    return list(raw["order"]), rules, frozenset(raw["main_calcs"])


def main_calcs() -> frozenset[str]:
    return _load()[2]


def _norm(s: str) -> str:
    return s.lower().replace("ё", "е")


def product_role(p: Product) -> RoleResult:
    from maxicalc.ml.category_baseline import table

    row = table().get(p.characteristics.get("category_id", ""))
    if row is not None and row.scope != "repair":
        return RoleResult("other", "категория не относится к ремонту")
    order, rules, _ = _load()
    cat = _norm(" > ".join(p.category_path))
    name = _norm(p.name)
    for role in order:
        for rc, rn in rules[role]:
            if (rc is not None and rc.search(cat)) or (rn is not None and rn.search(name)):
                hit = rc.search(cat) if rc is not None and rc.search(cat) else (
                    rn.search(name) if rn is not None else None)
                return RoleResult(role, f"«{hit.group(0) if hit else ''}»")
    return RoleResult("main", "по умолчанию")
