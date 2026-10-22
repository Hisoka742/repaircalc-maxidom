"""Checklist C4 (pack optimiser in the estimate) and D2 (grouping by work package)."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.basket import Need, build_basket
from maxicalc.service.room_calc import RoomPlan


def entry(sku: str, calc: str, price: str, attrs: dict[str, str]) -> CatalogEntry:
    return CatalogEntry(Product(sku=sku, name=f"Товар {sku}", price=D(price)), work=set(),
                        rooms={"any"}, props=set(), calc=calc, status="verified",
                        attrs={k: D(v) for k, v in attrs.items()})


def plan(needs: list[Need]) -> RoomPlan:
    return RoomPlan("Комната", "living", needs, [], [])


def test_a_cheaper_mix_of_pack_sizes_is_offered_next_to_the_single_sku_basket() -> None:
    small = entry("P25", "paint", "1000", {"pack_volume_l": "2.5"})
    big = entry("P9", "paint", "2200", {"pack_volume_l": "9"})
    need = Need(small, D(11), "л", D("2.5"), "уп", ["11 л"], [big])
    b = build_basket([plan([need])])
    line = b.lines[0]
    assert line.qty_packs == 5 and line.line_total == D(5000)        # the basket itself: one SKU
    assert line.optimized is not None
    assert line.optimized["total"] == D(3200)                         # 1 x 9 l + 1 x 2.5 l
    assert {(p["sku"], p["count"]) for p in line.optimized["packs"]} == {("P9", 1), ("P25", 1)}
    assert line.optimized["saving"] == D(1800)
    assert b.materials_total == D(5000)                               # main total unchanged
    assert b.optimized_total == D(3200)


def test_no_alternative_means_no_optimized_plan() -> None:
    only = entry("P25", "paint", "1000", {"pack_volume_l": "2.5"})
    b = build_basket([plan([Need(only, D(11), "л", D("2.5"), "уп", [], [])])])
    assert b.lines[0].optimized is None and b.optimized_total == b.materials_total


def test_a_dearer_alternative_is_not_offered() -> None:
    small = entry("P25", "paint", "1000", {"pack_volume_l": "2.5"})
    dear = entry("P9", "paint", "9000", {"pack_volume_l": "9"})
    b = build_basket([plan([Need(small, D(11), "л", D("2.5"), "уп", [], [dear])])])
    assert b.lines[0].optimized is None


def test_lines_are_grouped_by_work_package_and_the_groups_add_up() -> None:
    p = entry("P1", "paint", "1000", {"pack_volume_l": "2.5"})
    lam = entry("L1", "laminate", "1500", {"m2_per_pack": "2.131"})
    w = entry("W1", "wallpaper", "800", {})
    needs = [Need(p, D(5), "л", D("2.5"), "уп", [], []),
             Need(lam, D(10), "м²", D("2.131"), "уп", [], []),
             Need(w, D(4), "рулон", D(1), "рулон", [], [])]
    b = build_basket([plan(needs)])
    by = {g.key: g for g in b.groups}
    assert [g.key for g in b.groups] == ["floor", "walls", "wallpaper"]
    assert by["walls"].title == "Стены" and by["floor"].title == "Пол"
    assert by["walls"].total == D(2000) and by["wallpaper"].total == D(3200)
    assert sum(g.total for g in b.groups) == b.materials_total
    assert {ln.sku: ln.group for ln in b.lines} == {"P1": "walls", "L1": "floor", "W1": "wallpaper"}
