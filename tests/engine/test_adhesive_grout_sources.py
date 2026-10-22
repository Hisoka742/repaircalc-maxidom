"""Brand tables for tile adhesive and grout against manufacturer datasheet rows (sources in
engine/materials/tile.py and docs/CONSUMPTION_SOURCES.md)."""
from decimal import Decimal as D

import pytest

from maxicalc.engine.materials import tile


@pytest.mark.parametrize("side_mm,expected",
                         [(100, "2.6"), (250, "3.9"), (450, "5.2"), (800, "6.5")])
def test_osnovit_adhesive_table_rows(side_mm: int, expected: str) -> None:
    r = tile.adhesive_kg(1, side_mm, side_mm, None, "osnovit_ac14")
    assert r.value == D(expected)


# LITOKOL STARLIKE CRYSTAL EVO datasheet (bas.ru/docs/litokol-starlike-evo_2985.pdf), "Таблица
# расхода": tile w x h x thickness mm, joint mm -> kg/m2. The formula must reproduce it.
LITOKOL = [((10, 10, 3), 1, "0.93"), ((10, 10, 3), D("1.5"), "1.40"), ((20, 20, 3), 1, "0.47"),
           ((30, 30, 8), 2, "1.65"), ((50, 50, 4), 1, "0.25"), ((15, 15, 10), 2, "4.13")]


@pytest.mark.parametrize("dims,joint,table_kg", LITOKOL)
def test_grout_formula_reproduces_litokol_table(  # type: ignore[no-untyped-def]
        dims, joint, table_kg) -> None:
    w, h, t = dims
    q = tile.grout_kg_per_m2(w, h, t, joint, "1.6").value
    assert abs(q - D(table_kg)) / D(table_kg) < D("0.04")
