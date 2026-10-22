"""Laminate / SPC / parquet: packs = ceil(area x (1 + waste) / m2 per pack)."""
from decimal import Decimal

from maxicalc.engine.materials.waste import DEFAULT_TABLE, WasteTable, layout_waste
from maxicalc.engine.result import Calc
from maxicalc.engine.units import Number, ceil_int, d


def area_with_waste(
    area_m2: Number, layout: str = "straight", table: WasteTable | None = None
) -> Calc:
    a = d(area_m2)
    if a < 0:
        raise ValueError("Площадь не может быть отрицательной")
    w = layout_waste(layout, table)
    v = a * (1 + w)
    src = (table or DEFAULT_TABLE).source
    return Calc(v, "м²", (f"{a} м² × (1 + {w}) [{layout}; {src}] = {v} м²",))


def packs(area_with_waste_m2: Number, m2_per_pack: Number) -> Calc:
    a, p = d(area_with_waste_m2), d(m2_per_pack)
    if p <= 0:
        raise ValueError("Некорректная фасовка")
    n = ceil_int(a / p)
    return Calc(Decimal(n), "уп", (f"ceil({a} / {p}) = {n} уп",))


def underlay_packs(area_m2: Number, m2_per_pack: Number, reserve: Number = "0.05") -> Calc:
    """Underlay: ceil(area x (1 + 5%) / m2 per pack). Skip for SPC with integrated underlay."""
    a, p, r = d(area_m2), d(m2_per_pack), d(reserve)
    if a < 0 or p <= 0 or r < 0:
        raise ValueError("Некорректные параметры подложки")
    need = a * (1 + r)
    n = ceil_int(need / p)
    return Calc(Decimal(n), "уп", (f"{a} м² × (1 + {r}) = {need} м²; ceil({need} / {p}) = {n} уп",))


def underlay_area(area_m2: Number, reserve: Number = "0.05") -> Calc:
    """Underlay area to buy before rounding to packs: area x (1 + reserve)."""
    a, r = d(area_m2), d(reserve)
    if a < 0 or r < 0:
        raise ValueError("Некорректные параметры подложки")
    v = a * (1 + r)
    return Calc(v, "м²", (f"Подложка: {a} м² × (1 + {r}) = {v} м²",))
