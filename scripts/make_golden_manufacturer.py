"""Write tests/golden/golden_manufacturer.yaml: cases whose rates are the figures printed in
manufacturers' technical data sheets (URL + quote on every case). Expected values are plain
Decimal arithmetic here, independent of the engine. Run scripts/fetch_references.py to get the
same sheets and compare the quoted lines.

    python scripts/make_golden_manufacturer.py
"""
import math
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import yaml

H = "https://datasheets.tdx.henkel.com/"
OUT = Path(__file__).resolve().parents[1] / "tests" / "golden" / "golden_manufacturer.yaml"
cases: list[dict[str, Any]] = []


def add(cid: str, calc: str, kind: str, inputs: dict[str, Any], expected: Any, url: str,
        quote: str, verified: bool = True, note: str | None = None) -> None:
    c: dict[str, Any] = {
        "id": cid, "calc": calc, "kind": kind, "inputs": inputs,
        "expected": int(expected) if kind == "pack" else float(expected),
        "tolerance": 0, "source": "manufacturer-sheet", "verified": verified,
        "source_url": url, "quote": quote}
    if note:
        c["note"] = note
    cases.append(c)


# --- Ceresit CM 11 PLUS: adhesive kg/m2 by tile side (cm) -------------------------------------
U = H + "CERESIT-CM-11-ru_KZ.pdf"
rows = [(5, 3, "2.0"), (10, 4, "2.5"), (15, 6, "3.0"), (25, 8, "3.7"), (30, 10, "4.2"),
        (40, 12, "5.2")]
for n, (s, t, r) in enumerate(rows, 1):
    add(f"mf-cm11-{n:02d}", "adhesive_kg", "continuous",
        {"area": 10, "tile_w": s * 10, "tile_h": s * 10, "table": "cm11_plus"},
        D(10) * D(r), U, f"до {s} см: зуб {t} мм, расход ~ {r} кг/м² (CM 11 PLUS)")
add("mf-cm11-07", "adhesive_kg", "continuous",
    {"area": 7.5, "tile_w": 200, "tile_h": 100, "table": "cm11_plus"}, D("7.5") * D("3.7"), U,
    "до 25 см: зуб 8 мм, расход ~ 3,7 кг/м² (CM 11 PLUS)",
    note="плитка 20×10 см: большая сторона 20 см попадает в строку «до 25»")
add("mf-cm11-08", "adhesive_kg", "continuous",
    {"area": 13.2, "tile_w": 300, "tile_h": 300, "table": "cm11_plus"}, D("13.2") * D("4.2"), U,
    "до 30 см: зуб 10 мм, расход ~ 4,2 кг/м² (CM 11 PLUS)")

# --- Ceresit CE 40 Aquastatic: grout kg per m2 of cladding ---------------------------------------
U = H + "CERESIT-CE-40-ru_KZ.pdf"
rows2 = [((5, 5), 2, "0.6"), ((5, 5), 3, "0.7"), ((10, 10), 2, "0.4"), ((10, 20), 3, "0.4"),
         ((15, 15), 3, "0.4"), ((20, 20), 5, "0.5")]
for n, ((w, h), j, r) in enumerate(rows2, 1):
    add(f"mf-ce40-{n:02d}", "grout_table_kg", "continuous",
        {"area": 10, "tile_w": w * 10, "tile_h": h * 10, "joint": j}, D(10) * D(r), U,
        f"плитка {w}х{h} см, шов {j} мм: около {r} кг/м² облицовки")
add("mf-ce40-07", "grout_table_kg", "continuous",
    {"area": 4.5, "tile_w": 100, "tile_h": 100, "joint": 2}, D("4.5") * D("0.4"), U,
    "плитка 10х10 см, шов 2 мм: около 0,4 кг/м² облицовки")
add("mf-ce40-08", "grout_table_kg", "continuous",
    {"area": 22, "tile_w": 200, "tile_h": 200, "joint": 5}, D(22) * D("0.5"), U,
    "плитка 20х20 см, шов 5 мм: около 0,5 кг/м² облицовки")

# --- Ceresit CR 65: waterproofing kg/m2 by operating condition --------------------------------
U = H + "CERESIT-CR-65-ru_KZ.pdf"
cond = [("high_humidity", "Высокая влажность: 2,0 - 2,5 мм ~ 3,5 кг/м²", "3.5"),
        ("water_no_pressure", "Вода без давления: 2,5 - 3,5 мм ~ 4,5 кг/м²", "4.5"),
        ("water_pressure", "Вода под давлением до 0,05 МПа: 3,0 - 4,0 мм ~ 6,0 кг/м²", "6.0"),
        ("max_thickness", "Максимальная толщина слоя: 5,0 мм ~ 8,0 кг/м²", "8.0")]
n = 0
for a in ("10", "6.2"):
    for key, quote, r in cond:
        n += 1
        add(f"mf-cr65-{n:02d}", "waterproofing_kg", "continuous",
            {"area": float(a), "condition": key}, D(a) * D(r), U, quote)

