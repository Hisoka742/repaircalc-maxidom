"""Wallpaper glue (checklist C2): by pack coverage, or by consumption per m2 and pack mass."""
from decimal import Decimal as D

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Room
from maxicalc.engine.materials import wallpaper
from maxicalc.ml.extract import extract
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.property_calc import calc_product


def test_glue_by_coverage_rounds_up_once() -> None:
    assert wallpaper.glue_packs(D("27.3"), coverage_m2_per_pack=40).value == 1
    assert wallpaper.glue_packs(D(85), coverage_m2_per_pack=40).value == 3   # ceil(2.125)
    assert wallpaper.glue_packs(D(80), coverage_m2_per_pack=40).value == 2   # exact fit


def test_glue_by_consumption_and_pack_mass() -> None:
    # 30 m2 x 0.2 kg/m2 = 6 kg; a 0.25 kg pack -> 24 packs
    r = wallpaper.glue_packs(D(30), consumption_kg_per_m2=D("0.2"), pack_mass_kg=D("0.25"))
    assert r.value == 24 and "6" in " ".join(r.explain)


def test_glue_needs_one_of_the_two_data_sets() -> None:
    with pytest.raises(ValueError):
        wallpaper.glue_packs(D(30))
    with pytest.raises(ValueError):
        wallpaper.glue_packs(D(30), consumption_kg_per_m2=D("0.2"))   # pack mass missing


def test_card_text_gives_glue_coverage() -> None:
    p = Product(sku="g", name="Клей для обоев Metylan флизелин 250 г",
                description="Хватает на 40 м2 обоев")
    assert extract(p).attrs["coverage_m2_per_pack"].value == D(40)
    # a tile adhesive that says "на 40 м2" must not get wallpaper-glue coverage
    t = Product(sku="t", name="Клей для плитки Ceresit CM11 25 кг", description="на 40 м2")
    assert "coverage_m2_per_pack" not in extract(t).attrs


def entry(sku: str, calc: str, attrs: dict[str, object]) -> CatalogEntry:
    return CatalogEntry(Product(sku=sku, name=sku, price=D(100)), work=set(), rooms={"any"},
                        props=set(), calc=calc, status="verified",
                        attrs={k: D(str(v)) for k, v in attrs.items()})


def test_wallpaper_product_card_adds_the_glue_companion() -> None:
    catalog = [
        entry("W1", "wallpaper", {"roll_width_m": "1.06", "roll_length_m": "10.05"}),
        entry("G1", "wallpaper_glue", {"coverage_m2_per_pack": 40}),
    ]
    room = Room.rectangle(4, 3, "2.5")
    est = calc_product(room, "living", catalog[0], catalog, include_ceiling=False)
    glue = next(ln for ln in est.basket.lines if ln.sku == "G1")
    # net walls = 2 x (4 + 3) x 2.5 = 35 m2 -> ceil(35 / 40) = 1 pack
    assert glue.qty_packs == 1
    assert any("35" in e for e in glue.explain)
