"""Room-level plan: which operations the renovation class needs, which SKU serves each,
and how much of it (all numbers from the deterministic engine, in base units).

Honesty rules: a SKU lacking the data the formula needs is skipped (next candidate tried);
if none is usable the operation yields a warning, never an invented quantity. Every default
the engine had to assume is listed in `assumptions`.

Two entry points: `plan_room` (a renovation class picks the products) and `plan_product`
(the customer picked a product; companions are added around it).
"""
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

from maxicalc.engine import electrical
from maxicalc.engine.electrical import ElectricalEstimate
from maxicalc.engine.geometry import Room
from maxicalc.engine.materials import (
    coatings,
    drywall,
    flooring,
    skirting,
    tile,
    wallpaper,
    waterproofing,
)
from maxicalc.engine.units import d
from maxicalc.knowledge.loader import load_corrections, load_electrical_norms, load_waste_table
from maxicalc.recommend.index import CatalogIndex
from maxicalc.recommend.inferred import effective_entry
from maxicalc.recommend.select import Candidate, CatalogEntry, recommend
from maxicalc.service.basket import Need
from maxicalc.service.presets import load_presets
from maxicalc.service.requirements import REQUIREMENTS

CALC_RU = {
    "paint": "краска", "primer": "грунтовка", "putty": "шпатлёвка", "laminate": "ламинат",
    "underlay": "подложка", "skirting": "плинтус", "tile": "плитка",
    "tile_adhesive": "плиточный клей", "tile_spacers": "крестики для плитки",
    "grout": "затирка", "self_leveling": "наливной пол",
    "waterproofing": "гидроизоляция", "wallpaper": "обои", "drywall": "гипсокартон",
    "wallpaper_glue": "клей для обоев",
}
# standard ГКЛ sheet (1200 x 2500 mm), used only when the card gives no sheet size
STANDARD_SHEET_M = (Decimal("2.5"), Decimal("1.2"))
ROOM_RU = {"living": "Гостиная", "bedroom": "Спальня", "kitchen": "Кухня", "bathroom": "Ванная",
           "kids": "Детская", "hallway": "Прихожая", "balcony": "Балкон"}
DEFAULT_PIECE_LEN_M = Decimal("2.5")
DEFAULT_GROUT_THICKNESS_MM = Decimal(8)
DEFAULT_JOINT_MM = Decimal(3)
DEFAULT_GROUT_DENSITY = Decimal("1.6")
WALLPAPER_TRIM_M = Decimal("0.1")
PAINT_LAYERS = 2
ALTERNATIVES = 2


