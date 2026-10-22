"""Ranking without ratings: hard constraints first, then card completeness (calculable products
before poorly described ones); rating and margin weights stay at 0 until such fields exist."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.recommend.select import CatalogEntry, completeness, recommend


def ent(sku: str, attrs: dict, chars: int, rating: str | None = None) -> CatalogEntry:  # type: ignore[type-arg]
    p = Product(sku=sku, name=sku, price=D(100),
                characteristics={f"k{i}": "v" for i in range(chars)},
                recsys_rating=None if rating is None else D(rating))
    return CatalogEntry(p, work=set(), rooms={"any"}, props=set(), calc="paint",
                        status="verified", attrs=attrs)


FULL = ent("Z-full", {"spread_m2_per_l": D(8), "pack_volume_l": D(9)}, 8)
BARE = ent("A-bare", {}, 0)


def test_completeness_scale() -> None:
    assert completeness(FULL) > 0.95
    assert completeness(BARE) < 0.2


def test_weight_zero_keeps_alphabetical_tiebreak() -> None:
    res = recommend([FULL, BARE], "living", calc="paint", completeness_weight=0.0)
    assert [c.entry.product.sku for c in res.items] == ["A-bare", "Z-full"]


def test_completeness_lifts_calculable_card() -> None:
    res = recommend([FULL, BARE], "living", calc="paint", completeness_weight=0.2)
    assert next(c.entry.product.sku for c in res.items) == "Z-full"


def test_rating_weight_zero_disables_popularity() -> None:
    hi = ent("B-hi", {}, 0, rating="5")
    lo = ent("A-lo", {}, 0, rating="1")
    off = recommend([hi, lo], "living", calc="paint", rating_weight=0.0)
    assert [c.entry.product.sku for c in off.items] == ["A-lo", "B-hi"]
    legacy = recommend([hi, lo], "living", calc="paint")           # None = legacy tie-break
    assert next(c.entry.product.sku for c in legacy.items) == "B-hi"
