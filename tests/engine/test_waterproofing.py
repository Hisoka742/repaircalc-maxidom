from decimal import Decimal as D

import pytest

from maxicalc.engine.geometry import Opening, Room
from maxicalc.engine.materials import coatings, waterproofing


@pytest.mark.parametrize(("condition", "rate"), [
    ("high_humidity", "3.5"), ("water_no_pressure", "4.5"), ("water_pressure", "6.0")])
def test_ceresit_cr65_consumption_table(condition: str, rate: str) -> None:
    assert waterproofing.kg(D("1"), condition).value == D(rate)


def test_card_value_overrides_table() -> None:
    assert waterproofing.kg(D("10"), "high_humidity", kg_per_m2=D("2")).value == D("20")


def test_unknown_condition() -> None:
    with pytest.raises(ValueError):
        waterproofing.kg(D("1"), "swamp")


def test_wet_room_area_floor_plus_wall_strip() -> None:
    r = Room.rectangle(4, 3, "2.5", [Opening("door", D("0.9"), D("2.05"), 0)])
    a = waterproofing.treated_area(r, wall_up_m=D("0.3"))
    # floor 12 + (14 - 0.9) * 0.3 = 15.93
    assert a.value == D("15.93")
    shower = waterproofing.treated_area(r, wall_up_m=D("0.3"), shower_wall_m2=D("4"))
    assert shower.value == D("19.93")


def test_corner_tape_length() -> None:
    r = Room.rectangle(4, 3, "2.5", [Opening("door", D("0.9"), D("2.05"), 0)])
    assert waterproofing.corner_tape_m(r).value == D("13.1")


def test_bags_of_waterproofing() -> None:
    r = Room.rectangle(4, 3, "2.5", [Opening("door", D("0.9"), D("2.05"), 0)])
    area = waterproofing.treated_area(r, wall_up_m=D("0.3")).value
    kg = waterproofing.kg(area, "high_humidity").value
    assert kg == D("55.755")
    assert coatings.packs(kg, D("25")).value == 3


def test_self_leveling_consumption_ceresit_cn68() -> None:
    # CN 68 (BY edition): ~1.8 kg/m2/mm
    kg = coatings.kg_by_thickness(D("20"), thickness_mm=D("5"), kg_per_m2_per_mm=D("1.8"))
    assert kg.value == D("180")
    assert coatings.packs(kg.value, D("25")).value == 8
