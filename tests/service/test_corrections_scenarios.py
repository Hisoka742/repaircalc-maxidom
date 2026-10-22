"""Seven demo scenarios: the same room, one condition changed, hand-computed quantities, and an
explain line with the coefficient, reason and source (docs/COEFFICIENTS.md)."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Room
from maxicalc.engine.materials import flooring, wallpaper
from maxicalc.knowledge.loader import load_corrections
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.property_calc import calc_room
from maxicalc.service.room_calc import Conditions

ROOM = Room.rectangle(4, 3, "2.5")          # floor 12, walls 35, ceiling 12


def ent(sku: str, name: str, calc: str, attrs: dict[str, str], brand: str | None = None,
        ) -> CatalogEntry:
    return CatalogEntry(Product(sku=sku, name=name, brand=brand, price=D(100)), work=set(),
                        rooms={"any"}, props=set(), calc=calc, status="verified",
                        attrs={k: D(v) for k, v in attrs.items()})


PAINT = ent("PA", "краска акриловая для стен", "paint",
            {"spread_m2_per_l": "10", "pack_volume_l": "2.5"})
PRIMER = ent("PR", "грунтовка", "primer", {"consumption_l_per_m2": "0.1", "pack_volume_l": "10"})
PUTTY = ent("PU", "шпатлевка финишная гипсовая", "putty",
            {"consumption_kg_per_m2_per_mm": "1.0", "pack_mass_kg": "20"})
PLASTER = ent("PL", "штукатурка гипсовая Ротбанд", "putty",
              {"consumption_kg_per_m2_per_mm": "0.85", "pack_mass_kg": "30"})
TILE = ent("TL", "плитка 300х300", "tile",
           {"tile_w_mm": "300", "tile_h_mm": "300", "m2_per_pack": "1"})
LAM = ent("LM", "ламинат 33 класс", "laminate", {"m2_per_pack": "2"})
UNDER = ent("UN", "подложка", "underlay", {"m2_per_pack": "10"})
SKIRT = ent("SK", "плинтус", "skirting", {"piece_len_m": "2.5"})
CATALOG = [PAINT, PRIMER, PUTTY, TILE, LAM, UNDER, SKIRT]


def packs(cond: Conditions | None, sku: str, room_type: str = "living", klass: str = "major",
          catalog: list[CatalogEntry] | None = None) -> tuple[int, list[str]]:
    est = calc_room(ROOM, room_type, klass, catalog or CATALOG, conditions=cond)
    line = next(ln for ln in est.basket.lines if ln.sku == sku)
    return int(line.qty_packs), line.explain


def test_1_tile_straight_vs_diagonal() -> None:
    straight, _ = packs(None, "TL", "bathroom")                       # 12 x 1.07 = 12.84 -> 13
    diagonal, ex2 = packs(Conditions(floor_layout="diagonal"), "TL", "bathroom")  # 13.44 -> 14
    assert (straight, diagonal) == (13, 14)
    assert any("diagonal" in e and "0.12" in e for e in ex2)


def test_2_putty_even_vs_uneven_walls() -> None:
    even, _ = packs(None, "PU")                                 # 35 x 2 mm x 1 = 70 kg -> 4 bags
    uneven, ex = packs(Conditions(wall_evenness="uneven"), "PU")  # 35 x 3 = 105 kg -> 6 bags
    assert (even, uneven) == (4, 6)
    assert any("evenness=uneven" in e and "Ceresit CT 225" in e for e in ex)


def test_3_paint_one_vs_two_layers() -> None:
    one, _ = packs(Conditions(paint_layers=1), "PA")            # 47 / 10 = 4.7 l -> 2 packs of 2.5
    two, _ = packs(Conditions(paint_layers=2), "PA")            # 9.4 l -> 4 packs
    assert (one, two) == (2, 4)


def test_4_paint_on_absorbent_surface() -> None:
    smooth, _ = packs(None, "PA")                               # 9.4 l -> 4
    absorbent, ex = packs(Conditions(paint_surface="absorbent"), "PA")   # 9.4 x 1.43 = 13.442 -> 6
    assert (smooth, absorbent) == (4, 6)
    assert any("1.43" in e and "Tikkurila Prof Euro 7" in e for e in ex)


def test_5_machine_vs_manual_plaster() -> None:
    cat = [PLASTER, PRIMER, PAINT]
    manual, _ = packs(None, "PL", catalog=cat)     # 35 x 10 x 0.85 = 297.5 kg -> 10 bags of 30
    machine, ex = packs(Conditions(plaster_application="machine"), "PL", catalog=cat)
    assert (manual, machine) == (10, 12)          # 297.5 x 1.18 = 351.05 kg -> 12
    assert any("application=machine" in e and "1.18" in e for e in ex)


def test_6_wallpaper_with_and_without_rapport() -> None:
    low = Room.rectangle(4, 3, "2.2")        # strip 2.3 m: 4 per roll; with rapport 2.56 m: 3
    plain = wallpaper.rolls(low, "0.53", "10.05", 0, "straight", "0.1", 0)
    pattern = wallpaper.rolls(low, "0.53", "10.05", "0.64", "straight", "0.1", 0)
    assert (plain.value, pattern.value) == (D(7), D(10))
    assert any("раппорт" in e.lower() for e in pattern.explain)


def test_7_laminate_straight_vs_diagonal() -> None:
    cat = [LAM, UNDER, SKIRT, PAINT, PRIMER]
    straight, _ = packs(None, "LM", klass="cosmetic", catalog=cat)    # 12 x 1.05 / 2 = 6.3 -> 7
    diagonal, ex = packs(Conditions(floor_layout="diagonal"), "LM", klass="cosmetic",
                         catalog=cat)                                  # 12 x 1.20 / 2 = 7.2 -> 8
    assert straight == 7 and diagonal == 8
    area = flooring.area_with_waste(12, "herringbone").value          # 12 x 1.15 = 13.8
    assert area == D("13.8") and any("diagonal" in e for e in ex)


def test_every_correction_has_a_public_source() -> None:
    for c in load_corrections().entries:
        assert c.source.url.startswith("https://") and c.source.quote and c.reason
        assert c.source.kind in ("manufacturer", "third_party", "derived")
