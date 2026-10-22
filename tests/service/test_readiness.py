from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.ml.readiness import readiness_report
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.requirements import REQUIREMENTS, missing_attrs
from maxicalc.service.room_calc import PRODUCT_CALCS


def e(sku: str, calc: str, attrs: dict[str, object], status: str = "auto") -> CatalogEntry:
    return CatalogEntry(
        Product(sku=sku, name=sku, price=D("1")), work=set(), rooms={"any"}, props=set(),
        calc=calc, status=status,
        attrs={k: (v if isinstance(v, int) else D(str(v))) for k, v in attrs.items()})


def test_requirements_cover_every_product_calculator() -> None:
    # every calc that has a quantity calculator is described in the table (skirting needs nothing)
    assert set(PRODUCT_CALCS) <= set(REQUIREMENTS) | {"skirting"}


def test_missing_attrs() -> None:
    assert missing_attrs("paint", {"spread_m2_per_l": D(10), "pack_volume_l": D(2)}) == []
    assert missing_attrs("paint", {"pack_volume_l": D(2)}) == ["spread_m2_per_l"]
    # tile needs a size AND either m2 or pieces per pack
    assert missing_attrs("tile", {"tile_w_mm": D(300), "tile_h_mm": D(300)}) == [
        "m2_per_pack/pcs_per_pack"]
    assert missing_attrs("tile", {"tile_w_mm": D(300), "tile_h_mm": D(300),
                                  "pcs_per_pack": 10}) == []
    assert missing_attrs("skirting", {}) == []
    assert missing_attrs("unknown_calc", {}) == []


def test_readiness_report_shares_and_top_missing() -> None:
    entries = [
        e("p1", "paint", {"spread_m2_per_l": 10, "pack_volume_l": 2}),
        e("p2", "paint", {"pack_volume_l": 2}),
        e("p3", "paint", {}),
        e("p4", "paint", {"spread_m2_per_l": 10, "pack_volume_l": 2}, status="review"),  # ignored
        e("l1", "laminate", {"m2_per_pack": "2.1"}),
        e("x1", "none", {}),                                                             # ignored
    ]
    rep = readiness_report(entries)
    paint = rep["paint"]
    assert (paint.total, paint.ready) == (3, 1)
    assert abs(paint.share - 1 / 3) < 1e-9
    assert paint.top_missing[0] == ("spread_m2_per_l", 2)
    assert rep["laminate"].share == 1.0
    assert "none" not in rep


def test_readiness_flags_blocking_types() -> None:
    entries = [e(f"p{i}", "paint", {}) for i in range(10)]
    entries.append(e("l", "laminate", {"m2_per_pack": 2}))
    rep = readiness_report(entries)
    assert rep["paint"].blocking and not rep["laminate"].blocking