@dataclass
class RoomPlan:
    room_name: str
    room_type: str
    needs: list[Need]
    warnings: list[str]
    assumptions: list[str]
    electrical: ElectricalEstimate | None = None
    # work -> (quantity, unit): what a contractor would be paid for, from the geometry
    works: dict[str, tuple[Decimal, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Conditions:
    """Work conditions that change quantities; each non-default value shows its coefficient,
    reason and source in the estimate (knowledge/corrections.yaml, waste_coefficients.yaml)."""

    floor_layout: str = "straight"      # tile / laminate: straight | diagonal | herringbone
    wall_evenness: str = "even"         # putty: even | uneven
    paint_surface: str = "smooth"       # paint: smooth | absorbent
    paint_layers: int = PAINT_LAYERS
    plaster_application: str = "manual"  # plaster: manual | machine


@dataclass
class _Ctx:
    room: Room
    room_type: str
    name: str
    index: CatalogIndex
    tier: str | None
    include_ceiling: bool = True
    overlays: tuple[str, ...] = ()
    forced: dict[str, CatalogEntry] = field(default_factory=dict)
    needs: list[Need] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    electrical_estimate: ElectricalEstimate | None = None
    works: dict[str, tuple[Decimal, str]] = field(default_factory=dict)
    inferred_notes: dict[str, list[str]] = field(default_factory=dict)
    inferred_held: dict[str, list[str]] = field(default_factory=dict)
    conditions: Conditions = field(default_factory=Conditions)

    def _effective(self, c: Candidate) -> Candidate:
        """Merge LLM-inferred attributes that clear the threshold into the entry's attrs."""
        entry, notes, held = effective_entry(c.entry)
        if notes:
            self.inferred_notes[entry.product.sku] = notes
        if held:
            self.inferred_held[entry.product.sku] = held
        return replace(c, entry=entry) if entry is not c.entry else c

    def work_for(self, calc: str) -> tuple[str, Decimal, str] | None:
        r = self.room
        table: dict[str, tuple[str, Decimal, str]] = {
            "paint": ("painting_walls", self.paint_area(), "м²"),
            "primer": ("priming", self.paint_area(), "м²"),
            "putty": ("puttying", r.wall_area_net_m2, "м²"),
            "wallpaper": ("wallpapering", r.wall_area_net_m2, "м²"),
            "drywall": ("drywall_lining", r.wall_area_net_m2, "м²"),
            "laminate": ("laminate", r.floor_area_m2, "м²"),
            "tile": ("tiling_floor", r.floor_area_m2, "м²"),
            "self_leveling": ("self_leveling", r.floor_area_m2, "м²"),
            "waterproofing": ("waterproofing", r.floor_area_m2, "м²"),
            "skirting": ("skirting", r.skirting_length_m, "м"),
        }
        return table.get(calc)

    def note(self, text: str) -> None:
        if text not in self.assumptions:
            self.assumptions.append(text)

    def _missing(self, entry: CatalogEntry, required: tuple[str, ...],
                 any_of: tuple[str, ...]) -> list[str]:
        miss = [a for a in required if a not in entry.attrs]
        if any_of and not any(a in entry.attrs for a in any_of):
            miss.append("/".join(any_of))
        return miss

    def pick(self, calc: str) -> tuple[Candidate, list[CatalogEntry]] | None:
        required, any_of = REQUIREMENTS.get(calc, ((), ()))
        if calc in self.forced:
            return self._pick_forced(calc, required, any_of)
        res = self.index.recommend(self.room_type, calc, self.tier, self.overlays)
        if not res.items:
            self.warnings.append(
                f"{self.name}: нет подходящего товара ({CALC_RU.get(calc, calc)}) — "
                f"{res.warnings[0] if res.warnings else 'каталог пуст'}")
            return None
        eff = [self._effective(c) for c in res.items]
        usable = [c for c in eff if not self._missing(c.entry, required, any_of)]
        if not usable:
            missing = ", ".join(self._missing(eff[0].entry, required, any_of))
            held = self.inferred_held.get(eff[0].entry.product.sku)
            extra = (f"; значения, выведенные моделью ({', '.join(held)}), ниже порога уверенности"
                     if held else "")
            self.warnings.append(
                f"{self.name}: у подходящих товаров ({CALC_RU.get(calc, calc)}) в карточке нет "
                f"данных для расчёта: {missing}{extra}")
            return None
        return usable[0], [c.entry for c in usable[1:1 + ALTERNATIVES]]

    def _pick_forced(
        self, calc: str, required: tuple[str, ...], any_of: tuple[str, ...]
    ) -> tuple[Candidate, list[CatalogEntry]] | None:
        entry = self._effective(Candidate(self.forced[calc], 1.0, [])).entry
        check = recommend([entry], self.room_type, calc=calc, include_review=True,
                          overlays=self.overlays)
        if check.excluded:
            self.warnings.append(
                f"{self.name}: выбранный товар не рекомендуется для этого помещения — "
                f"{check.excluded[0][1]}")
        miss = self._missing(entry, required, any_of)
        if miss:
            self.warnings.append(
                f"{self.name}: в карточке товара {entry.product.sku} нет данных для расчёта: "
                f"{', '.join(miss)}")
            return None
        return Candidate(entry, 1.0, ["выбран покупателем"]), []

    def add(self, cand: Candidate, alts: list[CatalogEntry], qty: Decimal, base_unit: str,
            pack_size: Decimal, pack_unit: str, explain: list[str]) -> None:
        lines = [f"{self.name}: {explain[0]}", *explain[1:]] if explain else []
        lines += self.inferred_notes.get(cand.entry.product.sku, [])
        self.needs.append(Need(cand.entry, qty, base_unit, pack_size, pack_unit, lines, alts,
                               list(cand.reasons)))
        w = self.work_for(cand.entry.calc)
        if w and w[1] > 0:
            self.works[w[0]] = (w[1], w[2])

    def paint_area(self) -> Decimal:
        area = self.room.wall_area_net_m2
        return area + self.room.ceiling_area_m2 if self.include_ceiling else area


def _attr(c: Candidate, key: str) -> Decimal:
    return d(c.entry.attrs[key])  # type: ignore[arg-type]


def _surface_label(x: _Ctx) -> str:
    return "Стены и потолок" if x.include_ceiling else "Стены"


def _op_walls_paint(x: _Ctx) -> None:
    got = x.pick("paint")
    if not got:
        return
    c, alts = got
    area = x.paint_area()
    cond = x.conditions
    r = coatings.liters_by_spread(area, _attr(c, "spread_m2_per_l"), cond.paint_layers)
    liters, extra = r.value, []
    if cond.paint_surface != "smooth":
        k = load_corrections().find("wall_painting", "water_dispersion_paint",
                                    surface=cond.paint_surface)
        liters = liters * k.value
        extra = [k.explain(), f"{r.value} л × {k.value} = {liters} л"]
    x.add(c, alts, liters, "л", _attr(c, "pack_volume_l"), "уп",
          [f"{_surface_label(x)} {area} м²", *r.explain, *extra])


def _op_walls_primer(x: _Ctx) -> None:
    got = x.pick("primer")
    if not got:
        return
    c, alts = got
    area = x.paint_area()
    r = coatings.liters_by_consumption(area, _attr(c, "consumption_l_per_m2"), 1)
    x.add(c, alts, r.value, "л", _attr(c, "pack_volume_l"), "уп",
          [f"Грунтование {area} м²", *r.explain])


def _op_walls_putty(x: _Ctx) -> None:
    got = x.pick("putty")
    if not got:
        return
    c, alts = got
    cond = x.conditions
    name = c.entry.product.name.lower()
    plaster = any(w in name for w in ("штукатур", "ротбанд", "мп 75", "мп75"))
    extra: list[str] = []
    factor = Decimal(1)
    if plaster:
        mm = load_presets().layers_mm["plaster"]
        x.note(f"Слой штукатурки принят {mm} мм")
        if cond.plaster_application != "manual":
            k = load_corrections().find("plastering", "gypsum_plaster",
                                        application=cond.plaster_application)
            factor = k.value
            extra.append(k.explain())
    elif cond.wall_evenness != "even":
        k = load_corrections().find("puttying", "finish_putty", evenness=cond.wall_evenness)
        mm = k.value
        extra.append(k.explain())
        x.note(f"Неровные стены: средний слой шпатлёвки принят {mm} мм")
    else:
        mm = load_presets().layers_mm["putty_finish"]
        x.note(f"Слой финишной шпатлёвки принят {mm} мм")
    r = coatings.kg_by_thickness(x.room.wall_area_net_m2, mm,
                                 _attr(c, "consumption_kg_per_m2_per_mm"))
    kg = r.value * factor
    if factor != 1:
        extra.append(f"{r.value} кг × {factor} = {kg} кг")
    x.add(c, alts, kg, "кг", _attr(c, "pack_mass_kg"), "уп",
          [f"{'Штукатурка' if plaster else 'Шпатлёвка'} стен {x.room.wall_area_net_m2} м²",
           *r.explain, *extra])


def _op_wallpaper(x: _Ctx) -> None:
    got = x.pick("wallpaper")
    if not got:
        return
    c, alts = got
    rapport_cm = c.entry.attrs.get("rapport_cm")
    rapport_m = Decimal(0) if rapport_cm is None else d(rapport_cm) / 100  # type: ignore[arg-type]
    x.note(f"Припуск на подгонку по высоте принят {WALLPAPER_TRIM_M} м, запас рулонов не добавлен")
    r = wallpaper.rolls(x.room, _attr(c, "roll_width_m"), _attr(c, "roll_length_m"),
                        rapport_m, "straight", WALLPAPER_TRIM_M, 0)
    x.add(c, alts, r.value, "рулон", Decimal(1), "рулон", [*r.explain])


def _op_walls_drywall(x: _Ctx) -> None:
    """Moisture-resistant drywall lining of the walls of a wet room.

    Runs for wet rooms (and wherever the customer states high humidity); a customer who picked a
    drywall product on its card gets the calculation for the walls they entered."""
    wet = x.room_type in load_presets().wet_rooms or "wet_zone" in x.overlays
    if not wet and "drywall" not in x.forced:
        return
    got = x.pick("drywall")
    if not got:
        return
    c, alts = got
    ln, wd = c.entry.attrs.get("length_mm"), c.entry.attrs.get("width_mm")
    if ln is not None and wd is not None:
        a, b = d(ln) / 1000, d(wd) / 1000  # type: ignore[arg-type]
        sheet = (max(a, b), min(a, b))
    else:
        sheet = STANDARD_SHEET_M
        x.note("Размер листа гипсокартона принят стандартным 2500×1200 мм (в карточке не указан)")
    area = x.room.wall_area_net_m2
    r = drywall.sheets(area, sheet[1], sheet[0])
    x.note("Профиль, саморезы и шпатлёвка швов для каркаса гипсокартона в смету не входят")
    x.add(c, alts, r.value, "лист", Decimal(1), "лист", [f"Обшивка стен {area} м²", *r.explain])


def _op_wallpaper_glue(x: _Ctx) -> None:
    """Glue for the wallpaper being hung: by the pack's coverage, else consumption x pack mass."""
    got = x.pick("wallpaper_glue")
    if not got:
        return
    c, alts = got
    area = x.room.wall_area_net_m2
    cov = c.entry.attrs.get("coverage_m2_per_pack")
    if cov is not None:
        r = wallpaper.glue_packs(area, coverage_m2_per_pack=d(cov))  # type: ignore[arg-type]
        x.add(c, alts, r.value, "уп", Decimal(1), "уп",
              [f"Клей для обоев на {area} м²", *r.explain])
        return
    mass = c.entry.attrs.get("pack_mass_kg")
    if mass is None:
        x.warnings.append(f"{x.name}: у клея для обоев {c.entry.product.sku} нет массы упаковки")
        return
    r = wallpaper.glue_packs(area, consumption_kg_per_m2=_attr(c, "consumption_kg_per_m2"),
                             pack_mass_kg=d(mass))  # type: ignore[arg-type]
    x.add(c, alts, r.value, "уп", Decimal(1), "уп", [f"Клей для обоев на {area} м²", *r.explain])


def _op_waterproofing(x: _Ctx) -> None:
    got = x.pick("waterproofing")
    if not got:
        return
    c, alts = got
    area = waterproofing.treated_area(x.room)
    kg_attr = c.entry.attrs.get("consumption_kg_per_m2")
    if kg_attr is None:
        x.note("Расход гидроизоляции принят по таблице Ceresit CR 65 (повышенная влажность)")
    r = waterproofing.kg(area.value, "high_humidity",
                         None if kg_attr is None else d(kg_attr))  # type: ignore[arg-type]
    x.add(c, alts, r.value, "кг", _attr(c, "pack_mass_kg"), "уп", [*area.explain, *r.explain])


def _op_self_leveling(x: _Ctx) -> None:
    got = x.pick("self_leveling")
    if not got:
        return
    c, alts = got
    mm = load_presets().layers_mm["self_leveling"]
    x.note(f"Толщина слоя наливного пола принята {mm} мм")
    r = coatings.kg_by_thickness(x.room.floor_area_m2, mm,
                                 _attr(c, "consumption_kg_per_m2_per_mm"))
    x.add(c, alts, r.value, "кг", _attr(c, "pack_mass_kg"), "уп",
          [f"Наливной пол {x.room.floor_area_m2} м²", *r.explain])


def _op_floor_prep(x: _Ctx) -> None:
    if x.room_type in load_presets().wet_rooms:
        _op_waterproofing(x)
    else:
        _op_self_leveling(x)


def _op_laminate(x: _Ctx) -> None:
    got = x.pick("laminate")
    if got:
        c, alts = got
        r = flooring.area_with_waste(x.room.floor_area_m2, x.conditions.floor_layout,
                                     load_waste_table("laminate"))
        x.add(c, alts, r.value, "м²", _attr(c, "m2_per_pack"), "уп", [*r.explain])


def _op_underlay(x: _Ctx) -> None:
    got = x.pick("underlay")
    if got:
        c, alts = got
        r = flooring.underlay_area(x.room.floor_area_m2)
        x.add(c, alts, r.value, "м²", _attr(c, "m2_per_pack"), "уп", [*r.explain])


def _op_tile(x: _Ctx) -> None:
    area = x.room.floor_area_m2
    got = x.pick("tile")
    if not got:
        return
    c, alts = got
    w, h = _attr(c, "tile_w_mm"), _attr(c, "tile_h_mm")
    r = tile.area_with_waste(area, x.conditions.floor_layout, w, h, load_waste_table())
    if "m2_per_pack" in c.entry.attrs:
        pack = _attr(c, "m2_per_pack")
    else:
        pack = _attr(c, "pcs_per_pack") * w * h / Decimal(1_000_000)
    x.add(c, alts, r.value, "м²", pack, "уп", [*r.explain])

    adh = x.pick("tile_adhesive")
    if adh:
        ac, aalts = adh
        rate = ac.entry.attrs.get("consumption_kg_per_m2")
        low = f"{ac.entry.product.name} {ac.entry.product.brand or ''}".lower()
        if "cm 11 plus" in low:
            table, maker = "cm11_plus", "Ceresit CM 11 PLUS"
        elif "основит" in low:
            table, maker = "osnovit_ac14", "ОСНОВИТ Гранипликс АС14 F"
        else:
            table, maker = "cm11", "Ceresit CM 11"
        if rate is None:
            x.note(f"Расход плиточного клея принят по таблице {maker} (по размеру плитки)")
        ar = tile.adhesive_kg(area, w, h, None if rate is None else d(rate),  # type: ignore[arg-type]
                              table)
        x.add(ac, aalts, ar.value, "кг", _attr(ac, "pack_mass_kg"), "уп", [*ar.explain])
    gr = x.pick("grout")
    if gr:
        gc, galts = gr
        x.note(f"Для затирки приняты толщина плитки {DEFAULT_GROUT_THICKNESS_MM} мм, "
               f"шов {DEFAULT_JOINT_MM} мм, плотность {DEFAULT_GROUT_DENSITY} кг/дм³")
        gres = tile.grout_kg(area, w, h, DEFAULT_GROUT_THICKNESS_MM, DEFAULT_JOINT_MM,
                             DEFAULT_GROUT_DENSITY)
        x.add(gc, galts, gres.value, "кг", _attr(gc, "pack_mass_kg"), "уп", [*gres.explain])
    sp = x.pick("tile_spacers")
    if sp:
        sc, salts = sp
        x.note(f"Для крестиков принят шов {DEFAULT_JOINT_MM} мм, раскладка прямая")
        sres = tile.spacers(area, w, h, DEFAULT_JOINT_MM, "straight")
        x.add(sc, salts, sres.value, "шт", _attr(sc, "pcs_per_pack"), "уп", [*sres.explain])


def _op_floor_covering(x: _Ctx) -> None:
    if x.room_type in load_presets().wet_rooms:
        _op_tile(x)
    else:
        _op_laminate(x)
        _op_underlay(x)


def _skirting(x: _Ctx) -> None:
    got = x.pick("skirting")
    if not got:
        return
    c, alts = got
    plen = c.entry.attrs.get("piece_len_m")
    if plen is None:
        x.note("Длина планки плинтуса не указана в карточке — принято 2,5 м")
    r = skirting.pieces(x.room, DEFAULT_PIECE_LEN_M if plen is None else d(plen))  # type: ignore[arg-type]
    x.add(c, alts, r.value, "шт", Decimal(1), "шт", [*r.explain])


def _op_skirting(x: _Ctx) -> None:
    if x.room_type not in load_presets().wet_rooms:
        _skirting(x)


def _op_electrical(x: _Ctx) -> None:
    norms = load_electrical_norms()
    if x.room_type not in norms:
        x.warnings.append(f"{x.name}: нет норм электрики для этого помещения")
        return
    x.electrical_estimate = electrical.estimate(x.room_type, x.room.floor_area_m2, norms)
    e = x.electrical_estimate
    points = e.sockets + e.switches + e.light_points
    if points > 0:
        x.works["electrical_point"] = (Decimal(points), "шт")


Op = Callable[[_Ctx], None]
_OPS: dict[str, Op] = {
    "walls_drywall": _op_walls_drywall, "walls_paint": _op_walls_paint,
    "walls_primer": _op_walls_primer,
    "walls_putty": _op_walls_putty, "floor_prep": _op_floor_prep,
    "floor_covering": _op_floor_covering, "skirting": _op_skirting,
    "electrical": _op_electrical,
}

# Product-card calculators: the chosen product's own op, then its companions.
_PRODUCT_OPS: dict[str, tuple[Op, ...]] = {
    "paint": (_op_walls_paint, _op_walls_primer),
    "primer": (_op_walls_primer,),
    "putty": (_op_walls_putty, _op_walls_primer),
    "wallpaper": (_op_wallpaper, _op_walls_primer, _op_wallpaper_glue),
    "laminate": (_op_laminate, _op_underlay, _skirting),
    "underlay": (_op_underlay,),
    "skirting": (_skirting,),
    "tile": (_op_tile,),
    "self_leveling": (_op_self_leveling, _op_walls_primer),
    "waterproofing": (_op_waterproofing,),
    "drywall": (_op_walls_drywall,),
}
PRODUCT_CALCS = frozenset(_PRODUCT_OPS)


def _index(catalog: "list[CatalogEntry] | CatalogIndex") -> CatalogIndex:
    return catalog if isinstance(catalog, CatalogIndex) else CatalogIndex(catalog)


def plan_room(
    room: Room, room_type: str, klass: str, catalog: "list[CatalogEntry] | CatalogIndex",
    tier: str | None = None, name: str | None = None, include_ceiling: bool = True,
    overlays: tuple[str, ...] = (), conditions: Conditions | None = None,
) -> RoomPlan:
    presets = load_presets()
    if klass not in presets.classes:
        raise ValueError(f"Неизвестный класс ремонта: {klass}")
    pkg = presets.classes[klass]
    x = _Ctx(room, room_type, name or ROOM_RU.get(room_type, room_type), _index(catalog),
             tier or pkg.default_tier, include_ceiling, overlays,
             conditions=conditions or Conditions())
    if "wet_zone" in overlays and room_type != "bathroom":
        x.note("Помещение отмечено как влажное: применены требования к материалам для влажных зон")
    if "heavy_traffic" in overlays:
        x.note("Помещение отмечено как с высокой нагрузкой: применены требования к износостойкости")
    for op in pkg.ops:
        _OPS[op](x)
    return RoomPlan(x.name, room_type, x.needs, x.warnings, x.assumptions, x.electrical_estimate,
                    x.works)


def plan_product(
    room: Room, room_type: str, entry: CatalogEntry,
    catalog: "list[CatalogEntry] | CatalogIndex", name: str | None = None,
    include_ceiling: bool = True, overlays: tuple[str, ...] = (),
) -> RoomPlan:
    """Quantity of the customer's chosen product for this room, plus companion items."""
    ops = _PRODUCT_OPS.get(entry.calc)
    if ops is None:
        raise ValueError(
            f"Для товара этого типа ({entry.calc}) нет калькулятора количества")
    ceiling = include_ceiling and entry.calc not in ("wallpaper",)
    x = _Ctx(room, room_type, name or ROOM_RU.get(room_type, room_type), _index(catalog), None,
             ceiling, overlays, forced={entry.calc: entry})
    for op in ops:
        op(x)
    return RoomPlan(x.name, room_type, x.needs, x.warnings, x.assumptions, None, x.works)
