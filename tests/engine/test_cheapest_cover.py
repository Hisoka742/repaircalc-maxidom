"""cheapest_cover must agree with the exact DP (optimal_cover) and be fast on awkward sizes."""
import random
import time
from decimal import Decimal as D

from maxicalc.engine.packaging import Pack, cheapest_cover, optimal_cover, single_sku_options


def test_matches_the_dp_on_random_small_instances() -> None:
    rnd = random.Random(7)
    for _ in range(300):
        k = rnd.choice([2, 3, 4])
        packs = [Pack(f"S{i}", D(str(rnd.choice([0.5, 0.9, 1, 1.5, 2, 2.5, 3, 4, 5, 9, 10]))),
                      D(rnd.randint(100, 4000))) for i in range(k)]
        if len({p.size for p in packs}) < k:
            continue
        req = D(str(round(rnd.uniform(0.5, 60), 1)))
        a, b = cheapest_cover(req, packs), optimal_cover(req, packs)
        assert (a.total_cost, a.total_size, sum(ln.count for ln in a.lines)) == (
            b.total_cost, b.total_size, sum(ln.count for ln in b.lines)), (req, packs)
        assert a.total_size >= req


def test_never_worse_than_the_best_single_sku() -> None:
    packs = [Pack("a", D("2.5"), D(1000)), Pack("b", D(9), D(2200))]
    plan = cheapest_cover(D(11), packs)
    assert plan.total_cost == D(3200)
    assert plan.total_cost <= single_sku_options(D(11), packs)[0].total_cost


def test_awkward_sizes_are_fast_where_the_dp_is_not() -> None:
    packs = [Pack("a", D("0.9"), D(400)), Pack("b", D("2.5"), D(900)), Pack("c", D("9"), D(2900))]
    t0 = time.perf_counter()
    for r in range(1, 60):
        cheapest_cover(D(r) + D("0.3"), packs)
    assert (time.perf_counter() - t0) / 59 < 0.002        # well under 2 ms each


def test_a_huge_search_falls_back_to_a_single_sku_not_a_wrong_answer() -> None:
    packs = [Pack("a", D("0.37"), D(10)), Pack("b", D("0.41"), D(11)), Pack("c", D("0.43"), D(12)),
             Pack("d", D("0.47"), D(13))]
    plan = cheapest_cover(D(5000), packs, max_nodes=50)
    assert plan.total_size >= 5000 and len(plan.lines) == 1


def test_zero_requirement_and_bad_packs() -> None:
    assert cheapest_cover(D(0), [Pack("a", D(1), D(1))]).lines == ()
    import pytest

    with pytest.raises(ValueError):
        cheapest_cover(D(3), [])
    with pytest.raises(ValueError):
        cheapest_cover(D(3), [Pack("a", D(0), D(1))])
