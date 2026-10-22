"""Spacers from layout geometry: hand-computed counts and the explain trace."""
from decimal import Decimal as D

import pytest

from maxicalc.engine.materials import tile


def test_straight_layout_300mm_tile_3mm_joint() -> None:
    # pitch 303 mm -> n = 10 m2 / 0.091809 m2 = 108.9...; nodes = n + 2 sqrt(n) = 129.8 -> 130
    r = tile.spacers(10, 300, 300, 3, "straight")
    assert r.value == D(130) and r.unit == "шт"
    assert any("раскладка straight" in e for e in r.explain)


def test_offset_layout_doubles_the_node_count() -> None:
    s = tile.spacers(10, 300, 300, 3, "straight").value
    o = tile.spacers(10, 300, 300, 3, "offset").value
    assert s == D(130) and o == D(260)   # 2 x 129.8 = 259.6 -> 260


def test_bigger_tile_needs_fewer_spacers_and_zero_area_none() -> None:
    assert tile.spacers(10, 600, 600, 3).value < tile.spacers(10, 300, 300, 3).value
    assert tile.spacers(0, 300, 300, 3).value == D(0)


def test_invalid_input_raises() -> None:
    with pytest.raises(ValueError):
        tile.spacers(10, 0, 300, 3)
    with pytest.raises(ValueError):
        tile.spacers(10, 300, 300, 0)
