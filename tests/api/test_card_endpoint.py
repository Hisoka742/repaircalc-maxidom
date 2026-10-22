"""Product-card calculator (`/api/v1/product/{id}/calc`) and humidity/load overlays."""
from decimal import Decimal as D

from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.catalog.schema import Product
from maxicalc.config import Settings
from maxicalc.recommend.select import CatalogEntry


def entry(sku: str, pid: str, calc: str, price: str, attrs: dict[str, object],
          props: set[str] | None = None, **prod: object) -> CatalogEntry:
    return CatalogEntry(
        Product(sku=sku, product_id=pid, name=f"Товар {sku}", price=D(price),
                **prod),  # type: ignore[arg-type]
        work=set(), rooms={"any"}, props=props or set(), calc=calc, status="verified",
        attrs={k: (v if isinstance(v, int) else D(str(v))) for k, v in attrs.items()})


ENTRIES = [
    entry("P1", "5001", "paint", "1000", {"spread_m2_per_l": 10, "pack_volume_l": "2.5"},
          {"washable"}),
    entry("R1", "5002", "primer", "500", {"consumption_l_per_m2": "0.15", "pack_volume_l": 5}),
    entry("L1", "5003", "laminate", "1500", {"m2_per_pack": "2.131"}, {"wear_class_33"}),
    entry("D1", "5004", "drywall", "400", {}, {"moisture_resistant"}),
    entry("D2", "5005", "drywall", "300", {}),
    entry("D3", "5006", "drywall", "350", {}, {"moisture_resistant"}, in_stock=False),
]


def client() -> TestClient:
    cfg = Settings(rate_limit_per_min=0)
    return TestClient(create_app(AppState(list(ENTRIES), cfg), cfg))


def test_wall_calc_by_stand_id_matches_hand_computation() -> None:
    # 4.2 x 2.6 = 10.92 m2; paint 2 layers at 10 m2/l = 2.184 l -> 1 can of 2.5 l;
    # primer 0.15 l/m2 = 1.638 l -> 1 can of 5 l
    r = client().post("/api/v1/product/5001/calc", json={"wall": {"width_m": "4.2",
                                                                  "height_m": "2.6"}})
    assert r.status_code == 200, r.text
    j = r.json()
    lines = {ln["sku"]: ln for ln in j["basket"]["lines"]}
    assert lines["P1"]["qty_packs"] == 1 and lines["P1"]["product_id"] == "5001"
    assert lines["R1"]["qty_packs"] == 1
    assert D(j["basket"]["materials_total"]) == D("1500")
    assert any("10.92" in e for e in lines["P1"]["explain"])


def test_same_request_same_estimate_id() -> None:
    c = client()
    body = {"wall": {"width_m": "4", "height_m": "2.5"}}
    a = c.post("/api/v1/product/5001/calc", json=body).json()
    b = c.post("/api/v1/product/5001/calc", json=body).json()
    assert a["estimate_id"] == b["estimate_id"] and b["cached"] is True


def test_get_variant_for_plain_embedding() -> None:
    r = client().get("/api/v1/product/5001/calc",
                     params={"wall_width_m": "4", "wall_height_m": "2.5"})
    assert r.status_code == 200 and r.json()["basket"]["lines"][0]["sku"] == "P1"


def test_wrong_surface_for_the_product_is_a_clear_422() -> None:
    c = client()
    r = c.post("/api/v1/product/5001/calc",
               json={"floor": {"length_m": "4", "width_m": "3"}})
    assert r.status_code == 422 and "стен" in r.json()["error"]["message"].lower()
    r = c.post("/api/v1/product/5003/calc", json={"wall": {"width_m": "4", "height_m": "2.5"}})
    assert r.status_code == 422


def test_floor_product_by_floor_dimensions() -> None:
    r = client().post("/api/v1/product/5003/calc",
                      json={"floor": {"length_m": "4", "width_m": "3"}})
    assert r.status_code == 200
    line = next(ln for ln in r.json()["basket"]["lines"] if ln["sku"] == "L1")
    assert line["qty_packs"] == 6        # 12 m2 x 1.05 = 12.6 -> 6 packs of 2.131 m2


def test_unknown_product_and_missing_dimensions() -> None:
    c = client()
    assert c.post("/api/v1/product/nope/calc",
                  json={"wall": {"width_m": "1", "height_m": "1"}}).status_code == 404
    assert c.post("/api/v1/product/5001/calc", json={}).status_code == 422


def test_high_humidity_applies_wet_zone_rules_to_any_room() -> None:
    c = client()
    base = c.post("/v1/recommend", json={"room_type": "living", "calc": "drywall"}).json()
    wet = c.post("/v1/recommend", json={"room_type": "living", "calc": "drywall",
                                        "humidity": "high"}).json()
    assert {i["sku"] for i in base["items"]} == {"D1", "D2"}      # D3 is out of stock
    assert {i["sku"] for i in wet["items"]} == {"D1"}              # only moisture resistant
    assert any("влаж" in x["reason"].lower() for x in wet["excluded"])


def test_out_of_stock_is_excluded_with_a_reason() -> None:
    res = client().post("/v1/recommend", json={"room_type": "bathroom", "calc": "drywall"}).json()
    assert [i["sku"] for i in res["items"]] == ["D1"]
    assert {"sku": "D3", "reason": "нет в наличии"} in res["excluded"]


def test_catalog_browse_for_the_admin_page() -> None:
    c = client()
    page = c.get("/v1/catalog/products", params={"q": "d1"}).json()
    assert page["total"] == 1 and page["items"][0]["sku"] == "D1"
    assert page["items"][0]["product_id"] == "5004"
    assert "moisture_resistant" in page["items"][0]["properties"]
    by_id = c.get("/v1/catalog/products", params={"q": "5001"}).json()
    assert [i["sku"] for i in by_id["items"]] == ["P1"]
    only = c.get("/v1/catalog/products", params={"calc": "drywall", "limit": 2}).json()
    assert only["total"] == 3 and len(only["items"]) == 2
