from decimal import Decimal as D

import pytest

from maxicalc.engine import electrical, labor
from maxicalc.engine.materials import drywall, flooring


def test_drywall_sheets_with_waste() -> None:
    # 1.2 x 2.5 = 3 m2 ; 10 m2 * 1.1 / 3 = 3.67 -> 4
    c = drywall.sheets(D("10"), sheet_w_m=D("1.2"), sheet_h_m=D("2.5"))
    assert c.value == 4
    assert c.unit == "лист"


def test_drywall_sheets_exact_boundary() -> None:
    # 30 m2 * 1.1 / 3 = 11 exactly -> 11, not 12
    assert drywall.sheets(D("30"), D("1.2"), D("2.5")).value == 11


def test_knauf_c111_quantities_per_m2() -> None:
    q = drywall.system_quantities(D("10"), drywall.KNAUF_C111)
    assert q["profile_ps_50"].value == D("20") and q["profile_ps_50"].unit == "м"
    assert q["screws_tn25"].value == D("290")
    assert q["sealing_tape"].value == D("12")
    assert q["sheet_12_5"].value == D("20")  # both faces


def test_knauf_c611_quantities_per_m2() -> None:
    q = drywall.system_quantities(D("10"), drywall.KNAUF_C611)
    assert q["adhesive_perlfix"].value == D("35")
    assert q["reinforcing_tape"].value == D("7.5")


def test_underlay_packs() -> None:
    assert flooring.underlay_packs(D("12"), m2_per_pack=D("10")).value == 2  # 12.6 / 10
    assert flooring.underlay_packs(D("9.5"), m2_per_pack=D("10")).value == 1  # 9.975 / 10


NORMS = {
    "living": electrical.RoomNorms(m2_per_socket=D("6"), min_sockets=3, switches=1,
                                   m2_per_light=D("8"), cable_m_per_point=D("6")),
}


def test_electrical_estimate_is_labelled_estimate() -> None:
    e = electrical.estimate("living", D("20"), NORMS)
    assert e.sockets == 4  # max(3, ceil(20/6)=4)
    assert e.switches == 1
    assert e.light_points == 3  # ceil(20/8)
    assert e.points == 8
    assert e.junction_boxes == 8
    assert e.cable_m == D("48.0") or e.cable_m == D("48")
    assert e.breakers == 2  # 1 socket group + 1 light group
    assert any("оценк" in line.lower() for line in e.explain)


def test_electrical_min_sockets_floor() -> None:
    assert electrical.estimate("living", D("5"), NORMS).sockets == 3


def test_electrical_unknown_room() -> None:
    with pytest.raises(ValueError):
        electrical.estimate("garage", D("10"), NORMS)


RATES = {"wallpapering": labor.WorkRate("wallpapering", "м²", D("500"), "test")}
SPREAD = labor.Spread(low=D("0.9"), high=D("1.2"))


def test_labor_range() -> None:
    r = labor.estimate("wallpapering", D("10"), RATES, region_coeff=D("1.1"),
                       class_mult=D("1.2"), spread=SPREAD)
    assert r.expected == D("6600.00")
    assert r.low == D("5940.00")
    assert r.high == D("7920.00")
    assert any("прибли" in line.lower() for line in r.explain)


def test_labor_missing_rate_is_an_error_not_a_guess() -> None:
    rates = {"tiling": labor.WorkRate("tiling", "м²", None, "TODO: no source yet")}
    with pytest.raises(ValueError, match="ставка"):
        labor.estimate("tiling", D("10"), rates, D("1"), D("1"), SPREAD)
    with pytest.raises(ValueError, match="ставка"):
        labor.estimate("plumbing", D("10"), rates, D("1"), D("1"), SPREAD)
