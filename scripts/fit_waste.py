"""Fit waste/cutting coefficients from order data.

    uv run python scripts/fit_waste.py orders.csv \
        --out src/maxicalc/knowledge/waste_coefficients.yaml

orders.csv: layout,required_m2,bought_m2 (one row per order line). Prints the old and new
coefficients; with fewer than 5 rows per layout the default is kept. Do not run on invented data:
the result is only as good as the orders.
"""
import argparse
import sys
from pathlib import Path

from maxicalc.knowledge.loader import load_waste_table
from maxicalc.ml.waste_fit import fit_table, load_orders, write_table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("orders")
    ap.add_argument("--out", default=None, help="write the fitted table here")
    a = ap.parse_args()
    try:
        rows, skipped = load_orders(Path(a.orders))
    except (OSError, ValueError) as e:
        print(f"ОШИБКА: {e}")
        return 2
    old = load_waste_table()
    new = fit_table(rows, old, source=Path(a.orders).name)
    print(f"Заказов: {len(rows)} (пропущено {skipped})")
    for k in old.layouts:
        print(f"  {k}: {old.layouts[k]} -> {new.layouts[k]}")
    print(f"Источник: {new.source}")
    if a.out:
        write_table(new, Path(a.out))
        print(f"Записано: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
