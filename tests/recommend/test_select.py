from decimal import Decimal as D

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.metrics import ndcg_at_k
from maxicalc.ml.taxonomy import load_taxonomy
from maxicalc.recommend.companions import companions_for
from maxicalc.recommend.rules_kb import load_room_rules
from maxicalc.recommend.select import CatalogEntry, Constraints, recommend
from maxicalc.recommend.tiers import price_rank, price_tier


def entry(sku: str, calc: str, price: str | None, props: set[str] | None = None,
          rooms: set[str] | None = None, work: set[str] | None = None,
          status: str = "auto") -> CatalogEntry:
    return CatalogEntry(
        product=Product(sku=sku, name=f"Товар {sku}", price=None if price is None else D(price)),
        work=work or set(), rooms=rooms or {"any"}, props=props or set(), calc=calc,
        status=status)


def skus(r) -> list[str]:  # type: ignore[no-untyped-def]
    return [c.entry.product.sku for c in r.items]


# ---------- knowledge base ----------
def test_room_rules_reference_only_valid_labels() -> None:
    t = load_taxonomy()
    kb = load_room_rules()
    assert {"bathroom", "kitchen", "kids", "balcony", "hallway"} <= set(kb.rooms)
    for room, rr in kb.rooms.items():
        assert room in t.room_types
        for rule in [*rr.hard, *rr.soft]:
            assert set(rule.calc) <= set(t.calc_templates), (room, rule)
            assert set(rule.work) <= set(t.work_categories), (room, rule)
            assert set(getattr(rule, "require_any", ())) <= set(t.properties), (room, rule)
            assert set(getattr(rule, "prefer", ())) <= set(t.properties), (room, rule)
            assert rule.reason


# ---------- hard filters ----------
CAT = [
    entry("A", "paint", "1000", {"moisture_resistant"}),
    entry("B", "paint", "800"),
    entry("C", "drywall", "300"),
    entry("D", "drywall", "400", {"moisture_resistant"}),
    entry("E", "paint", "900", {"low_emission"}, rooms={"kids"}),
    entry("F", "paint", "700", {"low_emission"}),
    entry("G", "paint", "600", {"washable"}),
]


def test_bathroom_paint_requires_moisture_or_washable() -> None:
    r = recommend(CAT, "bathroom", calc="paint")
    assert set(skus(r)) == {"A", "G"}
    assert any(sku == "B" for sku, _ in r.excluded)


def test_bathroom_drywall_must_be_moisture_resistant() -> None:
    r = recommend(CAT, "bathroom", calc="drywall")
    assert skus(r) == ["D"]
    reason = dict(r.excluded)["C"]
    assert "влагостойк" in reason


def test_room_specific_product_is_not_offered_for_other_room() -> None:
    r = recommend(CAT, "kitchen", calc="paint")
    assert "E" not in skus(r)
    assert "washable" not in "".join(r.warnings)  # sanity: warnings are human text


def test_room_specific_product_ranks_first_in_its_room() -> None:
    r = recommend(CAT, "kids", calc="paint")
    assert skus(r)[0] == "E"  # kids-specific beats generic F; both are low-emission
    assert set(skus(r)) == {"E", "F"}


def test_unlabelled_or_review_items_are_not_recommended_by_default() -> None:
    cat = [entry("X", "drywall", "100", {"moisture_resistant"}, status="review")]
    assert recommend(cat, "bathroom", calc="drywall").items == []
    assert skus(recommend(cat, "bathroom", calc="drywall", include_review=True)) == ["X"]


def test_empty_result_carries_a_warning() -> None:
    r = recommend([entry("C", "drywall", "300")], "bathroom", calc="drywall")
    assert r.items == [] and r.warnings


def test_price_constraint_and_missing_price() -> None:
    cat = [entry("a", "paint", "500"), entry("b", "paint", "5000"), entry("c", "paint", None)]
    r = recommend(cat, "living", calc="paint", constraints=Constraints(max_price=D("1000")))
    assert skus(r) == ["a"]


def test_work_category_query() -> None:
    cat = [entry("w1", "paint", "1", work={"wall_finish_paint"}),
           entry("w2", "primer", "1", work={"wall_prep"})]
    assert skus(recommend(cat, "living", work="wall_prep")) == ["w2"]


