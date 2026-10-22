"""Checklist J1/F2: manual bindings always win over ML, survive a re-match, work for any product."""
from pathlib import Path

from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.config import Settings

CSV = (
    "sku;name;category;brand;price;description\n"
    "A1;Краска для стен Tikkurila 2,5 л моющаяся;Краски > Для стен;Tikkurila;900;Расход 10 м2/л\n"
    "B1;Грунтовка глубокого проникновения 5 л;Грунтовки;Ceresit;500;Расход 0,15 л/м2\n"
    "C1;Что-то непонятное;;;300;\n"
)


def make(tmp_path: Path) -> tuple[TestClient, Settings]:
    cat = tmp_path / "cat.csv"
    if not cat.exists():
        cat.write_text(CSV, encoding="utf-8")
    cfg = Settings(catalog_path=str(cat), overrides_path=str(tmp_path / "ov.jsonl"),
                   rate_limit_per_min=0, llm_enabled=False)
    return TestClient(create_app(AppState.from_settings(cfg), cfg)), cfg


BODY = {"work_categories": ["wall_prep"], "room_types": ["any"], "properties": ["washable"],
        "calc_template": "primer", "reviewer": "ivan"}


def product(c: TestClient, sku: str) -> dict:  # type: ignore[type-arg]
    r = c.get("/api/v1/catalog/products", params={"q": sku})
    return next(i for i in r.json()["items"] if i["sku"] == sku)


def test_an_auto_labelled_product_can_be_overridden_not_only_queued_ones(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    assert product(c, "A1")["calc"] == "paint"
    r = c.post("/api/v1/catalog/review/A1", json=BODY)
    assert r.status_code == 200, r.text
    p = product(c, "A1")
    assert p["calc"] == "primer" and p["status"] == "verified"
    assert p["properties"] == ["washable"]


def test_unknown_product_is_404(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    assert c.post("/api/v1/catalog/review/NOPE", json=BODY).status_code == 404


def test_the_override_survives_a_rematch_and_a_restart(tmp_path: Path) -> None:
    c, cfg = make(tmp_path)
    c.post("/api/v1/catalog/review/A1", json=BODY)
    assert c.post("/api/v1/catalog/rematch").status_code == 200       # ML runs again...
    assert product(c, "A1")["calc"] == "primer"                       # ...the human label wins
    c2 = TestClient(create_app(AppState.from_settings(cfg), cfg))     # a fresh process
    p = product(c2, "A1")
    assert p["calc"] == "primer" and p["status"] == "verified"


def test_rematch_without_overrides_keeps_ml_labels(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    before = product(c, "B1")
    assert c.post("/api/v1/catalog/rematch").status_code == 200
    assert product(c, "B1") == before


def test_a_product_without_a_calc_template_gets_a_clear_422(tmp_path: Path) -> None:
    c, _ = make(tmp_path)
    cat = product(c, "C1")
    assert cat["calc"] == "none"
    r = c.post("/api/v1/product/C1/calc", json={"wall": {"width_m": "4", "height_m": "2.5"}})
    assert r.status_code == 422
    assert "калькулятор" in r.json()["error"]["message"].lower()
