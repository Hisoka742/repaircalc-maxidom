import json
import time
from decimal import Decimal as D
from pathlib import Path

import openpyxl
import pytest

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.normalize import normalize_text, split_category_path

CSV = """Артикул;Наименование;Категория;Бренд;Цена;Описание;URL
100;  Обои  флизелиновые 1,06х10,05 м ;Обои > Флизелиновые;Erismann;1 299,90;Красивые;https://x/1
101;Грунт CT 17;Строительные смеси / Грунтовки;Ceresit;450;;
;Без артикула;Обои;;10;;
102;Плитка;Плитка;;abc;;
"""


def test_csv_with_russian_headers(tmp_path: Path) -> None:
    f = tmp_path / "c.csv"
    f.write_text(CSV, encoding="utf-8")
    items, rep = load_catalog(f)
    assert [p.sku for p in items] == ["100", "101", "102"]
    p = items[0]
    assert p.name == "Обои флизелиновые 1,06х10,05 м"
    assert p.category_path == ["Обои", "Флизелиновые"]
    assert p.price == D("1299.90")
    assert items[1].category_path == ["Строительные смеси", "Грунтовки"]
    assert items[2].price is None
    assert rep.read == 4 and rep.loaded == 3 and rep.skipped == 1
    assert any("артикул" in i.lower() or "sku" in i.lower() for i in rep.issues)
    assert any("цена" in i.lower() or "price" in i.lower() for i in rep.issues)


def test_csv_cp1251_and_comma_delimiter(tmp_path: Path) -> None:
    f = tmp_path / "c.csv"
    f.write_bytes("sku,name,price\n7,Краска белая,500\n".encode("cp1251"))
    items, _ = load_catalog(f)
    assert items[0].name == "Краска белая" and items[0].price == D("500")


def test_xlsx(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["sku", "name", "category", "price", "Ширина рулона, м"])
    ws.append([5, "Обои", "Обои", 999.5, "1,06"])
    f = tmp_path / "c.xlsx"
    wb.save(f)
    items, _ = load_catalog(f)
    assert items[0].sku == "5" and items[0].price == D("999.5")
    assert items[0].characteristics["Ширина рулона, м"] == "1,06"


def test_json_list_and_wrapped(tmp_path: Path) -> None:
    rows = [{"sku": "1", "name": "A", "price": 10, "characteristics": {"Вес, кг": "25"}}]
    for payload in (rows, {"products": rows}):
        f = tmp_path / "c.json"
        f.write_text(json.dumps(payload), encoding="utf-8")
        items, _ = load_catalog(f)
        assert items[0].characteristics == {"Вес, кг": "25"}


YML = """<?xml version="1.0" encoding="UTF-8"?>
<yml_catalog><shop>
<categories><category id="1">Обои</category>
<category id="2" parentId="1">Флизелиновые</category></categories>
<offers>
<offer id="55"><name>Обои 1,06х10,05</name><price>1200</price><categoryId>2</categoryId>
<vendor>Erismann</vendor><url>https://x/55</url><picture>https://x/55.jpg</picture>
<description>Описание</description>
<param name="Ширина рулона" unit="м">1,06</param></offer>
</offers></shop></yml_catalog>"""


def test_yml_feed(tmp_path: Path) -> None:
    f = tmp_path / "feed.xml"
    f.write_text(YML, encoding="utf-8")
    items, _ = load_catalog(f)
    p = items[0]
    assert p.sku == "55" and p.brand == "Erismann" and p.price == D("1200")
    assert p.category_path == ["Обои", "Флизелиновые"]
    assert p.characteristics["Ширина рулона, м"] == "1,06"
    assert p.image_url == "https://x/55.jpg"


def test_unknown_format(tmp_path: Path) -> None:
    f = tmp_path / "c.bin"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        load_catalog(f)


def test_ingest_10k_rows_is_fast(tmp_path: Path) -> None:
    lines = ["sku;name;category;price"] + [
        f"{i};Товар {i} 1,06х10,05 м;Обои > Виниловые;{i % 900 + 100},50" for i in range(10_000)]
    f = tmp_path / "big.csv"
    f.write_text("\n".join(lines), encoding="utf-8")
    t = time.perf_counter()
    items, rep = load_catalog(f)
    assert len(items) == 10_000 and rep.skipped == 0
    assert time.perf_counter() - t < 5


def test_normalize_helpers() -> None:
    assert normalize_text("  a  b\t c\n") == "a b c"
    assert split_category_path("A > B / C") == ["A", "B", "C"]
    assert split_category_path("") == []
    assert split_category_path("Тепло/звукоизоляция > Вата") == ["Тепло/звукоизоляция", "Вата"]


def test_common_1c_erp_header_synonyms_are_recognised() -> None:
    from maxicalc.catalog.adapters.base import map_headers

    mapped, unmapped = map_headers([
        "Номенклатура", "Группа товаров", "Торговая марка", "Розничная цена, руб.", "Ед. изм.",
        "Артикул поставщика", "Ставка НДС", "Описание товара"])
    assert mapped == {
        "Номенклатура": "name", "Группа товаров": "category", "Торговая марка": "brand",
        "Розничная цена, руб.": "price", "Ед. изм.": "unit", "Артикул поставщика": "sku",
        "Описание товара": "description"}
    assert unmapped == ["Ставка НДС"]
    for h, field in [("Наименование товара", "name"), ("Название товара", "name"),
                     ("Раздел каталога", "category"), ("Категория товара", "category"),
                     ("Код номенклатуры", "sku"), ("Артикул товара", "sku"),
                     ("Цена", "price"), ("Цена, руб", "price"), ("Цена с НДС", "price"),
                     ("Производитель", "brand"), ("URL", "url"), ("Ссылка на товар", "url")]:
        assert map_headers([h])[0] == {h: field}, h


def test_header_units_and_parentheses_do_not_hide_a_known_column() -> None:
    from maxicalc.catalog.adapters.base import map_headers

    for h, field in [("Розничная цена, руб.", "price"), ("Цена (руб.)", "price"),
                     ("Наименование, полное", "name"), ("Артикул (1С)", "sku"),
                     ("Вес, кг", None)]:
        mapped, _ = map_headers([h])
        assert mapped.get(h) == field, h
