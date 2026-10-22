import json
from decimal import Decimal as D

import httpx
import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract_with_llm
from maxicalc.ml.llm_client import LLMClient, LLMError

TEXT = "Обои виниловые на флизелиновой основе, ширина 106 см, длина 10 м"


def product() -> Product:
    return Product(sku="1", name=TEXT)


def client(handler: httpx.MockTransport | object, **kw: object) -> LLMClient:
    transport = handler if isinstance(handler, httpx.MockTransport) else httpx.MockTransport(
        handler)  # type: ignore[arg-type]
    return LLMClient("http://llm/v1", "test-model", transport=transport, retries=1, **kw)  # type: ignore[arg-type]


def reply(payload: object) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})


def test_request_shape_is_constrained_and_deterministic() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(json.loads(req.content))
        seen["url"] = str(req.url)
        return reply({"roll_width_m": {"value": 1.06, "quote": "ширина 106 см"}})

    r = extract_with_llm(product(), client(handler), needed=["roll_width_m"])
    assert seen["url"] == "http://llm/v1/chat/completions"
    assert seen["temperature"] == 0
    rf = seen["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True  # type: ignore[index]
    assert "roll_width_m" in rf["json_schema"]["schema"]["properties"]  # type: ignore[index]
    a = r.attrs["roll_width_m"]
    assert a.value == D("1.06") and a.source == "llm" and a.confidence == "low"


def test_ungrounded_quote_is_rejected() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return reply({"roll_width_m": {"value": 1.06, "quote": "ширина 1,06 м"}})  # not in text

    r = extract_with_llm(product(), client(handler), needed=["roll_width_m"])
    assert "roll_width_m" not in r.attrs
    assert any("цитат" in x.reason for x in r.rejected)


def test_out_of_range_llm_value_is_rejected() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return reply({"roll_width_m": {"value": 106, "quote": "ширина 106 см"}})

    r = extract_with_llm(product(), client(handler), needed=["roll_width_m"])
    assert "roll_width_m" not in r.attrs and r.rejected


def test_null_means_not_found() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return reply({"roll_length_m": {"value": None, "quote": None}})

    r = extract_with_llm(product(), client(handler), needed=["roll_length_m"])
    assert r.attrs == {} and r.rejected == []


def test_only_missing_fields_are_requested() -> None:
    called = False

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return reply({})

    p = Product(sku="1", name="Обои 1,06х10,05 м")
    r = extract_with_llm(p, client(handler), needed=["roll_width_m", "roll_length_m"])
    assert not called  # regex already has both -> no LLM call
    assert r.attrs["roll_width_m"].source == "name"


def test_server_error_is_reported_not_raised_from_extract() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    r = extract_with_llm(product(), client(handler), needed=["roll_width_m"])
    assert r.attrs == {} and r.errors


def test_client_raises_llmerror_on_bad_json() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    with pytest.raises(LLMError):
        client(handler).chat_json("sys", "user", {"type": "object", "properties": {}})


def test_client_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] == 1 else reply({"ok": True})

    out = client(handler).chat_json("s", "u", {"type": "object", "properties": {}})
    assert out == {"ok": True} and calls["n"] == 2
