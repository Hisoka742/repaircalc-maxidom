"""Labor cost range. Rates are data (knowledge/work_rates.yaml), never hard-coded here.

A rate with no value (rub_per_unit is None) is an error: we do not guess prices.
Result is explicitly approximate: low / expected / high.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from maxicalc.engine.units import Number, d

CENT = Decimal("0.01")


@dataclass(frozen=True)
class WorkRate:
    work: str
    unit: str
    rub_per_unit: Decimal | None
    source: str
    p25: Decimal | None = None
    p75: Decimal | None = None

    def at_tier(self, tier: str) -> Decimal | None:
        """Price at a sourced tier: p25 / median / p75 (falls back to the median)."""
        if tier == "p25" and self.p25 is not None:
            return self.p25
        if tier == "p75" and self.p75 is not None:
            return self.p75
        return self.rub_per_unit


@dataclass(frozen=True)
class Spread:
    low: Decimal
    high: Decimal


@dataclass(frozen=True)
class LaborEstimate:
    low: Decimal
    expected: Decimal
    high: Decimal
    explain: tuple[str, ...]


def estimate_total(
    base: Number, region_coeff: Number, class_mult: Number, spread: Spread
) -> LaborEstimate:
    """Range for an already summed base cost (sum of quantity x rate over the works)."""
    b, rc, cm = d(base), d(region_coeff), d(class_mult)
    if b < 0 or rc <= 0 or cm <= 0 or not (0 < spread.low <= 1 <= spread.high):
        raise ValueError("Некорректные параметры расчёта работ")
    exp = (b * rc * cm).quantize(CENT, rounding=ROUND_HALF_UP)
    low = (b * rc * cm * spread.low).quantize(CENT, rounding=ROUND_HALF_UP)
    high = (b * rc * cm * spread.high).quantize(CENT, rounding=ROUND_HALF_UP)
    return LaborEstimate(low, exp, high, ())


def estimate(
    work: str,
    quantity: Number,
    rates: dict[str, WorkRate],
    region_coeff: Number,
    class_mult: Number,
    spread: Spread,
) -> LaborEstimate:
    rate = rates.get(work)
    if rate is None or rate.rub_per_unit is None:
        raise ValueError(f"Не задана ставка для работы «{work}»")
    q, rc, cm = d(quantity), d(region_coeff), d(class_mult)
    if q < 0 or rc <= 0 or cm <= 0 or not (0 < spread.low <= 1 <= spread.high):
        raise ValueError("Некорректные параметры расчёта работ")
    base = q * rate.rub_per_unit * rc * cm

    def money(x: Decimal) -> Decimal:
        return x.quantize(CENT, rounding=ROUND_HALF_UP)

    exp, low, high = money(base), money(base * spread.low), money(base * spread.high)
    return LaborEstimate(
        low, exp, high,
        (f"{q} {rate.unit} × {rate.rub_per_unit} ₽ × регион {rc} × класс {cm} = {exp} ₽",
         f"Диапазон (приблизительно): {low} – {high} ₽; ставка: {rate.source}"),
    )
