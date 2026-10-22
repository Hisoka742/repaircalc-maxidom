from decimal import Decimal as D

import pytest
from hypothesis import given
from hypothesis import strategies as st

from maxicalc.engine.geometry import Opening, Room


def test_rectangle_basics() -> None:
    door = Opening("door", D("0.9"), D("2.05"), wall=0)
    win = Opening("window", D("1.2"), D("1.4"), wall=1)
    r = Room.rectangle(4, 3, "2.5", [door, win])
    assert r.floor_area_m2 == 12
    assert r.ceiling_area_m2 == 12
    assert r.perimeter_m == 14
    assert r.wall_area_gross_m2 == 35
    assert r.wall_area_net_m2 == D("35") - D("1.845") - D("1.68")
    assert r.skirting_length_m == D("13.1")
    assert r.wall_net_widths_m() == (D("3.1"), 3, 4, 3)
    assert (r.inner_corners, r.outer_corners) == (4, 0)


def test_l_shape() -> None:
    pts = [(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)]
    r = Room.from_vertices(pts, "2.5")
    assert r.floor_area_m2 == 12
    assert r.perimeter_m == 16
    assert (r.inner_corners, r.outer_corners) == (5, 1)


def test_orientation_independent() -> None:
    pts = [(0, 0), (4, 0), (4, 2), (2, 2), (2, 4), (0, 4)]
    r = Room.from_vertices(pts[::-1], "2.5")
    assert r.floor_area_m2 == 12
    assert (r.inner_corners, r.outer_corners) == (5, 1)


def test_validation() -> None:
    with pytest.raises(ValueError):
        Room.rectangle(4, 3, 0)
    with pytest.raises(ValueError):
        Room.rectangle(4, 3, "2.5", [Opening("door", D("5"), D("2"), wall=0)])
    with pytest.raises(ValueError):
        Room.rectangle(4, 3, "2.5", [Opening("door", D("1"), D("3"), wall=0)])
    with pytest.raises(ValueError):
        Room.rectangle(4, 3, "2.5", [Opening("door", D("1"), D("2"), wall=9)])


@given(
    w=st.decimals(min_value="0.3", max_value="2.5", places=2),
    h=st.decimals(min_value="0.3", max_value="2.4", places=2),
    wall=st.integers(0, 3),
    kind=st.sampled_from(["door", "window"]),
)
def test_opening_never_increases_material(w: D, h: D, wall: int, kind: str) -> None:
    base = Room.rectangle(4, 3, "2.5")
    with_op = Room.rectangle(4, 3, "2.5", [Opening(kind, w, h, wall)])  # type: ignore[arg-type]
    assert with_op.wall_area_net_m2 <= with_op.wall_area_gross_m2
    assert with_op.wall_area_net_m2 <= base.wall_area_net_m2
    assert with_op.skirting_length_m <= base.skirting_length_m
