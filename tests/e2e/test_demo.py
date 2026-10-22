"""The hackathon demo scenario, end to end, against the mock stand, with the network blocked.

stand (mock, case schema) -> client -> ingest job -> catalog -> API:
  1. «Квартира -> капитальный ремонт» + «санузел 6 м², высокая влажность»
  2. estimate with moisture-resistant drywall, tile with waste, washable paint, total + explanation
  3. product card: wall dimensions -> instant quantity and price
  4. a new product -> ML suggests a category and rooms
"""
import math
import socket
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.catalog.ingest_job import run_ingest
from maxicalc.catalog.stand_client import StandClient
from maxicalc.config import Settings
from maxicalc.ml.synth import generate
from maxicalc.stand_mock import build_stand_app

NAME = "/api/v1"
# what a real card carries: the numbers the calculators need
CARD_TEXT = {
    "paint": "Расход 10 м2/л в один слой", "primer": "Расход 0,15 л/м2",
    "putty": "Расход 1,1 кг/м2 на 1 мм слоя", "waterproofing": "Расход 3,5 кг/м2",
    "laminate": "В упаковке 2,131 м2", "tile": "В упаковке 1,44 м2",
    "underlay": "В упаковке 10 м2", "tile_adhesive": "Фасовка 25 кг", "grout": "Фасовка 2 кг",
}


@pytest.fixture(autouse=True)
def no_internet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []
    real = socket.socket.connect

    def guard(self: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) else str(address)
        if str(host) not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            attempts.append(str(host))
            raise OSError(f"network blocked in the e2e test: {host}")
        return real(self, address)  # type: ignore[arg-type]

    monkeypatch.setattr(socket.socket, "connect", guard)
    return attempts


@pytest.fixture(scope="module")
def api(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    tmp = tmp_path_factory.mktemp("e2e")
    products = []
    for n, it in enumerate(generate(3000, seed=11)):
        text = CARD_TEXT.get(it.gold.calc)       # consumption / pack data lives in the card
        products.append(it.product.model_copy(update={
            "price": it.product.price or D(300 + (n * 37) % 900),
            "description": f"{it.product.description} {text}".strip() if text else
            it.product.description}))
    stand = TestClient(build_stand_app(products), base_url="http://stand")
    client = StandClient(client=stand, cache_dir=tmp / "cache", backoff_s=0)  # type: ignore[arg-type]
    res = run_ingest(client, tmp / "out", per_page=200)
    assert res.loaded == len(products)
    cfg = Settings(catalog_path=str(tmp / "out" / "stand.jsonl"), rate_limit_per_min=0,
                   llm_enabled=False)
    return TestClient(create_app(AppState.from_settings(cfg), cfg))


def catalog_item(api: TestClient, sku: str) -> dict:  # type: ignore[type-arg]
    page = api.get(f"{NAME}/catalog/products", params={"sku": sku}).json()
    assert page["total"] == 1, sku
    return dict(page["items"][0])


def test_step_1_and_2_bathroom_estimate_with_wet_zone_materials(api: TestClient) -> None:
    text = "Квартира, капитальный ремонт, санузел 6 м², высокая влажность"
    parsed = api.post(f"{NAME}/parse", json={"text": text})
    p = parsed.json()
    assert p["ready"] and p["renovation_class"] == "major" and p["property_type"] == "apartment"
    room = p["rooms"][0]
    assert room["room_type"] == "bathroom" and D(room["area_m2"]) == 6
    assert room["humidity"] == "high"

    est = api.post(f"{NAME}/calc/property", json={
        "property_type": p["property_type"], "total_area_m2": "60",
        "renovation_class": p["renovation_class"],
        "rooms": [{"room_type": room["room_type"], "area_m2": room["area_m2"],
                   "humidity": room["humidity"]}]})
    assert est.status_code == 200, est.text
    j = est.json()
    lines = j["basket"]["lines"]
    groups = {ln["group"] for ln in lines}
    assert {"walls", "floor"} <= groups                       # grouped by work package
    for ln in lines:
        assert ln["explain"], ln["sku"]                      # every number has a trace
        item = catalog_item(api, ln["sku"])
        if item["calc"] == "drywall":
            assert "moisture_resistant" in item["properties"]        # no plain drywall
        if item["calc"] in ("paint", "wallpaper"):
            assert {"moisture_resistant", "washable"} & set(item["properties"])
    calcs = {catalog_item(api, ln["sku"])["calc"] for ln in lines}
    assert {"drywall", "tile"} <= calcs
    tile_line = next(ln for ln in lines if catalog_item(api, ln["sku"])["calc"] == "tile")
    assert any("запас" in e.lower() for e in tile_line["explain"])  # waste by layout is shown
    total = sum(D(ln["line_total"]) for ln in lines)
    assert total == D(j["basket"]["materials_total"]) > 0

    why = api.post(f"{NAME}/estimate/{j['estimate_id']}/explain").json()
    assert why["method"] == "template" and "Итого" in why["text"]    # works without the LLM
    assert why["facts"]


def test_step_3_product_card_gives_instant_quantity_and_price(api: TestClient) -> None:
    page = api.get(f"{NAME}/catalog/products", params={"calc": "paint", "status": "auto",
                                                      "limit": 5}).json()
    paint = next(i for i in page["items"] if "spread_m2_per_l" in i["attributes"]
                 and "pack_volume_l" in i["attributes"])
    r = api.post(f"{NAME}/product/{paint['product_id']}/calc",
                 json={"wall": {"width_m": "4.2", "height_m": "2.6"}})
    assert r.status_code == 200, r.text
    j = r.json()
    main = next(ln for ln in j["basket"]["lines"] if ln["sku"] == paint["sku"])
    # 10.92 m2 x 2 layers / spread, in packs of pack_volume
    spread = D(paint["attributes"]["spread_m2_per_l"])
    pack = D(paint["attributes"]["pack_volume_l"])
    need_l = D("10.92") * 2 / spread
    assert main["qty_packs"] == math.ceil(need_l / pack)
    assert D(main["line_total"]) == D(main["unit_price"]) * main["qty_packs"]
    assert j["labor"] is None             # a product card shows materials only


def test_step_4_a_new_product_gets_a_category_and_rooms(api: TestClient) -> None:
    r = api.post(f"{NAME}/catalog/match", json={"products": [{
        "sku": "NEW-1", "name": "Плитка керамическая настенная Kerama Marazzi 20x30 см белая",
        "category_path": ["Плитка", "Настенная"], "description": "В упаковке 1,44 м2"}]})
    assert r.status_code == 200
    item = r.json()["results"][0]
    assert item["calc_template"]["label"] == "tile"
    assert item["calc_template"]["confidence"] > 0.5
    assert item["room_types"], "rooms are suggested"
    assert item["status"] in ("auto", "review")
