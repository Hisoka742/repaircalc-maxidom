"""Labor cost for an estimate: work quantities come from the room geometry (never from packs),
rates and multipliers come from `knowledge/work_rates.yaml`.

A renovation class has no multiplier: it differs by WORK SCOPE (which works are included) and
by price tier (cosmetic = p25, major = median, designer = p75 of the sourced rates). Without a
rate for a used work, or a spread, there is NO labor figure and the note says exactly what is
missing: this module never guesses a price.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from maxicalc.engine import labor as labor_engine
from maxicalc.engine.labor import Spread, WorkRate
from maxicalc.engine.units import d

REGION = "spb"   # the base region of the table; others need their own coefficient

WORK_RU = {
    "painting_walls": "покраска стен и потолка", "priming": "грунтование",
    "puttying": "шпатлёвка", "wallpapering": "оклейка обоев", "waterproofing": "гидроизоляция",
    "drywall_lining": "обшивка гипсокартоном", "laminate": "укладка ламината",
    "tiling_floor": "укладка плитки на пол", "tiling_wall": "укладка плитки на стены",
    "skirting": "монтаж плинтуса", "self_leveling": "наливной пол",
    "electrical_point": "электроточка (розетка, выключатель, светильник)",
}


@dataclass(frozen=True)
class WorkLine:
    work: str
    title: str
    quantity: Decimal
    unit: str
    rate: Decimal
    expected: Decimal   # quantity x rate at the class's price tier


@dataclass
class LaborResult:
    low: Decimal
    expected: Decimal
    high: Decimal
    items: list[WorkLine] = field(default_factory=list)
    explain: list[str] = field(default_factory=list)


def _sum_quantities(plans: list) -> dict[str, tuple[Decimal, str]]:  # type: ignore[type-arg]
    out: dict[str, tuple[Decimal, str]] = {}
    for p in plans:
        for work, (qty, unit) in p.works.items():
            cur = out.get(work, (Decimal(0), unit))[0]
            out[work] = (cur + qty, unit)
    return out


def compute_labor(
    plans: list,  # type: ignore[type-arg]
    renovation_class: str,
    rates: dict[str, WorkRate],
    class_tier: dict[str, str],
    scope: dict[str, frozenset[str]],
    region_coeff: dict[str, Decimal],
    spread: Spread | None,
) -> tuple[LaborResult | None, str]:
    tier = class_tier.get(renovation_class)
    included = scope.get(renovation_class)
    if tier is None or included is None:
        return None, (f"Для класса «{renovation_class}» не заданы объём работ и уровень цен, "
                      "стоимость работ не рассчитана")
    all_qty = _sum_quantities(plans)
    qty = {w: v for w, v in all_qty.items() if w in included}
    skipped = sorted(w for w in all_qty if w not in included)
    if not qty:
        return None, "Нет работ для расчёта стоимости"
    missing = sorted(w for w in qty if rates.get(w) is None or rates[w].rub_per_unit is None)
    if missing:
        return None, ("Ставки работ не заданы: " + ", ".join(missing)
                      + ". Стоимость работ не рассчитана, цены не придумываются")
    if spread is None:
        return None, "Не задан разброс (min/max) ставок, диапазон стоимости работ не рассчитан"
    rc = region_coeff.get(REGION)
    if rc is None:
        return None, f"Не задан коэффициент региона {REGION}"
    items: list[WorkLine] = []
    for work, (q, unit) in sorted(qty.items()):
        rate = rates[work].at_tier(tier)
        assert rate is not None
        items.append(WorkLine(work, WORK_RU.get(work, work), q, unit, rate, q * rate))
    base = sum((i.expected for i in items), Decimal(0))
    est = labor_engine.estimate_total(base, rc, 1, spread)
    explain = [f"{i.title}: {i.quantity} {i.unit} × {i.rate} ₽ = {i.expected} ₽" for i in items]
    explain.append(
        f"Уровень цен класса «{renovation_class}»: {tier} опубликованных прайс-листов")
    if skipped:
        explain.append("Не входят в объём этого класса: "
                       + ", ".join(WORK_RU.get(w, w) for w in skipped))
    explain.append(f"Сумма {base} ₽ × регион {rc} = {est.expected} ₽")
    explain.append(f"Диапазон: {est.low} – {est.high} ₽ "
                   f"(разброс ставок {spread.low}–{spread.high})")
    return LaborResult(est.low, est.expected, est.high, items, explain), ""


__all__ = ["LaborResult", "WorkLine", "compute_labor", "d"]
