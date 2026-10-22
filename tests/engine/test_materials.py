from decimal import Decimal as D

import pytest

from maxicalc.engine.geometry import Opening, Room
from maxicalc.engine.materials import coatings, flooring, skirting, tile, wallpaper


def test_wallpaper_strips_per_wall_not_area() -> None:
    r = Room.rectangle(4, 3, "2.5", [Opening("door", D("0.9"), D("2.05"), 0)])
    c = wallpaper.rolls(r, roll_width_m=D("1.06"), roll_length_m=D("10.05"))
    # strip 2.6 m -> 3 strips/roll; strips 3+3+4+3 = 13 -> 5 rolls
    assert c.value == 5
    assert c.unit == "рулон"
    assert any("13" in line for line in c.explain)


def test_wallpaper_rapport_and_reserve() -> None:
    r = Room.rectangle(4, 3, "2.5")
    # strip = ceil(2.6/0.64)*0.64 = 3.2 m -> 3 strips/roll
    # strips: ceil(4/0.53)=8, ceil(3/0.53)=6 -> (8+6)*2 = 28 -> ceil(28/3) = 10
    a = wallpaper.rolls(r, roll_width_m=D("0.53"), roll_length_m=D("10.05"), rapport_m=D("0.64"))
    assert a.value == 10
    b = wallpaper.rolls(r, roll_width_m=D("0.53"), roll_length_m=D("10.05"),
                        rapport_m=D("0.64"), reserve_rolls=1)
    assert b.value == 11


def test_wallpaper_strip_longer_than_roll() -> None:
    r = Room.rectangle(4, 3, "2.5")
    with pytest.raises(ValueError):
        wallpaper.rolls(r, roll_width_m=D("1.06"), roll_length_m=D("2"))


def test_paint_liters() -> None:
    c = coatings.liters_by_spread(D("30"), spread_m2_per_l=D("10"), layers=2)
    assert c.value == D("6")
    p = coatings.liters_by_spread(D("30"), spread_m2_per_l=D("10"), layers=2, porous=True)
    assert p.value == D("6.6")


def test_primer_and_putty() -> None:
    assert coatings.liters_by_consumption(D("30"), D("0.15"), layers=1).value == D("4.5")
    putty = coatings.kg_by_thickness(D("30"), thickness_mm=D("2"), kg_per_m2_per_mm=D("1.1"))
    assert putty.value == D("66")
    assert coatings.packs(putty.value, D("25")).value == 3


def test_tile_waste_and_packs() -> None:
    a = tile.area_with_waste(D("12"), layout="straight", tile_w_mm=300, tile_h_mm=300)
    assert a.value == D("12.84")
    assert tile.packs(a.value, m2_per_pack=D("1.44")).value == 9
    small = tile.area_with_waste(D("3"), layout="straight", tile_w_mm=300, tile_h_mm=300)
    assert small.value == D("3.3")  # +7% +3% small room
    big = tile.area_with_waste(D("12"), layout="diagonal", tile_w_mm=600, tile_h_mm=600)
    assert big.value == D("12") * D("1.15")


def test_tile_pieces() -> None:
    # 12.84 m2 / 0.09 m2 = 142.67 -> 143 pcs ; 10 pcs/pack -> 15 packs
    assert tile.packs(D("12.84"), pcs_per_pack=10, tile_w_mm=300, tile_h_mm=300).value == 15


def test_grout_formula() -> None:
    g = tile.grout_kg_per_m2(300, 300, tile_thickness_mm=D("8"), joint_mm=D("3"),
                             density_kg_per_dm3=D("1.6"))
    assert g.value == D("0.256")
    assert tile.grout_kg(D("12"), 300, 300, D("8"), D("3"), D("1.6")).value == D("3.072")


def test_adhesive_fallback_and_card() -> None:
    # Ceresit CM 11 (01.2020) table: 300 mm side -> 10 mm notch -> ~4.2 kg/m2
    assert tile.adhesive_kg(D("12"), 300, 300).value == D("50.4")
    assert tile.adhesive_kg(D("12"), 300, 300, kg_per_m2=D("5")).value == D("60")


@pytest.mark.parametrize(("side_mm", "rate"), [
    (50, "1.7"), (100, "2.0"), (150, "2.7"), (250, "3.6"), (300, "4.2"), (500, "5.5")])
def test_adhesive_fallback_follows_ceresit_table(side_mm: int, rate: str) -> None:
    assert tile.adhesive_kg(D("1"), side_mm, side_mm // 2).value == D(rate)


def test_laminate_and_skirting() -> None:
    a = flooring.area_with_waste(D("12"), layout="straight")
    assert a.value == D("12.84")
    assert flooring.packs(a.value, m2_per_pack=D("2.131")).value == 7
    r = Room.rectangle(4, 3, "2.5", [Opening("door", D("0.9"), D("2.05"), 0)])
    s = skirting.pieces(r, piece_len_m=D("2.5"))
    assert s.value == 6  # 13.1*1.05/2.5 = 5.50 -> 6
