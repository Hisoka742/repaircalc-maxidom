"""Free-text parsing and the RAG explanation (with a mock LLM transport; no model needed)."""
import json
from decimal import Decimal as D

import httpx

from maxicalc.ml.llm_client import LLMClient
from maxicalc.ml.parse_request import parse_request, parse_rules
from maxicalc.recommend import rag


def llm_returning(payload: dict | None = None, status: int = 200) -> LLMClient:  # type: ignore[type-arg]
    def handler(req: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status)
        body = {"choices": [{"message": {"content": json.dumps(payload)}}]}
        return httpx.Response(200, json=body)

    return LLMClient("http://llm/v1", "m", retries=0, transport=httpx.MockTransport(handler))


# ---------------- parsing ----------------
def test_the_demo_phrase_is_fully_understood() -> None:
    p = parse_rules("Квартира, капитальный ремонт, санузел 6 м², высокая влажность")
    assert p.property_type == "apartment" and p.renovation_class == "major"
    assert [(r.room_type, r.area_m2, r.humidity) for r in p.rooms] == [("bathroom", D(6), "high")]
    assert "property_type" not in p.missing and "renovation_class" not in p.missing


def test_missing_things_are_reported_not_invented() -> None:
    p = parse_rules("ремонт ванной")
    assert [r.room_type for r in p.rooms] == ["bathroom"] and p.rooms[0].area_m2 is None
    assert {"property_type", "renovation_class", "room_area_m2"} <= set(p.missing)


def test_several_rooms_and_total_area() -> None:
    p = parse_rules("студия 28 м2 косметический, кухня 7 м2 и ванная 4,5 м2")
    assert p.property_type == "studio" and p.total_area_m2 == D(28)
    got = {(r.room_type, r.area_m2) for r in p.rooms}
    assert got == {("kitchen", D(7)), ("bathroom", D("4.5"))}


def test_room_count_is_not_a_living_room() -> None:
    p = parse_rules("2-комнатная квартира 54 м2 капитальный")
    assert p.rooms == [] and p.total_area_m2 == D(54)


def test_absurd_area_is_ignored() -> None:
    assert parse_rules("кухня 9000 м2").rooms[0].area_m2 is None


def test_llm_fallback_is_validated() -> None:
    llm = llm_returning({"property_type": "apartment", "renovation_class": "major",
                         "total_area_m2": 60, "rooms": [
                             {"room_type": "bathroom", "area_m2": 6, "humidity": "high"},
                             {"room_type": "kitchen", "area_m2": 9000, "humidity": None}]})
    p = parse_request("мне нужен ремонт для семьи", llm)   # rules find nothing
    assert p.method == "llm"
    by = {r.room_type: r for r in p.rooms}
    assert by["bathroom"].area_m2 == D(6) and by["bathroom"].humidity == "high"
    assert by["kitchen"].area_m2 is None                    # implausible area dropped, not kept


def test_an_answer_outside_the_schema_is_rejected_and_rules_win() -> None:
    llm = llm_returning({"property_type": "apartment", "renovation_class": "major",
                         "total_area_m2": 60, "rooms": [
                             {"room_type": "garage", "area_m2": 20, "humidity": None}]})
    p = parse_request("санузел 6 м2", llm)
    assert p.method == "rules" and p.rooms[0].room_type == "bathroom"


def test_llm_down_falls_back_to_rules() -> None:
    p = parse_request("санузел 6 м2", llm_returning(status=503))
    assert p.method == "rules" and p.rooms[0].room_type == "bathroom"


# ---------------- RAG ----------------
def ctx() -> rag.Context:
    return rag.Context(
        rooms=[("bathroom", "6")],
        lines=[rag.LineCtx("D1", "Гипсокартон влагостойкий", "drywall", 3, "лист", "1200",
                           "подходит для ванной")],
        total="1200", warnings=[], overlays={"wet_zone"}, room_names_ru={"bathroom": "Ванная"})


def test_retrieval_finds_the_wet_room_facts_and_not_unrelated_ones() -> None:
    ids = {f.id for f in rag.retrieve({"drywall"}, {"bathroom"}, {"wet_zone"})}
    assert "drywall-wet" in ids and "round-once" in ids
    assert "laminate-wear" not in ids and "wallpaper-strips" not in ids


def test_no_llm_gives_a_template_with_every_number_from_the_estimate() -> None:
    out = rag.explain(ctx(), None)
    assert out.method == "template" and "1200" in out.text and "3 лист" in out.text


def test_good_llm_answer_is_used_and_cites_known_facts() -> None:
    llm = llm_returning({"explanation": "Для ванной выбран влагостойкий гипсокартон: 3 листа.",
                         "used_fact_ids": ["drywall-wet"]})
    out = rag.explain(ctx(), llm)
    assert out.method == "llm" and [f.id for f in out.facts] == ["drywall-wet"]


def test_llm_that_invents_a_number_is_rejected() -> None:
    llm = llm_returning({"explanation": "Нужно 7 листов гипсокартона.",
                         "used_fact_ids": ["drywall-wet"]})
    out = rag.explain(ctx(), llm)
    assert out.method == "template" and "7" in out.note


def test_llm_citing_an_unknown_fact_is_rejected() -> None:
    llm = llm_returning({"explanation": "Подходит.", "used_fact_ids": ["made-up"]})
    assert rag.explain(ctx(), llm).method == "template"


def test_llm_outage_is_reported_not_raised() -> None:
    out = rag.explain(ctx(), llm_returning(status=500))
    assert out.method == "template" and "LLM недоступен" in out.note
