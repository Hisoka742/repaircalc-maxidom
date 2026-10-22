"""Embedding relevance as a ranking term: off by default, never overrides a hard rule."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.ml.embed import HashingEmbedder
from maxicalc.recommend.relevance import RelevanceScorer, query_text
from maxicalc.recommend.select import CatalogEntry, recommend


def entry(sku: str, name: str, props: set[str]) -> CatalogEntry:
    p = Product(product_id=sku, sku=sku, name=name, category_path=["Краски"], price=D("100"))
    return CatalogEntry(p, {"wall_paint"}, {"any"}, props, "paint", "verified")


E = [entry("A", "Краска для стен влагостойкая моющаяся", {"moisture_resistant"}),
     entry("B", "Саморез по металлу 4х25", {"moisture_resistant"})]


def test_query_text_is_russian_and_names_room_and_need() -> None:
    t = query_text("bathroom", "paint")
    assert "краска" in t and "ванная" in t


def test_weight_zero_changes_nothing_and_positive_weight_reorders_by_similarity() -> None:
    base = recommend(E, "bathroom", calc="paint", top_k=2)
    scorer = RelevanceScorer(HashingEmbedder())
    rel = scorer.scores(E, "bathroom", "paint")
    assert rel["A"] > rel["B"]
    off = recommend(E, "bathroom", calc="paint", top_k=2, relevance=rel, relevance_weight=0.0)
    assert [c.score for c in off.items] == [c.score for c in base.items]
    on = recommend(E, "bathroom", calc="paint", top_k=2, relevance=rel, relevance_weight=0.5)
    assert on.items[0].entry.product.sku == "A"
    assert on.items[0].score > base.items[0].score


def test_relevance_never_resurrects_a_product_that_breaks_a_hard_rule() -> None:
    wet = entry("C", "Краска для ванной комнаты", set())   # no moisture_resistant: hard rule
    scorer = RelevanceScorer(HashingEmbedder())
    rel = scorer.scores([wet], "bathroom", "paint")
    res = recommend([wet], "bathroom", calc="paint", relevance=rel, relevance_weight=1.0)
    assert res.items == [] and res.excluded
