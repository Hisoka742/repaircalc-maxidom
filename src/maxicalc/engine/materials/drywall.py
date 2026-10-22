"""Drywall (ГКЛ/ГКЛВ): sheets and per-m2 system quantities.

sheets = ceil(area x 1.1 / sheet area)  (plan 5.2; 10% waste is a team default).

Knauf system norms (quantity per 1 m2 of system) were taken from the Knauf product-system
pages for C 111 (single metal frame, one layer 12.5 mm each side) and C 611 (glued lining),
read via a search-tool excerpt because knauf.com returned HTTP 403 to direct fetches:
UNVERIFIED against the page itself. Knauf states the numbers are indicative and exclude
cutting losses.
"""
from decimal import Decimal

from maxicalc.engine.result import Calc
from maxicalc.engine.units import Number, ceil_int, d

WASTE = Decimal("0.10")

# name -> (quantity per 1 m2, unit)
Norms = dict[str, tuple[Decimal, str]]

KNAUF_C111: Norms = {
    "sheet_12_5": (Decimal("2.0"), "м²"),
    "profile_pn_50x40": (Decimal("0.7"), "м"),
    "profile_ps_50": (Decimal("2.0"), "м"),
    "screws_tn25": (Decimal("29"), "шт"),
    "sealing_tape": (Decimal("1.2"), "м"),
    "putty_fugen": (Decimal("0.6"), "кг"),
    "reinforcing_tape": (Decimal("1.5"), "м"),
    "dowel_nail_6x40": (Decimal("1.6"), "шт"),
}

KNAUF_C611: Norms = {
    "sheet": (Decimal("1.0"), "м²"),
    "reinforcing_tape": (Decimal("0.75"), "м"),
    "putty_fugen_joints": (Decimal("0.3"), "кг"),
    "adhesive_perlfix": (Decimal("3.5"), "кг"),
}


def sheets(area_m2: Number, sheet_w_m: Number, sheet_h_m: Number) -> Calc:
    a, w, h = d(area_m2), d(sheet_w_m), d(sheet_h_m)
    if a < 0 or w <= 0 or h <= 0:
        raise ValueError("Некорректные параметры ГКЛ")
    sheet = w * h
    need = a * (1 + WASTE)
    n = ceil_int(need / sheet)
    return Calc(
        Decimal(n), "лист",
        (f"Лист {w}×{h} = {sheet} м²; {a} м² × (1 + {WASTE}) = {need} м²",
         f"ceil({need} / {sheet}) = {n} лист"),
    )


def system_quantities(area_m2: Number, norms: Norms) -> dict[str, Calc]:
    a = d(area_m2)
    if a < 0:
        raise ValueError("Площадь не может быть отрицательной")
    return {
        name: Calc(a * per, unit, (f"{a} м² × {per} {unit}/м² = {a * per} {unit}",))
        for name, (per, unit) in norms.items()
    }
