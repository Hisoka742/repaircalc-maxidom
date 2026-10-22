from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path

import yaml

from maxicalc.engine.units import d

FILE = Path(__file__).resolve().parents[1] / "knowledge" / "presets.yaml"


@dataclass(frozen=True)
class RoomTemplate:
    room_type: str
    share: Decimal


@dataclass(frozen=True)
class ClassPackage:
    ops: tuple[str, ...]
    default_tier: str | None


@dataclass(frozen=True)
class Presets:
    ceiling_height_m: Decimal
    room_aspect: Decimal
    property_types: dict[str, tuple[RoomTemplate, ...]]
    wet_rooms: frozenset[str]
    classes: dict[str, ClassPackage]
    layers_mm: dict[str, Decimal]


@cache
def load_presets(path: Path = FILE) -> Presets:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    types = {
        name: tuple(RoomTemplate(r["type"], d(r["share"])) for r in body["rooms"])
        for name, body in raw["property_types"].items()
    }
    for name, rooms in types.items():
        if sum((r.share for r in rooms), Decimal(0)) > 1:
            raise ValueError(f"Доли комнат в «{name}» суммарно больше 1")
    return Presets(
        d(raw["defaults"]["ceiling_height_m"]), d(raw["defaults"]["room_aspect"]), types,
        frozenset(raw["wet_rooms"]),
        {k: ClassPackage(tuple(v["ops"]), v.get("default_tier"))
         for k, v in raw["classes"].items()},
        {k: d(v) for k, v in raw["layers_mm"].items()},
    )
