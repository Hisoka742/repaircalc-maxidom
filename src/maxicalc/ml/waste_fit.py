"""Fit the waste coefficients from real purchases (checklist C6, case section 3.3).

Input: one row per order line: layout, required net area (m2), bought area actually used (m2,
packs x pack area). The waste of a row is bought / required - 1. Per layout the coefficient is
the sample mean shrunk toward the default with `PRIOR` pseudo-observations, so a handful of
orders cannot move it far, below `MIN_N` rows it is not touched, and it is clamped to [0, CAP].
Until real orders exist the shipped table is the default one and says so in its `source`.
"""
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from maxicalc.engine.materials.waste import DEFAULT_TABLE, WasteTable

MIN_N = 5
PRIOR = 20
CAP = Decimal("0.5")


@dataclass(frozen=True)
class Order:
    layout: str
    required_m2: Decimal
    bought_m2: Decimal


def fit_table(
    orders: list[Order], base: WasteTable = DEFAULT_TABLE, source: str = ""
) -> WasteTable:
    layouts = dict(base.layouts)
    used: list[str] = []
    for layout, prior in base.layouts.items():
        w = [o.bought_m2 / o.required_m2 - 1 for o in orders
             if o.layout == layout and o.required_m2 > 0 and o.bought_m2 >= o.required_m2]
        n = len(w)
        if n < MIN_N:
            continue
        mean = sum(w, Decimal(0)) / n
        fitted = (n * mean + PRIOR * prior) / (n + PRIOR)
        layouts[layout] = max(Decimal(0), min(CAP, fitted)).quantize(Decimal("0.001"))
        used.append(f"{layout} n={n}")
    src = (f"подогнано по заказам ({', '.join(used)})" if used
           else base.source) + (f"; {source}" if source and used else "")
    return WasteTable(layouts, base.small_room_extra, base.large_format_extra, src,
                      base.small_room_area_m2, base.large_format_side_mm)


def load_orders(path: Path) -> tuple[list[Order], int]:
    """CSV with columns layout, required_m2, bought_m2. Bad rows are counted, not guessed."""
    rows: list[Order] = []
    skipped = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        need = {"layout", "required_m2", "bought_m2"}
        if not rd.fieldnames or not need <= set(rd.fieldnames):
            raise ValueError(f"В файле заказов нужны колонки: {', '.join(sorted(need))}")
        for r in rd:
            try:
                req, got = Decimal(r["required_m2"]), Decimal(r["bought_m2"])
            except (InvalidOperation, TypeError):
                skipped += 1
                continue
            if req <= 0 or got <= 0:
                skipped += 1
                continue
            rows.append(Order(str(r["layout"]).strip(), req, got))
    return rows, skipped


def write_table(t: WasteTable, path: Path) -> None:
    data = {
        "version": 1, "source": t.source,
        "layouts": {k: float(v) for k, v in t.layouts.items()},
        "small_room_extra": float(t.small_room_extra),
        "large_format_extra": float(t.large_format_extra),
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
