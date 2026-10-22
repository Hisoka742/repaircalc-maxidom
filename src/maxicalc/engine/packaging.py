"""Pack optimisation: min-cost integer cover of a required quantity.

Exact DP (unbounded knapsack, "at least Q"). Ties broken by smaller overbuy, then fewer packs.
"""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from math import gcd, lcm

from maxicalc.engine.units import ceil_int

MAX_DP_STEPS = 200_000


@dataclass(frozen=True)
class Pack:
    sku: str
    size: Decimal
    price: Decimal


@dataclass(frozen=True)
class PackLine:
    pack: Pack
    count: int


@dataclass(frozen=True)
class PackPlan:
    lines: tuple[PackLine, ...]
    required: Decimal

    @property
    def total_cost(self) -> Decimal:
        return sum((ln.pack.price * ln.count for ln in self.lines), Decimal(0))

    @property
    def total_size(self) -> Decimal:
        return sum((ln.pack.size * ln.count for ln in self.lines), Decimal(0))

    @property
    def overbuy(self) -> Decimal:
        return self.total_size - self.required


def single_sku_options(required: Decimal, packs: list[Pack]) -> list[PackPlan]:
    """ceil(Q / size) for each pack on its own, cheapest first."""
    if required <= 0:
        return []
    plans = [PackPlan((PackLine(p, ceil_int(required / p.size)),), required) for p in packs]
    return sorted(plans, key=lambda p: (p.total_cost, p.overbuy))


def optimal_cover(required: Decimal, packs: list[Pack]) -> PackPlan:
    if not packs:
        raise ValueError("Нет доступных фасовок")
    if any(p.size <= 0 or p.price < 0 for p in packs):
        raise ValueError("Некорректная фасовка")
    if required <= 0:
        return PackPlan((), required)

    fr = [Fraction(p.size) for p in packs]
    scale = lcm(*(f.denominator for f in fr))
    sizes = [int(f * scale) for f in fr]
    g = gcd(*sizes)
    sizes = [s // g for s in sizes]
    target = _ceil_frac(Fraction(required) * scale / g)
    if target > MAX_DP_STEPS:
        return single_sku_options(required, packs)[0]

    # dp[i] = (cost, total_size, count) minimal to cover at least i units
    dp: list[tuple[Decimal, int, int]] = [(Decimal(0), 0, 0)]
    choice = [-1]
    for i in range(1, target + 1):
        best: tuple[Decimal, int, int] | None = None
        best_j = -1
        for j, p in enumerate(packs):
            c, s, n = dp[max(0, i - sizes[j])]
            cand = (c + p.price, s + sizes[j], n + 1)
            if best is None or cand < best:
                best, best_j = cand, j
        assert best is not None
        dp.append(best)
        choice.append(best_j)

    counts = [0] * len(packs)
    i = target
    while i > 0:
        j = choice[i]
        counts[j] += 1
        i = max(0, i - sizes[j])
    return PackPlan(
        tuple(PackLine(p, c) for p, c in zip(packs, counts, strict=True) if c), required
    )


class _TooBig(Exception):
    pass


def cheapest_cover(required: Decimal, packs: list[Pack], max_nodes: int = 20_000) -> PackPlan:
    """Same objective and tie-breaks as `optimal_cover` (min cost, then less overbuy, then
    fewer packs), by branch and bound over the pack counts instead of a DP over a size grid.

    The DP's cost grows with the lcm of the pack sizes (0.9 l, 2.5 l, 9 l ...), which made it
    ~7 ms per basket line: too slow for the request path. This one visits only the counts that
    can beat the best plan so far, and falls back to the cheapest single-SKU option when the
    search would exceed `max_nodes` (never wrong, only not mixed)."""
    if not packs:
        raise ValueError("Нет доступных фасовок")
    if any(p.size <= 0 or p.price < 0 for p in packs):
        raise ValueError("Некорректная фасовка")
    if required <= 0:
        return PackPlan((), required)
    ordered = sorted(packs, key=lambda p: (-p.size, p.price))
    best: list[tuple[Decimal, Decimal, int, tuple[int, ...]]] = []   # one element at most
    nodes = 0

    def consider(cost: Decimal, size: Decimal, n: int, counts: tuple[int, ...]) -> None:
        cand = (cost, size, n, counts)
        if not best or cand[:3] < best[0][:3]:
            best[:] = [cand]

    def rec(i: int, rem: Decimal, cost: Decimal, size: Decimal, n: int,
            counts: tuple[int, ...]) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            raise _TooBig
        p = ordered[i]
        if i == len(ordered) - 1:
            k = ceil_int(rem / p.size) if rem > 0 else 0
            consider(cost + k * p.price, size + k * p.size, n + k, (*counts, k))
            return
        top = ceil_int(rem / p.size) if rem > 0 else 0
        for k in range(top + 1):
            c = cost + k * p.price
            if best and c > best[0][0]:
                break                      # more of this pack only costs more
            r = rem - k * p.size
            rec(i + 1, r if r > 0 else Decimal(0), c, size + k * p.size, n + k, (*counts, k))

    try:
        rec(0, required, Decimal(0), Decimal(0), 0, ())
    except _TooBig:
        return single_sku_options(required, packs)[0]
    counts = best[0][3]
    return PackPlan(tuple(PackLine(p, c) for p, c in zip(ordered, counts, strict=True) if c),
                    required)


def _ceil_frac(f: Fraction) -> int:
    return -((-f.numerator) // f.denominator)
