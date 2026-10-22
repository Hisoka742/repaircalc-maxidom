"""Golden-case runner shared by pytest and eval. Not part of engine/ (reads files)."""
import os
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from maxicalc.engine.geometry import Opening, Room
from maxicalc.engine.materials import (
    coatings,
    flooring,
    skirting,
    tile,
    wallpaper,
    waterproofing,
)
from maxicalc.engine.packaging import Pack, optimal_cover
from maxicalc.engine.units import d

GOLDEN_FILE = Path(__file__).resolve().parents[2] / "tests" / "golden" / "golden_cases.yaml"
# independent re-derivations written by scripts/make_golden.py (not manufacturer references)
GENERATED_FILE = GOLDEN_FILE.with_name("golden_generated.yaml")
# figures read from manufacturer technical data sheets, each with URL, inputs and the quote
MANUFACTURER_FILE = GOLDEN_FILE.with_name("golden_manufacturer.yaml")
# cases the team filled from manufacturers' online calculators (scripts/import_references.py)
IMPORTED_FILE = GOLDEN_FILE.with_name("golden_imported.yaml")


def _room(i: dict[str, Any]) -> Room:
    ops = [Opening(o["kind"], d(o["w"]), d(o["h"]), o["wall"]) for o in i.get("openings", [])]
    return Room.rectangle(i["length"], i["width"], i["height"], ops)


def _wallpaper(i: dict[str, Any]) -> Decimal:
    return wallpaper.rolls(
        _room(i), i["roll_width"], i["roll_length"], i.get("rapport", 0),
        i.get("match", "straight"), i.get("trim", "0.1"), i.get("reserve", 0)).value


def _paint(i: dict[str, Any]) -> Decimal:
    return coatings.liters_by_spread(
        i["area"], i["spread"], i.get("layers", 2), i.get("porous", False)).value


def _putty_bags(i: dict[str, Any]) -> Decimal:
    kg = coatings.kg_by_thickness(i["area"], i["thickness_mm"], i["rate"]).value
    return coatings.packs(kg, i["bag_kg"]).value


def _tile_packs(i: dict[str, Any]) -> Decimal:
    a = tile.area_with_waste(i["area"], i["layout"], i["tile_w"], i["tile_h"]).value
    return tile.packs(a, i.get("m2_per_pack"), i.get("pcs_per_pack"),
                      i["tile_w"], i["tile_h"]).value


def _grout_kg(i: dict[str, Any]) -> Decimal:
    return tile.grout_kg(i["area"], i["tile_w"], i["tile_h"], i["thickness"], i["joint"],
                         i.get("density", "1.6")).value


def _adhesive_kg(i: dict[str, Any]) -> Decimal:
    return tile.adhesive_kg(i["area"], i["tile_w"], i["tile_h"], i.get("kg_per_m2"),
                            i.get("table", "cm11")).value


def _grout_table_kg(i: dict[str, Any]) -> Decimal:
    r = tile.grout_table_kg(i["area"], i["tile_w"], i["tile_h"], i["joint"], i.get("table", "ce40"))
    if r is None:
        raise ValueError("плитка и шов не совпадают со строкой таблицы производителя")
    return r.value


def _primer_packs(i: dict[str, Any]) -> Decimal:
    v = coatings.liters_by_consumption(i["area"], i["l_per_m2"], i.get("layers", 1)).value
    return coatings.packs(v, i["can_l"]).value


def _paint_packs(i: dict[str, Any]) -> Decimal:
    v = coatings.liters_by_spread(i["area"], i["spread"], i.get("layers", 1)).value
    return coatings.packs(v, i["can_l"]).value


def _waterproofing_kg(i: dict[str, Any]) -> Decimal:
    return waterproofing.kg(i["area"], i["condition"], i.get("kg_per_m2")).value


def _layer_kg(i: dict[str, Any]) -> Decimal:
    return coatings.kg_by_thickness(i["area"], i["thickness_mm"], i["rate"]).value


def _laminate_packs(i: dict[str, Any]) -> Decimal:
    a = flooring.area_with_waste(i["area"], i.get("layout", "straight")).value
    return flooring.packs(a, i["m2_per_pack"]).value


def _skirting(i: dict[str, Any]) -> Decimal:
    return skirting.pieces(_room(i), i.get("piece_len", "2.5")).value


def _pack_cost(i: dict[str, Any]) -> Decimal:
    packs = [Pack(p["sku"], d(p["size"]), d(p["price"])) for p in i["packs"]]
    return optimal_cover(d(i["required"]), packs).total_cost


CALCS: dict[str, Callable[[dict[str, Any]], Decimal]] = {
    "wallpaper_rolls": _wallpaper, "paint_liters": _paint, "putty_bags": _putty_bags,
    "tile_packs": _tile_packs, "grout_kg": _grout_kg, "laminate_packs": _laminate_packs,
    "skirting_pieces": _skirting, "pack_cost": _pack_cost, "adhesive_kg": _adhesive_kg,
    "waterproofing_kg": _waterproofing_kg, "layer_kg": _layer_kg,
    "grout_table_kg": _grout_table_kg, "primer_packs": _primer_packs,
    "paint_packs": _paint_packs,
}


@dataclass(frozen=True)
class CaseResult:
    id: str
    calc: str
    kind: str
    expected: Decimal
    actual: Decimal | None
    passed: bool
    error: str | None = None


def run_case(case: dict[str, Any]) -> CaseResult:
    exp = d(case["expected"])
    tol = d(case.get("tolerance", 0))
    try:
        act = CALCS[case["calc"]](case["inputs"])
    except Exception as e:  # report, don't crash the suite
        return CaseResult(case["id"], case["calc"], case["kind"], exp, None, False, repr(e))
    return CaseResult(case["id"], case["calc"], case["kind"], exp, act, abs(act - exp) <= tol)


def load_cases(path: Path = GOLDEN_FILE) -> list[dict[str, Any]]:
    """Built-in golden cases plus, if GOLDEN_EXTRA points at a file, the organisers' reference
    values (same format). A set GOLDEN_EXTRA that does not exist is an error, not silence."""
    cases = list(yaml.safe_load(path.read_text(encoding="utf-8"))["cases"])
    if path == GOLDEN_FILE:
        for extra_file in (GENERATED_FILE, MANUFACTURER_FILE, IMPORTED_FILE):
            if extra_file.exists():
                cases += list(yaml.safe_load(extra_file.read_text(encoding="utf-8"))["cases"])
    extra = os.environ.get("GOLDEN_EXTRA")
    if extra:
        cases += list(yaml.safe_load(Path(extra).read_text(encoding="utf-8"))["cases"])
    seen: set[str] = set()
    for c in cases:
        if c["id"] in seen:
            raise ValueError(f"Повторяющийся id эталонного случая: {c['id']}")
        seen.add(c["id"])
    return cases


def run_all(path: Path = GOLDEN_FILE) -> list[CaseResult]:
    return [run_case(c) for c in load_cases(path)]
