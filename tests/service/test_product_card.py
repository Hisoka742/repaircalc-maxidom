from decimal import Decimal as D

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Opening, Room
from maxicalc.recommend.index import CatalogIndex
from maxicalc.recommend.select import CatalogEntry, recommend
from maxicalc.service.basket import build_basket
from maxicalc.service.room_calc import plan_product


def e(sku: str, calc: str, price: str, attrs: dict[str, object],
      props: set[str] | None = None) -> CatalogEntry:
    return CatalogEntry(
        Product(sku=sku, name=f"Товар {sku}", price=D(price)), work=set(), rooms={"any"},
        props=props or set(), calc=calc, status="verified",
        attrs={k: (v if isinstance(v, int) else D(str(v))) for k, v in attrs.items()})


WALLPAPER = e("W1", "wallpaper", "1500", {"roll_width_m": "1.06", "roll_length_m": "10.05"})
PRIMER = e("R1", "primer", "500", {"consumption_l_per_m2": "0.15", "pack_volume_l": 5})
PAINT = e("P1", "paint", "1000", {"spread_m2_per_l": 10, "pack_volume_l": "2.5"}, {"washable"})
TILE = e("T1", "tile", "1100", {"tile_w_mm": 300, "tile_h_mm": 300, "m2_per_pack": "1.44"})
ADH = e("A1", "tile_adhesive", "600", {"pack_mass_kg": 25})
GROUT = e("G1", "grout", "350", {"pack_mass_kg": 2})
LAM = e("L1", "laminate", "1500", {"m2_per_pack": "2.131"}, {"wear_class_33"})
UND = e("U1", "underlay", "300", {"m2_per_pack": 10})
SKIRT = e("S1", "skirting", "200", {"piece_len_m": "2.5"})
CATALOG = [WALLPAPER, PRIMER, PAINT, TILE, ADH, GROUT, LAM, UND, SKIRT]

ROOM = Room.rectangle(4, 3, "2.5", [Opening("door", D("0.9"), D("2.05"), 0)])


def lines(plan):  # type: ignore[no-untyped-def]
    return {ln.sku: ln for ln in build_basket([plan]).lines}


def test_wallpaper_card_gives_rolls_by_strips_and_primer_companion() -> None:
    plan = plan_product(ROOM, "living", WALLPAPER, CATALOG)
    q = lines(plan)
    assert q["W1"].qty_packs == 5            # strips 3+3+4+3 = 13, 3 per roll -> 5 rolls
    primer = next(n for n in plan.needs if n.entry.calc == "primer")
    assert primer.base_qty == D("33.155") * D("0.15")   # walls only, no ceiling, door excluded
    assert q["R1"].qty_packs == 1


def test_paint_card_with_and_without_ceiling() -> None:
    walls = Room.rectangle(4, 3, "2.5")
    with_c = plan_product(walls, "living", PAINT, CATALOG)
    no_c = plan_product(walls, "living", PAINT, CATALOG, include_ceiling=False)
    p1 = next(n for n in with_c.needs if n.entry.calc == "paint")
    p2 = next(n for n in no_c.needs if n.entry.calc == "paint")
    assert p1.base_qty == D("47") * 2 / 10     # walls 35 + ceiling 12
    assert p2.base_qty == D("35") * 2 / 10


def test_tile_card_includes_adhesive_and_grout_even_in_a_dry_room() -> None:
    kitchen = Room.rectangle(3, 3, "2.5")
    q = lines(plan_product(kitchen, "kitchen", TILE, CATALOG))
    assert q["T1"].qty_packs == 7     # 9 * 1.07 = 9.63 / 1.44 = 6.69
    assert q["A1"].qty_packs == 2     # 9 * 4.2 = 37.8 kg / 25
    assert q["G1"].qty_packs == 2     # 9 * 0.256 = 2.304 kg / 2


def test_laminate_card_companions_underlay_and_skirting() -> None:
    q = lines(plan_product(ROOM, "living", LAM, CATALOG))
    assert set(q) == {"L1", "U1", "S1"}
    assert q["L1"].qty_packs == 6 and q["U1"].qty_packs == 2 and q["S1"].qty_packs == 6


def test_chosen_product_violating_room_rules_is_calculated_but_warned() -> None:
    plain = e("PX", "paint", "100", {"spread_m2_per_l": 10, "pack_volume_l": 2})
    plan = plan_product(Room.rectangle(2, 2, "2.5"), "bathroom", plain, [plain])
    assert any(n.entry.product.sku == "PX" for n in plan.needs)
    assert any("не рекомендуется" in w for w in plan.warnings)


def test_missing_card_data_gives_warning_not_quantity() -> None:
    bare = e("PB", "paint", "100", {"pack_volume_l": 2})
    plan = plan_product(Room.rectangle(2, 2, "2.5"), "living", bare, [bare])
    assert plan.needs == [] and any("spread_m2_per_l" in w for w in plan.warnings)


def test_unsupported_product_type() -> None:
    sock = e("E1", "electrical", "100", {})
    with pytest.raises(ValueError, match="калькулятор"):
        plan_product(ROOM, "living", sock, [sock])


# ---------- catalog index ----------
def test_index_memoises_and_matches_plain_recommend() -> None:
    idx = CatalogIndex(CATALOG)
    a = idx.recommend("living", "paint", None)
    assert idx.recommend("living", "paint", None) is a          # memoised
    plain = recommend(CATALOG, "living", calc="paint", top_k=10)
    assert [c.entry.product.sku for c in a.items] == [c.entry.product.sku for c in plain.items]
    assert idx.get("P1") is PAINT and idx.get("nope") is None
    assert {x.product.sku for x in idx.of_calc("tile")} == {"T1"}


def test_index_query_is_memoised_and_equals_direct_recommend() -> None:
    from maxicalc.recommend.select import Constraints

    idx = CatalogIndex(CATALOG)
    a = idx.query("living", None, "paint", Constraints(), 5)
    assert idx.query("living", None, "paint", Constraints(), 5) is a
    assert [c.entry.product.sku for c in a.items] == [
        c.entry.product.sku for c in recommend(CATALOG, "living", calc="paint", top_k=5).items]
    assert idx.query("living", None, "paint", Constraints(max_price=D("1")), 5) is not a
