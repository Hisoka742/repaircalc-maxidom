"""Checklist A2/K2/K3: public routes live under /api/v1, /v1 stays as an alias, CORS, readiness."""
from decimal import Decimal as D

from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.catalog.schema import Product
from maxicalc.config import Settings
from maxicalc.recommend.select import CatalogEntry

ROOM = {"room": {"length_m": "4", "width_m": "3", "height_m": "2.5"}, "room_type": "living",
        "renovation_class": "cosmetic"}


def entries() -> list[CatalogEntry]:
    return [CatalogEntry(
        Product(sku="P1", product_id="9", name="Краска", price=D("1000")), work=set(),
        rooms={"any"}, props={"washable"}, calc="paint", status="verified",
        attrs={"spread_m2_per_l": D(10), "pack_volume_l": D("2.5")})]


def client(**cfg: object) -> TestClient:
    s = Settings(rate_limit_per_min=0, **cfg)  # type: ignore[arg-type]
    return TestClient(create_app(AppState(entries(), s), s))


def test_case_paths_are_in_openapi_and_legacy_paths_are_not() -> None:
    paths = client().get("/openapi.json").json()["paths"]
    for p in ("/api/v1/calc/property", "/api/v1/calc/room", "/api/v1/recommend",
              "/api/v1/product/{product_id}/calc", "/api/v1/parse",
              "/api/v1/catalog/products", "/api/v1/catalog/match",
              "/api/v1/estimate/{estimate_id}/explain"):
        assert p in paths, p
    assert not any(p.startswith("/v1/") for p in paths)


def test_every_public_route_answers_under_api_v1_and_legacy_v1_is_an_alias() -> None:
    c = client()
    a = c.post("/api/v1/calc/room", json=ROOM)
    b = c.post("/v1/calc/room", json=ROOM)
    assert a.status_code == b.status_code == 200
    assert a.json()["estimate_id"] == b.json()["estimate_id"]
    assert c.get("/api/v1/catalog/products").status_code == 200
    assert c.post("/api/v1/parse", json={"text": "кухня 9 м2"}).status_code == 200
    legacy = c.post("/v1/products/P1/quantity", json={"room": ROOM["room"],
                                                      "room_type": "living"})
    assert legacy.status_code == 200


def test_cors_allows_a_bitrix_origin_to_call_the_api() -> None:
    r = client(cors_origins="https://shop.example").options(
        "/api/v1/calc/room",
        headers={"Origin": "https://shop.example", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://shop.example"


def test_ready_is_503_without_a_catalog_and_200_with_one() -> None:
    s = Settings(rate_limit_per_min=0)
    empty = TestClient(create_app(AppState([], s), s))
    assert empty.get("/ready").status_code == 503
    r = client().get("/ready")
    assert r.status_code == 200 and r.json()["catalog_size"] == 1
    assert "llm" in r.json()


def test_a_non_local_llm_url_is_flagged() -> None:
    from maxicalc.config import llm_url_is_private

    assert llm_url_is_private("http://localhost:11434/v1")
    assert llm_url_is_private("http://ollama:11434/v1")           # compose service name
    assert llm_url_is_private("http://192.168.1.20:11434/v1")
    assert not llm_url_is_private("https://api.openai.com/v1")
