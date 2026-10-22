"""Loads knowledge/*.yaml into engine types. Lives outside engine/ because it reads files."""
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from maxicalc.engine.corrections import Correction, CorrectionTable, Source
from maxicalc.engine.electrical import RoomNorms
from maxicalc.engine.labor import Spread, WorkRate
from maxicalc.engine.materials.waste import WasteTable
from maxicalc.engine.units import d

HERE = Path(__file__).parent


def _load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((HERE / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@cache
def load_electrical_norms() -> dict[str, RoomNorms]:
    """Parsed once per process; treat the result as read-only."""
    out: dict[str, RoomNorms] = {}
    for room, v in _load("norms.yaml")["electrical"].items():
        out[room] = RoomNorms(
            m2_per_socket=d(v["m2_per_socket"]), min_sockets=int(v["min_sockets"]),
            switches=int(v["switches"]), m2_per_light=d(v["m2_per_light"]),
            cable_m_per_point=d(v["cable_m_per_point"]),
        )
    return out


def read_waste_table(path: Path | None = None, material: str = "tile") -> WasteTable:
    raw = yaml.safe_load((path or HERE / "waste_coefficients.yaml").read_text(encoding="utf-8"))
    if material != "tile":
        raw = raw[material]
    return WasteTable(
        layouts={k: d(v) for k, v in raw["layouts"].items()},
        small_room_extra=d(raw["small_room_extra"]),
        large_format_extra=d(raw["large_format_extra"]),
        source=str(raw["source"]),
    )


@cache
def load_waste_table(material: str = "tile") -> WasteTable:
    """The coefficients the calculators use (knowledge/waste_coefficients.yaml): `tile` (default,
    top level) or `laminate` (manufacturer table)."""
    return read_waste_table(material=material)


@cache
def load_corrections() -> CorrectionTable:
    out = []
    for c in _load("corrections.yaml")["corrections"]:
        s = c["source"]
        out.append(Correction(
            c["id"], c["work"], c["material"], tuple(sorted(c["condition"].items())),
            c["effect"]["type"], d(c["effect"]["value"]), c["reason"],
            Source(s["kind"], s["name"], s["url"], s["quote"], s.get("note", ""))))
    return CorrectionTable(tuple(out))


@cache
def load_work_rates() -> dict[str, WorkRate]:
    """Parsed once per process; treat the result as read-only."""
    out: dict[str, WorkRate] = {}
    for work, v in _load("work_rates.yaml")["rates"].items():
        rate = v["rub_per_unit"]
        out[work] = WorkRate(work, v["unit"], None if rate is None else d(rate), v["source"],
                             d(v["p25"]) if v.get("p25") is not None else None,
                             d(v["p75"]) if v.get("p75") is not None else None)
    return out


@dataclass(frozen=True)
class LaborParams:
    region_coeff: dict[str, Decimal]
    class_tier: dict[str, str]          # class -> p25 | median | p75 of the sourced rates
    scope: dict[str, frozenset[str]]    # class -> works included in the renovation
    spread: Spread | None


@cache
def load_labor_params() -> LaborParams:
    raw = _load("work_rates.yaml")
    sp = raw["spread"]
    spread = None
    if sp["low"] is not None and sp["high"] is not None:
        spread = Spread(d(sp["low"]), d(sp["high"]))
    return LaborParams(
        region_coeff={k: d(v) for k, v in raw["region_coeff"].items()},
        class_tier={k: str(v) for k, v in raw["class_tier"].items()},
        scope={k: frozenset(v) for k, v in raw["scope"].items()},
        spread=spread,
    )
