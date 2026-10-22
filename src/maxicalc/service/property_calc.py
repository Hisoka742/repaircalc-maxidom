"""Property-level calculator: property type + area + renovation class -> rooms -> basket."""
from dataclasses import dataclass, field
from decimal import Decimal

from maxicalc.engine.electrical import ElectricalEstimate
from maxicalc.engine.geometry import Room
from maxicalc.engine.labor import WorkRate
from maxicalc.engine.units import d
from maxicalc.knowledge.loader import LaborParams, load_labor_params, load_work_rates
from maxicalc.recommend.index import CatalogIndex
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.basket import Basket, build_basket
from maxicalc.service.labor_calc import LaborResult, compute_labor
from maxicalc.service.presets import load_presets
from maxicalc.service.room_calc import Conditions, RoomPlan, plan_product, plan_room

TIERS = ("economy", "standard", "premium")


@dataclass(frozen=True)
class RoomInput:
    room_type: str
    area_m2: Decimal
    height_m: Decimal | None = None
    humidity: str | None = None   # "high" -> wet-zone requirements, whatever the room is called
    load: str | None = None       # "high" -> heavy-traffic requirements


@dataclass(frozen=True)
class PropertyInput:
    property_type: str
    total_area_m2: Decimal
    renovation_class: str
    rooms: list[RoomInput] | None = None   # overrides the preset when given
    tier: str | None = None
    ceiling_height_m: Decimal | None = None


@dataclass(frozen=True)
class RoomSummary:
    room_type: str
    area_m2: Decimal
    height_m: Decimal
    humidity: str | None = None
    load: str | None = None


@dataclass
class PropertyEstimate:
    rooms: list[RoomSummary]
    basket: Basket
    labor: LaborResult | None   # None until every needed rate is sourced; never invented
    labor_note: str = ""
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    electrical: list[tuple[str, ElectricalEstimate]] = field(default_factory=list)


def overlays_for(humidity: str | None, load: str | None) -> tuple[str, ...]:
    out: list[str] = []
    if humidity == "high":
        out.append("wet_zone")
    if load == "high":
        out.append("heavy_traffic")
    return tuple(out)


def rectangle_for_area(area: Decimal, height: Decimal, aspect: Decimal) -> Room:
    """Rectangle with exactly `area` and length/width = aspect (no intermediate rounding)."""
    length = (area * aspect).sqrt()
    return Room.rectangle(length, area / length, height)


def _rooms(inp: PropertyInput, ceiling: Decimal) -> list[RoomInput]:
    if inp.rooms:
        return list(inp.rooms)
    presets = load_presets()
    if inp.property_type not in presets.property_types:
        raise ValueError(f"Неизвестный тип недвижимости: {inp.property_type}")
    return [RoomInput(t.room_type, inp.total_area_m2 * t.share, ceiling)
            for t in presets.property_types[inp.property_type]]


def calc_property(
    inp: PropertyInput, catalog: list[CatalogEntry] | CatalogIndex
) -> PropertyEstimate:
    presets = load_presets()
    index = catalog if isinstance(catalog, CatalogIndex) else CatalogIndex(catalog)
    if inp.total_area_m2 <= 0:
        raise ValueError("Площадь должна быть положительной")
    if inp.renovation_class not in presets.classes:
        raise ValueError(f"Неизвестный класс ремонта: {inp.renovation_class}")
    if inp.tier is not None and inp.tier not in TIERS:
        raise ValueError(f"Неизвестный уровень цены: {inp.tier}")
    ceiling = inp.ceiling_height_m or presets.ceiling_height_m
    rooms = _rooms(inp, ceiling)

    plans: list[RoomPlan] = []
    summaries: list[RoomSummary] = []
    for r in rooms:
        if r.area_m2 <= 0:
            raise ValueError("Площадь комнаты должна быть положительной")
        h = r.height_m or ceiling
        geom = rectangle_for_area(d(r.area_m2), d(h), presets.room_aspect)
        plans.append(plan_room(geom, r.room_type, inp.renovation_class, index, inp.tier,
                               overlays=overlays_for(r.humidity, r.load)))
        summaries.append(RoomSummary(r.room_type, r.area_m2, h, r.humidity, r.load))

    return _finish(summaries, plans, True, inp.renovation_class)


def _labor(
    plans: list[RoomPlan], klass: str, rates: dict[str, WorkRate] | None,
    params: LaborParams | None,
) -> tuple[LaborResult | None, str]:
    p = params or load_labor_params()
    return compute_labor(plans, klass, rates if rates is not None else load_work_rates(),
                         p.class_tier, p.scope, p.region_coeff, p.spread)


def _finish(
    summaries: list[RoomSummary], plans: list[RoomPlan], with_labor: bool, klass: str = "",
    rates: dict[str, WorkRate] | None = None, params: LaborParams | None = None,
) -> PropertyEstimate:
    basket = build_basket(plans)
    est = PropertyEstimate(summaries, basket, None)
    if with_labor:
        est.labor, est.labor_note = _labor(plans, klass, rates, params)
        if est.labor is None:
            est.warnings.append("Ставки работ не заданы — стоимость работ не рассчитана")
    est.warnings.extend(basket.warnings)
    for p in plans:
        for w in p.warnings:
            if w not in est.warnings:
                est.warnings.append(w)
        for a in p.assumptions:
            if a not in est.assumptions:
                est.assumptions.append(a)
        if p.electrical:
            est.electrical.append((p.room_name, p.electrical))
    return est


def calc_room(
    room: Room, room_type: str, renovation_class: str,
    catalog: list[CatalogEntry] | CatalogIndex, tier: str | None = None,
    include_ceiling: bool = True, humidity: str | None = None, load: str | None = None,
    labor_rates: dict[str, WorkRate] | None = None, labor_params: LaborParams | None = None,
    conditions: Conditions | None = None,
) -> PropertyEstimate:
    """One room with explicit geometry (openings, L-shapes) -> materials for a class."""
    if tier is not None and tier not in TIERS:
        raise ValueError(f"Неизвестный уровень цены: {tier}")
    plan = plan_room(room, room_type, renovation_class, catalog, tier,
                     include_ceiling=include_ceiling, overlays=overlays_for(humidity, load),
                     conditions=conditions)
    summary = RoomSummary(room_type, room.floor_area_m2, room.height_m, humidity, load)
    return _finish([summary], [plan], True, renovation_class, labor_rates, labor_params)


def calc_product(
    room: Room, room_type: str, entry: CatalogEntry,
    catalog: list[CatalogEntry] | CatalogIndex, include_ceiling: bool = True,
    humidity: str | None = None, load: str | None = None,
) -> PropertyEstimate:
    """Product-card calculator: how many packs of THIS product for the room + companions."""
    plan = plan_product(room, room_type, entry, catalog, include_ceiling=include_ceiling,
                        overlays=overlays_for(humidity, load))
    summary = RoomSummary(room_type, room.floor_area_m2, room.height_m, humidity, load)
    return _finish([summary], [plan], False)
