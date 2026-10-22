from decimal import Decimal as D
from itertools import product

from hypothesis import given, settings
from hypothesis import strategies as st

from maxicalc.engine.packaging import Pack, optimal_cover, single_sku_options

PAINT = [Pack("p09", D("0.9"), D("500")), Pack("p25", D("2.5"), D("1100")),
         Pack("p9", D("9"), D("3500"))]


def test_paint_10l() -> None:
    plan = optimal_cover(D("10"), PAINT)
    assert plan.total_cost == 4400
    assert {ln.pack.sku: ln.count for ln in plan.lines} == {"p25": 4}
    assert plan.overbuy == 0


def test_paint_9_5l_mixes_sizes() -> None:
    plan = optimal_cover(D("9.5"), PAINT)
    assert plan.total_cost == 4000
    assert {ln.pack.sku: ln.count for ln in plan.lines} == {"p9": 1, "p09": 1}


def test_single_sku_options_sorted() -> None:
    opts = single_sku_options(D("10"), PAINT)
    assert [(o.lines[0].pack.sku, o.lines[0].count, o.total_cost) for o in opts] == [
        ("p25", 4, D("4400")), ("p09", 12, D("6000")), ("p9", 2, D("7000"))]


def test_zero_required() -> None:
    assert optimal_cover(D("0"), PAINT).lines == ()


@settings(deadline=None)  # brute-force reference is slow on a cold start
@given(
    req=st.integers(1, 30),
    sizes=st.lists(st.integers(1, 9), min_size=1, max_size=3, unique=True),
    prices=st.lists(st.integers(1, 30), min_size=3, max_size=3),
)
def test_matches_brute_force(req: int, sizes: list[int], prices: list[int]) -> None:
    packs = [Pack(f"s{s}", D(s), D(prices[i])) for i, s in enumerate(sizes)]
    plan = optimal_cover(D(req), packs)
    assert plan.total_size >= req
    best = None
    for counts in product(range(0, 32), repeat=len(packs)):
        if sum(c * int(p.size) for c, p in zip(counts, packs, strict=True)) >= req:
            cost = sum(c * p.price for c, p in zip(counts, packs, strict=True))
            best = cost if best is None else min(best, cost)
    assert plan.total_cost == best
