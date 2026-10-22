"""Price tiers within a matched category: economy <= p25, premium >= p75, else standard.

`PriceScale` sorts the pool once; tier and rank lookups are O(log n). Building it per
candidate (sorting the pool each time) made recommend() quadratic.
"""
from bisect import bisect_left, bisect_right
from decimal import Decimal

Tier = str  # "economy" | "standard" | "premium"
TIER_TARGET_RANK = {"economy": 0.15, "standard": 0.5, "premium": 0.85}


def _quantile(sorted_vals: list[Decimal], q: Decimal) -> Decimal:
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


class PriceScale:
    def __init__(self, pool: list[Decimal]) -> None:
        self._sorted = sorted(pool)
        self._p25: Decimal | None = None
        self._p75: Decimal | None = None
        if len(self._sorted) >= 2:
            self._p25 = _quantile(self._sorted, Decimal("0.25"))
            self._p75 = _quantile(self._sorted, Decimal("0.75"))

    def tier(self, price: Decimal) -> Tier:
        if self._p25 is None or self._p75 is None or self._p25 == self._p75:
            return "standard"
        if price <= self._p25:
            return "economy"
        if price >= self._p75:
            return "premium"
        return "standard"

    def rank(self, price: Decimal) -> float:
        """Mid-rank percentile of `price` in the pool, in [0, 1]."""
        n = len(self._sorted)
        if n == 0:
            return 0.5
        below = bisect_left(self._sorted, price)
        equal = bisect_right(self._sorted, price) - below
        return (below + 0.5 * equal) / n


def price_tier(price: Decimal, pool: list[Decimal]) -> Tier:
    return PriceScale(pool).tier(price)


def price_rank(price: Decimal, pool: list[Decimal]) -> float:
    return PriceScale(pool).rank(price)