def test_requires_calc_or_work() -> None:
    with pytest.raises(ValueError):
        recommend(CAT, "bathroom")


# ---------- scoring ----------
def test_soft_preference_ranks_higher() -> None:
    cat = [entry("plain", "tile", "1000"), entry("slip", "tile", "1000", {"anti_slip"})]
    assert skus(recommend(cat, "bathroom", calc="tile"))[0] == "slip"


def test_price_tier_selects_cheap_or_premium() -> None:
    cat = [entry(f"p{i}", "paint", str(100 * i), {"washable"}) for i in range(1, 11)]
    cheap = skus(recommend(cat, "kitchen", calc="paint", constraints=Constraints(tier="economy")))
    prem = skus(recommend(cat, "kitchen", calc="paint", constraints=Constraints(tier="premium")))
    assert cheap[0] in {"p1", "p2"} and prem[0] in {"p9", "p10"}


def test_ranking_is_deterministic() -> None:
    cat = [entry(s, "paint", "100", {"washable"}) for s in "dcba"]
    assert skus(recommend(cat, "kitchen", calc="paint")) == ["a", "b", "c", "d"]


def test_top_k() -> None:
    cat = [entry(str(i), "paint", str(i + 1), {"washable"}) for i in range(10)]
    assert len(recommend(cat, "kitchen", calc="paint", top_k=3).items) == 3


# ---------- reasons ----------
def test_reasons_are_russian_and_mention_matched_properties() -> None:
    cat = [entry("A", "paint", "1000", {"moisture_resistant", "wear_class_33"})]
    c = recommend(cat, "bathroom", calc="paint").items[0]
    text = " ".join(c.reasons)
    assert "влагостойк" in text and "ванн" in text


# ---------- tiers ----------
def test_price_tier_and_rank() -> None:
    pool = [D(x) for x in (100, 200, 300, 400, 500, 600, 700, 800)]
    assert price_tier(D("100"), pool) == "economy"
    assert price_tier(D("450"), pool) == "standard"
    assert price_tier(D("800"), pool) == "premium"
    assert price_rank(D("100"), pool) < price_rank(D("800"), pool)
    assert price_tier(D("5"), [D("5")]) == "standard"  # single-item pool


# ---------- companions ----------
def test_companions() -> None:
    assert companions_for("tile") == ["tile_adhesive", "grout", "tile_spacers"]
    assert companions_for("wallpaper") == ["wallpaper_glue", "primer"]
    assert companions_for("laminate") == ["underlay", "skirting"]
    assert companions_for("grout") == []
    assert companions_for("unknown") == []


# ---------- nDCG ----------
def test_ndcg() -> None:
    assert ndcg_at_k([3, 2, 0], [3, 2, 1], 5) == pytest.approx(
        (3 + 2 / 1.5849625007211562) / (3 + 2 / 1.5849625007211562 + 0.5))
    assert ndcg_at_k([], [], 5) == 1.0
    assert ndcg_at_k([0, 0], [0, 0], 5) == 1.0  # nothing relevant exists: perfect by convention


def test_recommend_scales_linearly_with_pool_size() -> None:
    """Regression: price tiers were recomputed (sorting the pool) per candidate -> quadratic,
    25-280 ms per call on 1000 products, which blocked the event loop under load."""
    import time

    cat = [entry(f"s{i}", "paint", str(100 + i % 997), {"washable"}) for i in range(3000)]
    t = time.perf_counter()
    r = recommend(cat, "kitchen", calc="paint", top_k=5)
    elapsed = time.perf_counter() - t
    assert len(r.items) == 5
    assert elapsed < 0.25, f"recommend took {elapsed:.2f}s on 3000 products"


def test_price_scale_matches_functions() -> None:
    from maxicalc.recommend.tiers import PriceScale

    pool = [D(x) for x in (100, 200, 300, 400, 500, 600, 700, 800)]
    scale = PriceScale(pool)
    for p in pool:
        assert scale.tier(p) == price_tier(p, pool)
        assert scale.rank(p) == pytest.approx(price_rank(p, pool))
