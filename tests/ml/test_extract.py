from decimal import Decimal as D

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract


def prod(name: str, chars: dict[str, str] | None = None, desc: str = "",
         category: tuple[str, ...] = ()) -> Product:
    return Product(sku="1", name=name, category_path=list(category),
                   characteristics=chars or {}, description=desc)


def vals(p: Product) -> dict[str, object]:
    return {k: a.value for k, a in extract(p).attrs.items()}


def test_wallpaper_roll_from_name() -> None:
    v = vals(prod("Обои флизелиновые Erismann 1,06х10,05 м"))
    assert v["roll_width_m"] == D("1.06")
    assert v["roll_length_m"] == D("10.05")


def test_wallpaper_roll_order_swapped() -> None:
    v = vals(prod("Обои виниловые 10,05 x 1,06 м"))
    assert v["roll_width_m"] == D("1.06")
    assert v["roll_length_m"] == D("10.05")


def test_tile_cm_and_mm() -> None:
    assert vals(prod("Керамогранит 60x60 см"))["tile_w_mm"] == D("600")
    v = vals(prod("Плитка настенная 300х600 мм"))
    assert (v["tile_w_mm"], v["tile_h_mm"]) == (D("300"), D("600"))


def test_tile_unit_missing_is_guessed_as_cm_and_flagged() -> None:
    r = extract(prod("Плитка Kerama 30x60"))
    assert r.attrs["tile_w_mm"].value == D("300")
    assert r.attrs["tile_w_mm"].confidence == "low"


def test_laminate_three_dims() -> None:
    v = vals(prod("Ламинат 33 класс 1380x193x8 мм"))
    assert (v["length_mm"], v["width_mm"], v["thickness_mm"]) == (D("1380"), D("193"), D("8"))
    assert v["wear_class"] == 33


def test_m2_per_pack_variants() -> None:
    assert vals(prod("Ламинат", {"Площадь в упаковке, м2": "2,131"}))["m2_per_pack"] == D("2.131")
    assert vals(prod("Ламинат 2,13 м²/уп"))["m2_per_pack"] == D("2.13")
    assert vals(prod("Плитка", desc="В упаковке 1,44 м2"))["m2_per_pack"] == D("1.44")


def test_mass_and_volume_not_confused_with_consumption() -> None:
    v = vals(prod("Клей плиточный 25 кг", desc="Расход 4,2 кг/м²"))
    assert v["pack_mass_kg"] == D("25")
    assert v["consumption_kg_per_m2"] == D("4.2")
    p = vals(prod("Краска водоэмульсионная 2,5 л", desc="Расход 10 м²/л"))
    assert p["pack_volume_l"] == D("2.5")
    assert p["spread_m2_per_l"] == D("10")


def test_consumption_per_mm() -> None:
    v = vals(prod("Смесь", desc="Расход 1,8 кг/м² на 1 мм слоя"))
    assert v["consumption_kg_per_m2_per_mm"] == D("1.8")


def test_ip_and_emission() -> None:
    v = vals(prod("Розетка IP 44", desc="Класс эмиссии E1"))
    assert v["ip_rating"] == 44
    assert v["emission_class"] == "E1"


def test_rapport() -> None:
    assert vals(prod("Обои", {"Раппорт, см": "64"}))["rapport_cm"] == D("64")
    assert vals(prod("Обои раппорт 0,32 м"))["rapport_cm"] == D("32")


def test_pcs_per_pack() -> None:
    assert vals(prod("Плитка", desc="10 шт. в упаковке"))["pcs_per_pack"] == 10
    assert vals(prod("Плитка", {"Количество в упаковке": "8 шт"}))["pcs_per_pack"] == 8


def test_characteristics_take_priority_over_name() -> None:
    v = vals(prod("Обои 0,53х10,05 м", {"Ширина рулона, м": "1,06"}))
    assert v["roll_width_m"] == D("1.06")


def test_out_of_range_values_are_rejected_not_returned() -> None:
    r = extract(prod("Обои 3,5х120 м"))
    assert "roll_width_m" not in r.attrs
    assert any(x.name == "roll_width_m" for x in r.rejected)
    r2 = extract(prod("Ламинат 99 класс"))
    assert "wear_class" not in r2.attrs and r2.rejected


def test_nothing_found_is_empty_not_error() -> None:
    r = extract(prod("Молоток"))
    assert r.attrs == {} and r.rejected == []


@pytest.mark.parametrize("raw", ["1 200,50", "1 200,50", "1200.50"])
def test_number_formats(raw: str) -> None:
    from maxicalc.ml.extract import parse_number
    assert parse_number(raw) == D("1200.50")


def test_dimensions_are_gated_by_product_type() -> None:
    # a ceiling profile or a plastic film must not become a tile / wallpaper roll
    assert vals(prod("Профиль потолочный CD 60x27 мм 3 м")) == {}
    assert vals(prod("Пленка полиэтиленовая строительная 1x10 м")) == {}
    assert vals(prod("Дюбель-гвоздь 6x40 мм, 100 шт. в упаковке")) == {"pcs_per_pack": 100}


def test_unit_after_each_number() -> None:
    v = vals(prod("Обои флизелиновые 1,06 м x 10,05 м"))
    assert (v["roll_width_m"], v["roll_length_m"]) == (D("1.06"), D("10.05"))


def test_consumption_at_layer_thickness_is_normalised_per_mm() -> None:
    v = vals(prod("Штукатурка гипсовая 30 кг", desc="Расход 8,5 кг/м2 при толщине слоя 10 мм"))
    assert v["consumption_kg_per_m2_per_mm"] == D("0.85")
    assert "consumption_kg_per_m2" not in v


def test_size_characteristic_is_read() -> None:
    v = vals(prod("Керамогранит Italon", {"Размер": "60x60 см"}))
    assert (v["tile_w_mm"], v["tile_h_mm"]) == (D("600"), D("600"))


def test_m2_per_pack_after_piece_count() -> None:
    v = vals(prod("Керамогранит", desc="В упаковке 4 шт., 1,44 м2"))
    assert v["m2_per_pack"] == D("1.44") and v["pcs_per_pack"] == 4


def test_plank_two_dimensions_are_length_and_width() -> None:
    v = vals(prod("Ламинат Egger", {"Размер": "1291x193"}))
    assert (v["length_mm"], v["width_mm"]) == (D("1291"), D("193"))
    assert "tile_w_mm" not in v
