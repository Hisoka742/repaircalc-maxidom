"""Free-text request -> structured calculator input ("санузел 6 м², высокая влажность").

Rules first (deterministic, instant, testable); the local LLM is only a fallback when the rules
find no room at all. Everything the LLM returns passes the same validation as rule output:
unknown room types or implausible areas are dropped, never guessed. Missing information is
reported in `missing`, not invented.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from maxicalc.ml.llm_client import LLMClient, LLMError

ROOM_WORDS: dict[str, tuple[str, ...]] = {
    "bathroom": ("санузел", "сануз", "ванн", "туалет", "душев", "wc"),
    "kitchen": ("кухн",),
    "kids": ("детск",),
    "bedroom": ("спальн",),
    "living": ("гостин", "зал", "комнат"),
    "hallway": ("прихож", "коридор", "холл"),
    "balcony": ("балкон", "лоджи"),
}
PROPERTY_WORDS = {"apartment": ("квартир",), "studio": ("студи",), "house": ("дом", "коттедж")}
CLASS_WORDS = {
    "major": ("капитальн", "капремонт", "кап."),
    "cosmetic": ("косметическ", "косметик"),
    "designer": ("дизайнерск", "дизайн-проект"),
}
TIER_WORDS = {"economy": ("эконом", "бюджет", "недорог"), "premium": ("премиум", "дорог"),
              "standard": ("стандарт", "средн")}
_AREA = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:м2|м²|м\^2|кв\.?\s*м|квадрат|м\b)", re.IGNORECASE)
_HIGH_HUM = re.compile(r"высок\w*\s+влажн|влажн\w+\s+(?:помещени|зон|комнат)|повышенн\w*\s+влажн"
                       r"|мокр\w+\s+зон", re.IGNORECASE)
_HIGH_LOAD = re.compile(r"высок\w*\s+нагрузк|большая\s+нагрузк|проходн", re.IGNORECASE)
# a comma between digits is a decimal separator ("4,5 м2"), not a list separator
_SPLIT = re.compile(r"[;]|(?<!\d),|,(?!\d)|\s+и\s+|\s+\+\s+|\n")
MAX_AREA = Decimal(500)


@dataclass
class ParsedRoom:
    room_type: str
    area_m2: Decimal | None = None
    humidity: Literal["high"] | None = None
    load: Literal["high"] | None = None


@dataclass
class Parsed:
    property_type: str | None = None
    renovation_class: str | None = None
    tier: str | None = None
    total_area_m2: Decimal | None = None
    rooms: list[ParsedRoom] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    method: Literal["rules", "llm", "none"] = "rules"
    notes: list[str] = field(default_factory=list)


def _first(words: dict[str, tuple[str, ...]], text: str) -> str | None:
    for key, ws in words.items():
        if any(w in text for w in ws):
            return key
    return None


def _room_of(seg: str) -> str | None:
    for key, ws in ROOM_WORDS.items():
        if any(w in seg for w in ws):
            return key
    return None


def _area(seg: str) -> Decimal | None:
    m = _AREA.search(seg)
    if not m:
        return None
    try:
        v = Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    return v if 0 < v <= MAX_AREA else None


def parse_rules(text: str) -> Parsed:
    t = text.lower().replace("ё", "е")
    out = Parsed()
    out.property_type = _first(PROPERTY_WORDS, t)
    out.renovation_class = _first(CLASS_WORDS, t)
    out.tier = _first(TIER_WORDS, t)
    global_hum = bool(_HIGH_HUM.search(t)) and not any(_room_of(s) for s in _SPLIT.split(t)
                                                       if _HIGH_HUM.search(s))
    segs = [s.strip() for s in _SPLIT.split(t) if s.strip()]
    for seg in segs:
        room = _room_of(seg)
        area = _area(seg)
        if room is None:
            if area is not None and out.total_area_m2 is None and (
                    out.property_type or "общ" in seg or "площад" in seg):
                out.total_area_m2 = area
            continue
        # "2-комнатная квартира" is a property description, not a living room
        if room == "living" and re.search(r"\d\s*-?\s*комнат", seg):
            if out.total_area_m2 is None and area is not None:
                out.total_area_m2 = area
            continue
        out.rooms.append(ParsedRoom(
            room, area, "high" if _HIGH_HUM.search(seg) else None,
            "high" if _HIGH_LOAD.search(seg) else None))
    if global_hum:
        for r in out.rooms:
            r.humidity = r.humidity or "high"
    # a bathroom is a wet room whether or not the text says so; keep what the text said
    out.method = "rules" if out.rooms or out.total_area_m2 else "none"
    _finish(out)
    return out


def _finish(p: Parsed) -> None:
    p.missing = []
    if p.property_type is None:
        p.missing.append("property_type")
    if p.renovation_class is None:
        p.missing.append("renovation_class")
    if p.total_area_m2 is None and not any(r.area_m2 for r in p.rooms):
        p.missing.append("total_area_m2")
    if any(r.area_m2 is None for r in p.rooms):
        p.missing.append("room_area_m2")


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "property_type": {"type": ["string", "null"],
                          "enum": ["apartment", "studio", "house", None]},
        "renovation_class": {"type": ["string", "null"],
                             "enum": ["cosmetic", "major", "designer", None]},
        "total_area_m2": {"type": ["number", "null"]},
        "rooms": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "room_type": {"type": "string", "enum": list(ROOM_WORDS)},
                "area_m2": {"type": ["number", "null"]},
                "humidity": {"type": ["string", "null"], "enum": ["high", None]},
            },
            "required": ["room_type", "area_m2", "humidity"], "additionalProperties": False}},
    },
    "required": ["property_type", "renovation_class", "total_area_m2", "rooms"],
    "additionalProperties": False,
}
SYSTEM = (
    "Извлеки параметры ремонта из запроса покупателя. Только то, что явно сказано; если чего-то "
    "нет — null. Не придумывай площади и типы помещений. Тип ремонта: cosmetic (косметический), "
    "major (капитальный), designer (дизайнерский)."
)


def parse_llm(text: str, llm: LLMClient) -> Parsed:
    out = Parsed(method="llm")
    data = llm.chat_json(SYSTEM, text, SCHEMA)
    pt, rc = data.get("property_type"), data.get("renovation_class")
    out.property_type = pt if pt in PROPERTY_WORDS else None
    out.renovation_class = rc if rc in CLASS_WORDS else None
    ta = data.get("total_area_m2")
    if isinstance(ta, int | float) and 0 < ta <= 5000:
        out.total_area_m2 = Decimal(str(ta))
    for r in data.get("rooms") or []:
        if not isinstance(r, dict) or r.get("room_type") not in ROOM_WORDS:
            out.notes.append("пропущено помещение неизвестного типа")
            continue
        a = r.get("area_m2")
        area = Decimal(str(a)) if isinstance(a, int | float) and 0 < a <= MAX_AREA else None
        out.rooms.append(ParsedRoom(r["room_type"], area, "high" if r.get("humidity") == "high"
                                    else None))
    _finish(out)
    return out


def parse_request(text: str, llm: LLMClient | None = None) -> Parsed:
    p = parse_rules(text)
    if p.rooms or llm is None:
        return p
    try:
        q = parse_llm(text, llm)
    except LLMError as e:
        p.notes.append(f"LLM недоступен: {e}")
        return p
    if q.rooms or q.total_area_m2:
        return q
    return p
