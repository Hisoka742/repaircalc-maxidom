"""Characteristic spellings found on real maxidom.ru cards (scraped 2026-10)."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract


def attrs(name: str, chars: dict[str, str]) -> dict[str, object]:
    res = extract(Product(sku="x", name=name, characteristics=chars))
    return {k: a.value for k, a in res.attrs.items()}


def test_consumption_in_litres_per_square_metre() -> None:
    a = attrs("грунт-антисептик Aura 3л", {"Объем": "3л", "Расход материала": "0,11л/кв.м"})
    assert a["consumption_l_per_m2"] == D("0.11") and a["pack_volume_l"] == D(3)


def test_consumption_in_grams_is_converted_to_kg() -> None:
    a = attrs("эмаль для радиаторов 0,9кг", {"Вес": "0.9кг", "Расход материала": "100г/кв.м"})
    assert a["consumption_kg_per_m2"] == D("0.1") and a["pack_mass_kg"] == D("0.9")


def test_tin_volume_key_is_read() -> None:
    a = attrs("эмаль ПФ-266 2кг", {"Вес": "2кг", "Литраж банки": "1.8л"})
    assert a["pack_volume_l"] == D("1.8") and a["pack_mass_kg"] == D(2)


def test_spread_in_m2_per_litre_characteristic() -> None:
    a = attrs("краска 2.5л", {"Расход": "10 кв.м/л", "Объем": "2.5л"})
    assert a["spread_m2_per_l"] == D(10)


def test_mosaic_with_three_dimensions_gives_tile_sides_and_thickness() -> None:
    a = attrs("мозаика мраморная STARO Wild Stone 30,5х30,5х0,4 коричневая",
              {"Размер": "30,5х30,5х0,4см"})
    assert a["tile_w_mm"] == D("305") and a["tile_h_mm"] == D("305")
    assert a["thickness_mm"] == D("4")