# --- Ceresit CN 68: self-levelling screed, 1.8 kg/m2/mm, bags 25 kg -------------------------------
U = H + "CERESIT-CN-68-ru_BY.pdf"
Q = "Расход сухой смеси около 1,8 кг / м2 / мм; Мешки 25 кг"
for n, (a, t) in enumerate([("10", 3), ("10", 5), ("12", 10), ("7.5", 4), ("20", 5),
                            ("30", 8)], 1):
    add(f"mf-cn68-{n:02d}", "layer_kg", "continuous",
        {"area": float(a), "thickness_mm": t, "rate": 1.8}, D(a) * t * D("1.8"), U, Q)
for n, (a, t) in enumerate([("20", 5), ("45", 7)], 7):
    kg = D(a) * t * D("1.8")
    add(f"mf-cn68-{n:02d}", "putty_bags", "pack",
        {"area": float(a), "thickness_mm": t, "rate": 1.8, "bag_kg": 25},
        math.ceil(kg / 25), U, Q)

# --- Ceresit CL 51: waterproofing mastic 1.4 kg/m2 (2 coats), buckets 5 and 15 kg -----------------
U = H + "CERESIT-CL-51-ru_KZ.pdf"
Q = "Расход CL 51: около 1,4 кг/м2 (2 слоя); поставляется в ведрах по 5 и 15 кг"
for n, (a, b) in enumerate([(10, 5), (25, 5), (4, 5), (3, 5), (50, 15), (12, 15), (6, 15),
                            (30, 15)], 1):
    kg = D(a) * D("1.4")
    add(f"mf-cl51-{n:02d}", "putty_bags", "pack",
        {"area": a, "thickness_mm": 1, "rate": 1.4, "bag_kg": b}, math.ceil(kg / b), U, Q,
        note="расход на м² (кг) задан как толщина 1 × 1,4; пакуется по весу ведра")

# --- Ceresit CT 17 PROFI: primer 0.1-0.2 l/m2, containers 5, 10, 30 l -------------------------
U = H + "CERESIT-CT-17-ru_KZ.pdf"
Q = "Расход CT 17 PROFI: 0,1 – 0,2 л/м² при однократном нанесении; ёмкости 5, 10 и 30 л"
for n, (a, r, c) in enumerate([(40, "0.1", 5), (40, "0.2", 5), (100, "0.1", 10),
                               (100, "0.2", 10), (250, "0.2", 30), (60, "0.15", 5),
                               (35, "0.2", 5), (300, "0.1", 30)], 1):
    v = D(a) * D(r)
    add(f"mf-ct17-{n:02d}", "primer_packs", "pack",
        {"area": a, "l_per_m2": float(r), "can_l": c, "layers": 1}, math.ceil(v / c), U, Q)

# --- Tikkurila Prof Euro 7: coverage m2/l, cans 0.9 2.7 5 9 18 l ---------------------
U = "https://tikkurila.com/sites/default/files/prof-euro-7-en-pds-tikkurila-1655905744.pdf"
Q = "Coverage 10-14 m²/l on smooth non-absorbent surface; 7-9 m²/l on rough absorbent surface"
for n, (a, s, c) in enumerate([(60, 14, "9"), (60, 10, "9"), (60, 7, "9"), (60, 9, "9"),
                               (100, 14, "18"), (100, 7, "18"), (25, 10, "5"),
                               (18, 9, "2.7")], 1):
    v = D(a) / D(s)
    add(f"mf-tikk-{n:02d}", "paint_packs", "pack",
        {"area": a, "spread": s, "layers": 1, "can_l": float(c)},
        math.ceil(v / D(c)), U, Q + " (на один слой)")

# --- Knauf Rotband: 8.5 kg/m2 (recommended thickness 10 mm), bags 10/25/30 kg ---------------------
U = "https://knauf.by/upload/iblock/dac/Knauf_IL_Rotband_07_06_19_preview_v4.pdf"
Q = "КНАУФ-Ротбанд кг 8,5*; средняя толщина слоя 10 мм; мешки 10, 25 и 30 кг"
for n, (a, t, b) in enumerate([(10, 10, 30), (20, 10, 30), (5, 10, 25), (12, 15, 30),
                               (40, 10, 30), (25, 5, 25), (60, 12, 30), (8, 20, 10)], 1):
    kg = D(a) * t * D("0.85")
    add(f"mf-rotband-{n:02d}", "putty_bags", "pack",
        {"area": a, "thickness_mm": t, "rate": 0.85, "bag_kg": b}, math.ceil(kg / b), U, Q,
        verified=False,
        note="8,5 кг/м² при 10 мм: сноска «*» листа не извлечена, основа не подтверждена")

OUT.write_text(
    "# Generated by scripts/make_golden_manufacturer.py - do not edit by hand.\n"
    + yaml.safe_dump({"cases": cases}, allow_unicode=True, sort_keys=False), encoding="utf-8")
print(len(cases), "cases ->", OUT)
