"""Wallpaper rolls by strips per wall (never area / roll-area).

Source: standard strip method used by manufacturers' calculators (e.g. Erismann, Rasch):
strip length = wall height + trim, rounded up to a rapport multiple; strips per roll =
floor(roll length / strip length); strips per wall = ceil(net wall width / roll width).
"""
from decimal import Decimal
from typing import Literal

from maxicalc.engine.geometry import Room
from maxicalc.engine.result import Calc
from maxicalc.engine.units import Number, ceil_int, d, floor_int


def glue_packs(
    area_m2: Number,
    coverage_m2_per_pack: Number | None = None,
    consumption_kg_per_m2: Number | None = None,
    pack_mass_kg: Number | None = None,
) -> Calc:
    """Wallpaper glue, from the product card: either the area one pack covers, or the
    consumption (kg per m2) with the pack mass. Packs are rounded up once, at the end."""
    a = d(area_m2)
    if a < 0:
        raise ValueError("Площадь не может быть отрицательной")
    if coverage_m2_per_pack is not None:
        c = d(coverage_m2_per_pack)
        if c <= 0:
            raise ValueError("Некорректное покрытие упаковки клея")
        n = ceil_int(a / c)
        return Calc(Decimal(n), "уп", (f"Одна упаковка клеит {c} м²: ceil({a} / {c}) = {n} уп",))
    if consumption_kg_per_m2 is not None and pack_mass_kg is not None:
        r, m = d(consumption_kg_per_m2), d(pack_mass_kg)
        if r <= 0 or m <= 0:
            raise ValueError("Некорректный расход или фасовка клея")
        kg = a * r
        n = ceil_int(kg / m)
        return Calc(Decimal(n), "уп",
                    (f"{a} м² × {r} кг/м² = {kg} кг; ceil({kg} / {m}) = {n} уп",))
    raise ValueError("Для клея нужно покрытие упаковки или расход вместе с массой упаковки")


def rolls(
    room: Room,
    roll_width_m: Number,
    roll_length_m: Number,
    rapport_m: Number = 0,
    match: Literal["straight", "drop"] = "straight",
    trim_m: Number = "0.1",
    reserve_rolls: int = 0,
) -> Calc:
    width, length, rap, trim = d(roll_width_m), d(roll_length_m), d(rapport_m), d(trim_m)
    if width <= 0 or length <= 0 or rap < 0 or trim < 0 or reserve_rolls < 0:
        raise ValueError("Некорректные параметры обоев")
    strip = room.height_m + trim
    ex = [f"Длина полотна: высота {room.height_m} м + припуск {trim} м = {strip} м"]
    if rap > 0:
        strip = ceil_int(strip / rap) * rap
        ex.append(f"С учётом раппорта {rap} м полотно округляется вверх: {strip} м")
        if match == "drop":
            strip += rap / 2
            ex.append(f"Со смещением (drop) добавляем половину раппорта: {strip} м")
    per_roll = floor_int(length / strip)
    if per_roll < 1:
        raise ValueError("Полотно длиннее рулона")
    ex.append(f"Полотен из рулона {length} м: floor({length}/{strip}) = {per_roll}")
    per_wall = [ceil_int(w / width) for w in room.wall_net_widths_m()]
    strips = sum(per_wall)
    ex.append(f"Полотен по стенам (ширина рулона {width} м): {per_wall} = {strips}")
    n = ceil_int(Decimal(strips) / per_roll) + reserve_rolls
    ex.append(f"Рулонов: ceil({strips}/{per_roll}) + запас {reserve_rolls} = {n}")
    return Calc(Decimal(n), "рулон", tuple(ex))
