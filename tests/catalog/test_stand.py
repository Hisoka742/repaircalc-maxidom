"""The stand API path: mock stand -> client -> JSONL -> adapter -> normalized products."""
import json
from decimal import Decimal

from fastapi.testclient import TestClient

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.adapters.maxidom_api import item_to_product
from maxicalc.catalog.schema import Product
from maxicalc.catalog.stand_client import StandClient
from maxicalc.stand_mock import build_stand_app


def _products(n: int = 25) -> list[Product]:
    out = []
    for i in range(n):
        out.append(Product(
            sku=f"A-{i}", name=f"Ламинат Tarkett LM{i} 32 класс", brand="Tarkett",
            price=Decimal(1500 + i), description="В упаковке 2,131 м2",
            category_path=["Напольные покрытия", "Ламинат"] if i % 2 else ["Краски", "Для стен"],
            characteristics={"Класс износостойкости": "32"}))
    return out


def test_item_uses_result_price_and_keeps_ids_as_strings() -> None:
    p = item_to_product({
        "id": 96611, "sku": "00123", "cod_good": "000777", "name": "Плитка", "price": 1800,
        "result_price": 1650, "quantity_in_package": 4, "package_area": 1.44,
        "categories_tree": [{"id": 33, "name": "Плитка", "depth": 2},
                            {"id": 2, "name": "Отделка", "depth": 1}],
        "stocks": [{"region_id": 1, "qty": 5}, {"region_id": 1, "qty": 2}],
        "ratings": {"rating": 4.7}, "recsys_rating": 1.05, "in_stock": True, "status": True,
        "characteristics": [{"code": "c", "name": "Цвет", "value": "Серый"}],
    })
    assert p is not None
    assert p.price == Decimal("1650") and p.list_price == Decimal("1800")
    assert p.product_id == "96611" and p.sku == "00123" and p.cod_good == "000777"
    assert p.category_path == ["Отделка", "Плитка"]            # ordered by depth
    assert p.package_area_m2 == Decimal("1.44")
    assert p.characteristics["Площадь упаковки"] == "1.44 м2"  # what the extractor understands
    assert p.stock_regions == {"1": Decimal(7)}
    assert p.rating == Decimal("4.7")


def test_client_reads_every_page_and_card(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = build_stand_app(_products(25))
    client = StandClient(client=TestClient(app, base_url="http://stand"), backoff_s=0)
    items = client.fetch_all(per_page=7)           # forces several pages per category
    assert len(items) == 25                        # not just the first page
    assert client.stats.pages >= 4 and client.stats.cards == 25
    assert all("description" in it and "characteristics" in it for it in items)
    out = tmp_path / "dump.jsonl"
    assert StandClient.dump(items, out) == 25
    products, report = load_catalog(out)
    assert len(products) == 25 and report.skipped == 0
    first = products[0]
    assert first.product_id and first.cod_good and first.price is not None
    assert first.characteristics["Площадь упаковки"] == "2.131 м2"
    assert first.brand == "Tarkett"


def test_duplicates_by_id_are_removed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "x.json"
    it = {"id": 1, "sku": "S", "name": "A", "result_price": 10, "cod_good": "1"}
    one = json.dumps(it)
    f.write_text(f'{{"items": [{one}, {one}]}}', encoding="utf-8")
    products, report = load_catalog(f)
    assert len(products) == 1 and report.issues_total == 1
