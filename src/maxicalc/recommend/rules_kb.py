from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

KB_FILE = Path(__file__).resolve().parents[1] / "knowledge" / "room_rules.yaml"


@dataclass(frozen=True)
class HardRule:
    calc: tuple[str, ...]
    work: tuple[str, ...]
    require_any: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class SoftRule:
    calc: tuple[str, ...]
    work: tuple[str, ...]
    prefer: tuple[str, ...]
    weight: float
    reason: str


@dataclass(frozen=True)
class RoomRules:
    hard: tuple[HardRule, ...] = field(default_factory=tuple)
    soft: tuple[SoftRule, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RoomKB:
    rooms: dict[str, RoomRules]
    overlays: dict[str, RoomRules] = field(default_factory=dict)


def _t(v: Any) -> tuple[str, ...]:
    return tuple(v or ())


@cache
def load_room_rules(path: Path = KB_FILE) -> RoomKB:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    def parse(body: dict[str, Any]) -> RoomRules:
        hard = tuple(HardRule(_t(r.get("calc")), _t(r.get("work")), _t(r["require_any"]),
                              r["reason"]) for r in body.get("hard") or [])
        soft = tuple(SoftRule(_t(r.get("calc")), _t(r.get("work")), _t(r["prefer"]),
                              float(r.get("weight", 1.0)), r["reason"])
                     for r in body.get("soft") or [])
        return RoomRules(hard, soft)

    rooms = {room: parse(body) for room, body in raw["rooms"].items()}
    overlays = {name: parse(body) for name, body in (raw.get("overlays") or {}).items()}
    return RoomKB(rooms, overlays)


def merged_rules(room: str, overlays: tuple[str, ...] = ()) -> RoomRules | None:
    """Rules of the room plus any overlay profiles (`wet_zone`, `heavy_traffic`).

    An overlay is how the user states what the room is like regardless of its name: a kitchen
    with a washing machine and high humidity gets the wet-zone requirements as well."""
    kb = load_room_rules()
    parts = [x for x in (kb.rooms.get(room), *(kb.overlays.get(o) for o in overlays)) if x]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return RoomRules(tuple(r for p in parts for r in p.hard),
                     tuple(r for p in parts for r in p.soft))
