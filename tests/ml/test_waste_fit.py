"""Checklist C6: waste/cutting coefficients are data, learnable, and named in explain."""
import random
from decimal import Decimal as D
from pathlib import Path

import pytest

from maxicalc.engine.materials import flooring, tile, waste
from maxicalc.knowledge.loader import load_waste_table
from maxicalc.ml.waste_fit import Order, fit_table, load_orders, write_table


def test_default_table_reproduces_the_previous_constants() -> None:
    t = waste.DEFAULT_TABLE
    assert t.layouts == {"straight": D("0.07"), "diagonal": D("0.12"), "herringbone": D("0.15")}
    assert waste.layout_waste("diagonal") == D("0.12")
    assert load_waste_table().layouts == t.layouts           # the shipped YAML = the defaults


def test_a_custom_table_changes_the_quantity_and_is_named_in_explain() -> None:
    custom = waste.WasteTable({"straight": D("0.10"), "diagonal": D("0.20"),
                               "herringbone": D("0.25")}, D("0.03"), D("0.03"),
                              "подогнано по заказам (n=120)")
    r = tile.area_with_waste(D(10), "diagonal", 300, 300, custom)
    assert r.value == D(10) * D("1.20")
    assert "0.20" in " ".join(r.explain) and "n=120" in " ".join(r.explain)
    assert flooring.area_with_waste(D(10), "straight", custom).value == D(11)


def orders(layout: str, true_waste: float, n: int, seed: int = 1) -> list[Order]:
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        req = D(str(round(rnd.uniform(5, 60), 1)))
        noise = D(str(round(rnd.uniform(-0.02, 0.02), 4)))
        out.append(Order(layout, req, req * (1 + D(str(true_waste)) + noise)))
    return out


def test_fit_recovers_the_true_waste_with_enough_orders() -> None:
    t = fit_table(orders("straight", 0.10, 300))
    assert abs(t.layouts["straight"] - D("0.10")) < D("0.01")
    assert t.layouts["diagonal"] == D("0.12")                  # no orders -> default kept
    assert "n=300" in t.source


def test_a_handful_of_orders_barely_moves_the_default() -> None:
    t = fit_table(orders("straight", 0.30, 3))
    assert t.layouts["straight"] == D("0.07")                  # below the minimum sample


def test_shrinkage_toward_the_default_with_a_small_sample() -> None:
    few = fit_table(orders("straight", 0.20, 10)).layouts["straight"]
    many = fit_table(orders("straight", 0.20, 400)).layouts["straight"]
    assert D("0.07") < few < many <= D("0.21")


def test_absurd_waste_is_clamped() -> None:
    t = fit_table(orders("straight", 2.0, 200))
    assert t.layouts["straight"] <= D("0.5")


def test_table_round_trips_through_yaml(tmp_path: Path) -> None:
    from maxicalc.knowledge.loader import read_waste_table

    p = tmp_path / "w.yaml"
    t = fit_table(orders("herringbone", 0.2, 100))
    write_table(t, p)
    back = read_waste_table(p)
    assert back.layouts == t.layouts and back.source == t.source


def test_orders_csv_loader_rejects_nonsense(tmp_path: Path) -> None:
    p = tmp_path / "o.csv"
    p.write_text("layout,required_m2,bought_m2\nstraight,10,10.7\ndiagonal,0,5\nstraight,x,1\n",
                 encoding="utf-8")
    rows, skipped = load_orders(p)
    assert len(rows) == 1 and skipped == 2
    with pytest.raises(ValueError):
        (tmp_path / "bad.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        load_orders(tmp_path / "bad.csv")
