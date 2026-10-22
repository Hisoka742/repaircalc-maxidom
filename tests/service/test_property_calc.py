from decimal import Decimal as D

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Room
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.basket import Need, build_basket
from maxicalc.service.property_calc import PropertyInput, RoomInput, calc_property
from maxicalc.service.room_calc import plan_room


def e(sku: str, calc: str, price: str, attrs: dict[str, object], props: set[str] | None = None,
      work: set[str] | None = None, name: str | None = None) -> CatalogEntry:
    return CatalogEntry(
        Product(sku=sku, name=name or f"Товар {sku}", price=D(price)),
        work=work or set(), rooms={"any"}, props=props or set(), calc=calc, status="verified",
        attrs={k: (v if isinstance(v, int) else D(str(v))) for k, v in attrs.items()})


CAT = [
    e("P1", "paint", "1000", {"spread_m2_per_l": 10, "pack_volume_l": "2.5"}, {"washable"}),
    e("R1", "primer", "500", {"consumption_l_per_m2": "0.15", "pack_volume_l": 5}),
    e("L1", "laminate", "1500", {"m2_per_pack": "2.131"}, {"wear_class_33"}),
    e("U1", "underlay", "300", {"m2_per_pack": 10}),
    e("S1", "skirting", "200", {"piece_len_m": "2.5"}),
]
LIVING = Room.rectangle(4, 3, "2.5")


def by_sku(lines):  # type: ignore[no-untyped-def]
    return {ln.sku: ln for ln in lines}


# ---------- room plan -> basket, hand-computed ----------
def test_living_room_cosmetic_quantities() -> None:
    plan = plan_room(LIVING, "living", "cosmetic", CAT)
    basket = build_basket([plan])
    q = by_sku(basket.lines)
    # walls 14*2.5 = 35 + ceiling 12 = 47 m2
    assert q["P1"].qty_packs == 4      # 47*2/10 = 9.4 l / 2.5 = 3.76 -> 4
    assert q["R1"].qty_packs == 2      # 47*0.15 = 7.05 l / 5 = 1.41 -> 2
    assert q["L1"].qty_packs == 6      # 12*1.05 = 12.6 / 2.131 = 5.91 -> 6 (Quick-Step 5 %)
    assert q["U1"].qty_packs == 2      # 12*1.05 = 12.6 / 10 -> 2
    assert q["S1"].qty_packs == 6      # 14*1.05/2.5 = 5.88 -> 6
    assert basket.materials_total == D("15800")
    assert q["L1"].line_total == D("9000") and q["L1"].unit_price == D("1500")


def test_every_line_has_russian_explain_and_reason() -> None:
    basket = build_basket([plan_room(LIVING, "living", "cosmetic", CAT)])
    for ln in basket.lines:
        assert ln.explain and any(ch in "".join(ln.explain) for ch in "абвгдежзиклмн")
        assert ln.reason


# ---------- accuracy: round once, after summing across rooms ----------
def test_quantities_are_summed_before_rounding() -> None:
    paint = e("P1", "paint", "1000", {"spread_m2_per_l": 10, "pack_volume_l": "2.5"})
    need = lambda: Need(entry=paint, base_qty=D("3"), base_unit="л", pack_size=D("2.5"),  # noqa: E731
                        pack_unit="уп", explain=["комната: 3 л"], alternatives=[])
    basket = build_basket_from([need(), need()])
    assert by_sku(basket.lines)["P1"].qty_packs == 3   # 6 l / 2.5 = 2.4 -> 3 (not 2 + 2 = 4)


def build_basket_from(needs: list[Need]):  # type: ignore[no-untyped-def]
    from maxicalc.service.room_calc import RoomPlan
    return build_basket([RoomPlan("r", "living", needs, [], [])])


# ---------- honesty: missing data -> warning, never a guess ----------
def test_missing_card_data_skips_candidate_then_falls_back() -> None:
    bad = e("A_BAD", "paint", "100", {"pack_volume_l": 2})          # no spread rate; sorts first
    cat = [bad, *CAT]
    plan = plan_room(LIVING, "living", "cosmetic", cat)
    skus = {n.entry.product.sku for n in plan.needs}
    assert "P1" in skus and "A_BAD" not in skus


def test_no_usable_product_gives_warning_not_line() -> None:
    cat = [c for c in CAT if c.calc != "paint"]
    plan = plan_room(LIVING, "living", "cosmetic", cat)
    assert not any(n.entry.calc == "paint" for n in plan.needs)
    assert any("краск" in w.lower() or "paint" in w for w in plan.warnings)


def test_room_rules_are_enforced_in_the_plan() -> None:
    bath = Room.rectangle(2, 2, "2.5")
    cat = [e("PX", "paint", "100", {"spread_m2_per_l": 10, "pack_volume_l": 2})]  # not washable
    plan = plan_room(bath, "bathroom", "cosmetic", cat)
    assert not any(n.entry.calc == "paint" for n in plan.needs)


def test_assumed_defaults_are_reported() -> None:
    cat = [e("S2", "skirting", "200", {})]    # no piece length on the card
    plan = plan_room(LIVING, "living", "cosmetic", cat)
    assert any("2,5" in a or "2.5" in a for a in plan.assumptions)
    assert any(n.entry.product.sku == "S2" for n in plan.needs)


