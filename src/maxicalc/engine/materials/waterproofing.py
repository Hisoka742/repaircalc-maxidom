"""Cement-polymer waterproofing (e.g. Ceresit CR 65).

Consumption by operating condition: Ceresit CR 65 technical description (Henkel TDX,
RU/KZ edition signed 2025-11-27): high humidity ~3.5 kg/m2 (layer 2.0-2.5 mm), water without
pressure ~4.5 kg/m2 (2.5-3.5 mm), water under pressure up to 0.05 MPa ~6.0 kg/m2 (3-4 mm).
A product-card value always takes precedence.

Treated-area geometry (floor + wall strip, shower zone) and corner tape follow the plan
(section 5.2) and are heuristics, not manufacturer figures.
"""
from decimal import Decimal

from maxicalc.engine.geometry import Room
from maxicalc.engine.result import Calc
from maxicalc.engine.units import Number, d

CR65_KG_PER_M2: dict[str, Decimal] = {
    "high_humidity": Decimal("3.5"),
    "water_no_pressure": Decimal("4.5"),
    "water_pressure": Decimal("6.0"),
    # same sheet: "Максимальная толщина слоя: 5,0 мм ~ 8,0 кг/м²"
    "max_thickness": Decimal("8.0"),
}


def kg(area_m2: Number, condition: str, kg_per_m2: Number | None = None) -> Calc:
    a = d(area_m2)
    if a < 0:
        raise ValueError("Площадь не может быть отрицательной")
    if kg_per_m2 is not None:
        rate, src = d(kg_per_m2), "из карточки товара"
    else:
        if condition not in CR65_KG_PER_M2:
            raise ValueError(f"Неизвестные условия эксплуатации: {condition}")
        rate, src = CR65_KG_PER_M2[condition], f"по таблице Ceresit CR 65 [{condition}]"
    if rate <= 0:
        raise ValueError("Некорректный расход")
    m = a * rate
    return Calc(m, "кг", (f"{a} м² × {rate} кг/м² ({src}) = {m} кг",))


def treated_area(
    room: Room, wall_up_m: Number = "0.3", shower_wall_m2: Number = 0
) -> Calc:
    """Floor + wall strip along the walls (no strip across door openings) + shower walls."""
    up, sh = d(wall_up_m), d(shower_wall_m2)
    if up < 0 or sh < 0:
        raise ValueError("Некорректные размеры зоны гидроизоляции")
    strip = room.skirting_length_m * up
    total = room.floor_area_m2 + strip + sh
    return Calc(
        total, "м²",
        (f"Пол {room.floor_area_m2} м² + стены на {up} м × {room.skirting_length_m} м = {strip} м²"
         f" + зона душа {sh} м² = {total} м²",),
    )


def corner_tape_m(room: Room) -> Calc:
    """Sealing tape along the wall/floor junction (not across doors)."""
    ln = room.skirting_length_m
    return Calc(ln, "м", (f"Лента по периметру пола без дверей: {ln} м",))
