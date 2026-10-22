"""Streaming YML adapter on a trimmed copy of the Maxidom feed."""
import gzip
from pathlib import Path

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.adapters.yml_feed import feed_date
from maxicalc.catalog.feed import feed_report, is_repair

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "maxidom_feed_sample.xml"


def test_offers_become_products_with_params_and_category_path() -> None:
    products, rep = load_catalog(FIX)
    assert rep.loaded == 3 and rep.skipped == 0
    p = products[0]
    assert p.sku == "100" and p.brand == "PARADE" and str(p.price) == "1499.00"
    assert p.category_path == ["Краска и малярный инструмент", "Краски и эмали",
                               "Краски для стен и потолков"]
    assert p.description == "Объем: 5 л | Расход: 10 м2/л"          # <br> kept as a separator
    assert p.characteristics["Объем, л"] == "5"
    assert p.characteristics["Назначение"] == "для потолков; для стен"   # repeated param joined
    assert p.characteristics["Вес, кг"] == "6.1" and p.in_stock is True
    assert products[1].in_stock is False and products[2].in_stock is None


def test_gzip_snapshot_and_feed_date(tmp_path: Path) -> None:
    gz = tmp_path / "latest.xml.gz"
    gz.write_bytes(gzip.compress(FIX.read_bytes()))
    products, _ = load_catalog(gz)
    assert len(products) == 3 and feed_date(gz) == "2026-10-19"


def test_truncated_feed_is_read_up_to_the_last_complete_offer(tmp_path: Path) -> None:
    cut = tmp_path / "cut.xml"
    text = FIX.read_text(encoding="utf-8")
    head = text[: text.index('<offer id="102"')]
    cut.write_text(head + '<offer id="103"><url>', encoding="utf-8")
    products, _ = load_catalog(cut)
    assert [p.sku for p in products] == ["100", "101"]


def test_scope_and_report() -> None:
    assert is_repair(["Краска и малярный инструмент", "Краски и эмали"])
    assert not is_repair(["Посуда", "Кувшины"])
    assert is_repair(["Интерьер", "Обои, пленка самоклеящаяся", "Обои"])
    assert not is_repair(["Интерьер", "Карнизы и комплектующие"])
    products, _ = load_catalog(FIX)
    rep = feed_report(products, 0.1, "2026-10-19")
    assert rep.offers == 3 and rep.repair == 1
    cov = rep.by_category["Краска и малярный инструмент > Краски и эмали"]
    assert cov.param_share == 1.0 and cov.mean_params == 2.0 + 0   # Объем, Назначение