# ---------- renovation classes ----------
FULL = [
    *CAT,
    e("PUT", "putty", "800", {"consumption_kg_per_m2_per_mm": "1.1", "pack_mass_kg": 25}),
    e("SL", "self_leveling", "900", {"consumption_kg_per_m2_per_mm": "1.8", "pack_mass_kg": 25}),
]


def test_major_adds_putty_and_levelling_but_cosmetic_does_not() -> None:
    cos = {n.entry.calc for n in plan_room(LIVING, "living", "cosmetic", FULL).needs}
    maj = {n.entry.calc for n in plan_room(LIVING, "living", "major", FULL).needs}
    assert "putty" not in cos and "self_leveling" not in cos
    assert {"putty", "self_leveling"} <= maj


def test_putty_quantity() -> None:
    plan = plan_room(LIVING, "living", "major", FULL)
    putty = next(n for n in plan.needs if n.entry.calc == "putty")
    assert putty.base_qty == D("35") * D("2") * D("1.1")     # walls 35 m2 x 2 mm x 1.1 kg
    lev = next(n for n in plan.needs if n.entry.calc == "self_leveling")
    assert lev.base_qty == D("12") * D("5") * D("1.8")       # 12 m2 x 5 mm x 1.8 kg


def test_unknown_class_rejected() -> None:
    with pytest.raises(ValueError):
        plan_room(LIVING, "living", "luxury", CAT)


# ---------- property level ----------
def test_apartment_rooms_come_from_preset_and_cover_total_area() -> None:
    est = calc_property(PropertyInput("apartment", D("60"), "cosmetic"), CAT)
    assert {r.room_type for r in est.rooms} >= {"living", "bedroom", "kitchen", "bathroom"}
    assert sum((r.area_m2 for r in est.rooms), D(0)) == D("60")
    assert abs(next(r for r in est.rooms if r.room_type == "living").area_m2 - D("18")) < D("1e-9")


def test_user_rooms_override_preset() -> None:
    inp = PropertyInput("apartment", D("60"), "cosmetic",
                        rooms=[RoomInput("living", D("20")), RoomInput("bedroom", D("12"))])
    est = calc_property(inp, CAT)
    assert [r.room_type for r in est.rooms] == ["living", "bedroom"]
    assert est.rooms[0].area_m2 == D("20")


def test_property_basket_merges_same_sku_across_rooms() -> None:
    inp = PropertyInput("apartment", D("60"), "cosmetic",
                        rooms=[RoomInput("living", D("12")), RoomInput("bedroom", D("12"))])
    est = calc_property(inp, CAT)
    assert len([ln for ln in est.basket.lines if ln.sku == "P1"]) == 1


def test_unknown_property_type_and_bad_area() -> None:
    with pytest.raises(ValueError):
        calc_property(PropertyInput("castle", D("100"), "cosmetic"), CAT)
    with pytest.raises(ValueError):
        calc_property(PropertyInput("apartment", D("0"), "cosmetic"), CAT)


def test_labor_is_a_range_for_cosmetic_and_unavailable_for_unsourced_class() -> None:
    est = calc_property(PropertyInput("apartment", D("60"), "cosmetic"), CAT)
    assert est.labor is not None and est.labor.low <= est.labor.expected <= est.labor.high
    major = calc_property(PropertyInput("apartment", D("60"), "major"), CAT)
    assert major.labor is not None and major.labor.expected >= est.labor.expected


def test_tier_changes_selection() -> None:
    cat = [e(f"P{i}", "paint", str(i * 100), {"spread_m2_per_l": 10, "pack_volume_l": 2})
           for i in range(1, 11)]
    eco = calc_property(PropertyInput("apartment", D("30"), "cosmetic", tier="economy"), cat)
    pre = calc_property(PropertyInput("apartment", D("30"), "cosmetic", tier="premium"), cat)
    price = lambda est: by_sku(est.basket.lines)  # noqa: E731
    eco_p = next(ln for ln in eco.basket.lines if ln.sku.startswith("P"))
    pre_p = next(ln for ln in pre.basket.lines if ln.sku.startswith("P"))
    assert eco_p.unit_price < pre_p.unit_price
    assert price(eco)


def test_to_entries_carries_labels_and_attributes() -> None:
    from maxicalc.ml.match import Matcher
    from maxicalc.recommend.build import to_entries

    p = Product(sku="1", name="Краска водоэмульсионная моющаяся 2,5 л", category_path=["Краски"],
                description="Расход 10 м2/л")
    [entry] = to_entries([p], Matcher().match([p]))
    assert entry.calc == "paint" and "washable" in entry.props
    assert entry.attrs["pack_volume_l"] == D("2.5") and entry.attrs["spread_m2_per_l"] == D("10")


def test_explain_traces_are_human_readable_but_calculation_is_exact() -> None:
    import re

    est = calc_property(PropertyInput("apartment", D("60"), "cosmetic"), CAT)
    for ln in est.basket.lines:
        for line in ln.explain:
            assert not re.search(r"\d+\.\d{5,}", line), line   # no 28-digit decimals shown
    # presentation rounding must not change the purchased quantity
    q = {ln.sku: ln.qty_packs for ln in est.basket.lines}
    assert q["P1"] > 0 and q["L1"] > 0
