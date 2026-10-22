"""LLM-inferred attributes: stored apart from facts, used above a threshold, stated in explain."""
from decimal import Decimal as D
from typing import Any

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Room
from maxicalc.ml.match import LabelDecision, MatchResult
from maxicalc.recommend.build import to_entries
from maxicalc.recommend.inferred import effective_entry
from maxicalc.recommend.select import CatalogEntry, Inferred
from maxicalc.service.property_calc import calc_room

ROOM = Room.rectangle(4, 3, "2.5")


def paint(inferred: dict[str, Inferred], facts: dict[str, Any] | None = None) -> CatalogEntry:
    attrs: dict[str, Any] = {"pack_volume_l": D("2.5")}
    attrs.update(facts or {})
    return CatalogEntry(Product(sku="P", name="Краска", price=D(100)), work=set(),
                        rooms={"any"}, props=set(), calc="paint", status="verified",
                        attrs=attrs, inferred=inferred)


def test_inferred_value_is_used_only_at_or_above_the_threshold() -> None:
    e = paint({"spread_m2_per_l": Inferred(D("10"), "low", "расход 10 м2/л")})
    low, notes, held = effective_entry(e, "medium")
    assert "spread_m2_per_l" not in low.attrs and held == ["spread_m2_per_l"] and not notes
    ok, notes, held = effective_entry(e, "low")
    assert ok.attrs["spread_m2_per_l"] == D("10") and not held
    assert "расход 10 м2/л" in notes[0] and "уверенность low" in notes[0]


def test_a_fact_is_never_overwritten_by_an_inference() -> None:
    e = paint({"spread_m2_per_l": Inferred(D("99"), "high", "q")},
              facts={"spread_m2_per_l": D("10")})
    eff, notes, _ = effective_entry(e, "low")
    assert eff.attrs["spread_m2_per_l"] == D("10") and not notes


def test_room_calc_says_it_used_an_inferred_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERRED_MIN_CONFIDENCE", "low")
    e = paint({"spread_m2_per_l": Inferred(D("10"), "low", "расход 10 м2/л")})
    est = calc_room(ROOM, "living", "cosmetic", [e])
    line = next(ln for ln in est.basket.lines if ln.sku == "P")
    assert any("получено моделью" in x for x in line.explain)


def test_below_threshold_the_card_is_unusable_and_the_warning_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFERRED_MIN_CONFIDENCE", "medium")
    e = paint({"spread_m2_per_l": Inferred(D("10"), "low", "расход 10 м2/л")})
    est = calc_room(ROOM, "living", "cosmetic", [e])
    assert all(ln.sku != "P" for ln in est.basket.lines)
    assert any("ниже порога" in w for w in est.warnings)


class FakeLLM:
    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {f: {"value": 12, "quote": "12 кв.м на литр"} for f in schema["properties"]}


def test_build_stores_llm_values_apart_from_facts() -> None:
    p = Product(sku="P", name="Краска белая 2.5 л", description="Хватает на 12 кв.м на литр",
                price=D(100))
    result = MatchResult(sku="P", calc_template=LabelDecision("paint", 0.99, "rule", True))
    (e,) = to_entries([p], [result], FakeLLM())  # type: ignore[arg-type]
    assert "spread_m2_per_l" not in e.attrs                    # not a fact
    inf = e.inferred["spread_m2_per_l"]
    assert inf.source == "llm" and inf.confidence == "low" and inf.evidence == "12 кв.м на литр"
    (plain,) = to_entries([p], [result])                       # without an LLM: nothing inferred
    assert plain.inferred == {}
