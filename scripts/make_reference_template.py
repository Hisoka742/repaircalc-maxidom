"""Write data/reference_cases_todo.csv: 40 cases for the team to run through MANUFACTURER online
calculators (10 wallpaper, 10 laminate, 10 paint, 10 tile), with exact inputs.

    uv run python scripts/make_reference_template.py [--out data/reference_cases_todo.csv]

Fill, per row: `calculator_url` (the exact page used), `result_value` (what the calculator
returned), `accessed_date`, and the product columns marked (fill). Then:
    uv run python scripts/import_references.py data/reference_cases_todo.csv

Which manufacturer: the `manufacturer_hint` column. The URLs of the calculators are NOT
pre-filled: none of them could be confirmed from here, so a wrong guess would be worse than a
blank. Use the manufacturer's own calculator (not a shop's or a third-party app).
"""
import argparse
import csv
import json
from pathlib import Path

COLUMNS = [
    "id", "calc", "manufacturer_hint", "inputs_text", "inputs_json",
    "calculator_url", "result_value", "result_unit", "accessed_date",
    "roll_width_m (fill)", "roll_length_m (fill)", "m2_per_pack (fill)", "coverage_m2_per_l (fill)",
    "tile_w_mm (fill)", "tile_h_mm (fill)", "note",
]

WALLPAPER_HINT = ("производитель обоев (Erismann, Marburg, A.S. Création, Rasch, Палитра): "
                  "«калькулятор обоев»")
LAMINATE_HINT = ("производитель ламината (Quick-Step, Tarkett, Kronospan, Pergo, Egger): "
                 "калькулятор напольных покрытий")
PAINT_HINT = ("производитель краски (Tikkurila, Dulux, Caparol, Parade): "
              "калькулятор расхода краски")
TILE_HINT = ("производитель плитки / клея (Kerama Marazzi, Ceresit, Litokol, Knauf): "
             "калькулятор плитки")

# rooms: (length m, width m, height m, door w x h, window w x h, wall of openings)
ROOMS = [(4, 3, 2.5), (5, 4, 2.7), (3.5, 3, 2.6), (6, 4.5, 2.8), (3, 2.5, 2.5),
         (4.2, 3.6, 2.5), (5.5, 3.2, 2.7), (3.8, 3.8, 2.6), (7, 4, 2.7), (2.8, 2.4, 2.5)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/reference_cases_todo.csv")
    a = ap.parse_args()
    rows: list[dict[str, str]] = []

    def add(cid: str, calc: str, hint: str, text: str, inputs: dict, unit: str) -> None:  # type: ignore[type-arg]
        r = {c: "" for c in COLUMNS}
        r.update({"id": cid, "calc": calc, "manufacturer_hint": hint, "inputs_text": text,
                  "inputs_json": json.dumps(inputs, ensure_ascii=False), "result_unit": unit})
        rows.append(r)

    # wallpaper: rolls for a room, one door 0.9 x 2.05 and one window 1.4 x 1.4 (for even i)
    for i, (rl, w, h) in enumerate(ROOMS, 1):
        ops = [{"kind": "door", "w": 0.9, "h": 2.05, "wall": 0}]
        if i % 2 == 0:
            ops.append({"kind": "window", "w": 1.4, "h": 1.4, "wall": 1})
        rapport = [0, 0.32, 0.64, 0.0, 0.53][i % 5]
        inputs = {"length": rl, "width": w, "height": h, "openings": ops, "rapport": rapport}
        text = (f"комната {rl}x{w} м, высота {h} м; дверь 0.9x2.05"
                + ("; окно 1.4x1.4" if i % 2 == 0 else "")
                + f"; раппорт {rapport} м; рулон: возьмите из карточки обоев (fill)")
        add(f"ref-wp-{i:02d}", "wallpaper_rolls", WALLPAPER_HINT, text, inputs, "рулонов")

    # laminate: packs for a floor area
    areas = [12, 18.5, 9.6, 27, 14.2, 33, 7.8, 21.4, 16, 42]
    for i, area in enumerate(areas, 1):
        layout = "diagonal" if i % 4 == 0 else "straight"
        add(f"ref-lam-{i:02d}", "laminate_packs", LAMINATE_HINT,
            f"площадь пола {area} м²; укладка {layout}; упаковка (fill) м²",
            {"area": area, "layout": layout}, "упаковок")

    # paint: litres for walls (+ ceiling) in two coats
    paint_areas = [30, 45.5, 22, 60, 38.4, 80, 18, 52, 27.5, 100]
    for i, area in enumerate(paint_areas, 1):
        add(f"ref-pnt-{i:02d}", "paint_liters", PAINT_HINT,
            f"площадь окрашиваемых поверхностей {area} м²; 2 слоя; продукт и его расход (fill)",
            {"area": area, "layers": 2}, "л")

    # tile: packs for an area with a given tile
    tiles = [(10, 300, 300), (14.5, 600, 300), (6.2, 200, 200), (22, 600, 600),
             (8.8, 250, 400), (16, 450, 450), (12, 300, 600), (5.5, 100, 100),
             (30, 800, 800), (9.4, 200, 300)]
    for i, (area, tw, th) in enumerate(tiles, 1):
        layout = "diagonal" if i % 5 == 0 else "straight"
        add(f"ref-til-{i:02d}", "tile_packs", TILE_HINT,
            f"площадь {area} м²; плитка {tw}x{th} мм; укладка {layout}; упаковка (fill) м²",
            {"area": area, "tile_w": tw, "tile_h": th, "layout": layout}, "упаковок")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} строк -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
