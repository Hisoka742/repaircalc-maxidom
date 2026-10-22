"""Leaf category name (the only category info in the official dump) -> full path.

Table built from the Maxidom YML feed's category tree by scripts/build_category_lift.py and
committed (knowledge/category_lift.json) so the dump pipeline does not need the feed. Names
that sit under several parents take the parent with most offers; `lift_ambiguity` tells.
"""
import json
from functools import cache
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "knowledge" / "category_lift.json"


@cache
def _table() -> dict[str, dict[str, object]]:
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}


def lift(leaf: str) -> list[str] | None:
    e = _table().get(leaf.strip().lower())
    return list(e["path"]) if e else None  # type: ignore[call-overload]


def lift_ambiguity(leaf: str) -> int:
    e = _table().get(leaf.strip().lower())
    return int(e["ambiguous"]) if e else 0  # type: ignore[call-overload]
