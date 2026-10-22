"""Attach units to bare numbers of the official dump, by rules in knowledge/dataset_units.yaml.

The original text is kept as "<name> (исходно)" so every normalized value can be audited.
"""
import re
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from maxicalc.catalog.normalize import parse_number

FILE = Path(__file__).resolve().parents[2] / "knowledge" / "dataset_units.yaml"
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_HAS_UNIT = re.compile(r"[а-яa-z]", re.IGNORECASE)


@cache
def _cfg() -> dict[str, Any]:
    return yaml.safe_load(FILE.read_text(encoding="utf-8"))["consumption"]


def _fmt(x: Decimal) -> str:
    return f"{x.normalize():f}".replace(".", ",")


def normalize_consumption(chars: dict[str, str], category: str, name: str) -> str | None:
    """Rewrite chars["Расход материала"] with a unit; returns the rule applied or None."""
    cfg = _cfg()
    raw = chars.get(cfg["key"])
    if not raw or _HAS_UNIT.search(raw):
        return None
    if not re.search(cfg["families"], f"{category} {name}".lower().replace("ё", "е")):
        return None
    nums = [parse_number(m.group(0)) for m in _NUM.finditer(raw)]
    if not nums:
        return None
    top = max(nums)
    if top < Decimal(str(cfg["litres_below"])):
        unit, rule = "л/м2", "<1 -> л/м2"
    elif Decimal(str(cfg["grams_from"])) <= top <= Decimal(str(cfg["max_grams"])):
        unit, rule = "г/м2", ">=10 -> г/м2"
    else:
        return None
    chars[cfg["key"] + " (исходно)"] = raw
    chars[cfg["key"]] = f"{_fmt(top)} {unit}"
    return rule
