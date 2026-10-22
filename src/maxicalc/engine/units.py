"""Numeric helpers. All engine arithmetic is Decimal; round to purchasable units last."""
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

Number = int | str | float | Decimal


def d(x: Number) -> Decimal:
    """Convert to Decimal at the boundary (floats via their shortest repr)."""
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def ceil_int(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_CEILING))


def floor_int(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_FLOOR))


def mm_to_m(x: Decimal) -> Decimal:
    return x / 1000
