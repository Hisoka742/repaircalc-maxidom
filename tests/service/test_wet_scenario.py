"""The hackathon demo scenario: apartment, major renovation, bathroom 6 m2, high humidity."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.property_calc import PropertyInput, RoomInput, calc_property


def ent(sku: str, calc: str, attrs: dict[str, object], props: set[str], name: str) -> CatalogEntry:
    return CatalogEntry(
        Product(sku=sku, name=name, price=D("400")), work=set(), rooms={"any"}, props=props,
        calc=calc, status="verified",
        attrs={k: (v if isinstance(v, int) else D(str(v))) for k, v in attrs.items()})


def test_card_text_gives_drywall_sheet_thickness_not_profile() -> None:
    sheet = extract(Product(sku="1", name="Gyproc GK10 12,5 мм лист ГКЛВ влагостойкий"))
    assert sheet.attrs["thickness_mm"].value == D("12.5")
    profile = extract(Product(sku="2", name="Профиль для гипсокартона Knauf 27x28 мм 3 м"))
    assert "thickness_mm" not in profile.attrs


def test_wet_bathroom_gets_moisture_resistant_sheets_by_hand_computed_count() -> None:
    catalog = [
        ent("G1", "drywall", {"thickness_mm": "12.5"}, {"moisture_resistant"}, "ГКЛВ лист"),
        ent("G2", "drywall", {"thickness_mm": "12.5"}, set(), "ГКЛ лист обычный"),
    ]
    est = calc_property(
        PropertyInput("apartment", D(60), "major", [RoomInput("bathroom", D(6), None, "high")]),
        catalog)
    line = next(ln for ln in est.basket.lines if ln.sku == "G1")
    # 6 m2 at aspect 1.5 -> 3 x 2 m, h 2.7: walls 2 x (3 + 2) x 2.7 = 27 m2
    # sheets: ceil(27 x 1.1 / (2.5 x 1.2)) = ceil(9.9) = 10
    assert line.qty_packs == 10 and line.unit == "лист"
    assert all(ln.sku != "G2" for ln in est.basket.lines)
    assert any("стандартным 2500×1200" in a for a in est.assumptions)


def test_dry_room_gets_no_drywall_lining() -> None:
    catalog = [ent("G1", "drywall", {"thickness_mm": "12.5"}, {"moisture_resistant"}, "ГКЛВ")]
    est = calc_property(
        PropertyInput("apartment", D(60), "major", [RoomInput("living", D(18))]), catalog)
    assert all(ln.sku != "G1" for ln in est.basket.lines)
