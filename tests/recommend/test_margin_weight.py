"""Checklist E3: margin is a configurable ranking weight, inactive until a margin field exists."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.recommend.index import CatalogIndex
from maxicalc.recommend.select import CatalogEntry, Constraints, recommend


def ent(sku: str, margin: str | None, rating: str | None = None) -> CatalogEntry:
    p = Product(sku=sku, name=sku, price=D(100), margin=None if margin is None else D(margin),
                recsys_rating=None if rating is None else D(rating))
    return CatalogEntry(p, work=set(), rooms={"any"}, props=set(), calc="paint",
                        status="verified")


CAT = [ent("A", "0.10"), ent("B", "0.60"), ent("C", None)]


def skus(res) -> list[str]:  # type: ignore[no-untyped-def]
    return [c.entry.product.sku for c in res.items]


def test_weight_zero_ignores_margin() -> None:
    res = recommend(CAT, "living", calc="paint", margin_weight=0.0)
    assert skus(res) == ["A", "B", "C"]            # ties broken by sku, margin not used


def test_positive_weight_lifts_high_margin_but_not_over_a_hard_rule() -> None:
    res = recommend(CAT, "living", calc="paint", margin_weight=1.0)
    assert skus(res)[0] == "B"
    assert skus(res)[-1] == "C"                    # unknown margin gets no bonus
    # a hard room rule still removes a product whatever its margin
    wet = CatalogEntry(Product(sku="D", name="D", price=D(100), margin=D("0.99")), work=set(),
                       rooms={"any"}, props=set(), calc="drywall", status="verified")
    res2 = recommend([wet], "bathroom", calc="drywall", margin_weight=5.0)
    assert res2.items == [] and res2.excluded


def test_the_index_passes_the_configured_weight() -> None:
    idx = CatalogIndex(CAT, margin_weight=1.0)
    res = idx.query("living", None, "paint", Constraints(), 3)
    assert skus(res)[0] == "B"


def test_popularity_breaks_ties_but_margin_weight_is_independent() -> None:
    cat = [ent("A", None, rating="4.9"), ent("B", None, rating="1.0")]
    assert skus(recommend(cat, "living", calc="paint")) == ["A", "B"]
