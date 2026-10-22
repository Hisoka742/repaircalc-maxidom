"""Data-quality report of the official dump (data/raw/products_final.json) per category.

    python scripts/ingest_dump.py [--catalog data/raw/products_final.json]

Writes docs/DATASET_REPORT.md (summary + focus categories) and eval/dataset_quality.csv (all
categories), and records load time and peak RAM (also appended to out/ingest_dump.json for the
pitch). Numbers are measured here, on the machine that runs the script.
"""
import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.adapters.products_dump import dump_items, merged_characteristics
from maxicalc.ml.extract import extract
from maxicalc.resources import Stage

ROOT = Path(__file__).resolve().parents[1]
# calculator-relevant attribute sets (any of the alternatives counts as "calculable")
READY = {
    "paint": ("краск|эмал", {"spread_m2_per_l", "pack_volume_l"}),
    "wallpaper": ("обои", {"roll_width_m", "roll_length_m"}),
    "laminate/spc": ("ламинат|spc", {"m2_per_pack"}),
    "tile/porcelain": ("плитк|керамогранит", {"m2_per_pack"}),
}
FOCUS = ["Краски для стен и потолков", "Краски фасадные", "Грунтовка", "Обои", "Ламинат 33 класса",
         "Керамогранит напольный", "Плитка настенная для ванной", "Шпатлевки", "Штукатурки",
         "Клеи для плитки керамической и керамогранита",
         "Затирки для плитки керамической и керамогранита"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=str(ROOT / "data/raw/products_final.json"))
    a = ap.parse_args()
    path = Path(a.catalog)
    with Stage("load + normalize") as st_load:
        products, rep = load_catalog(path)
    only_desc: Counter[str] = Counter()
    empty_chars: Counter[str] = Counter()
    for item in dump_items(path):
        cat = next(iter((item.get("categories") or {}).values()), "?")
        _, od = merged_characteristics(item)
        if od:
            only_desc[cat] += 1
        if not item.get("characteristics"):
            empty_chars[cat] += 1
    rows: dict[str, dict[str, int]] = defaultdict(Counter)
    attr_cov: dict[str, Counter[str]] = defaultdict(Counter)
    with Stage("extraction (all products)") as st_ext:
        for p in products:
            c = p.category_path[-1] if p.category_path else "?"
            r = rows[c]
            r["n"] += 1
            r["price"] += p.price is not None and p.price > 0
            r["unit"] += bool(p.unit)
            r["brand"] += bool(p.brand)
            r["chars"] += len(p.characteristics) > 1
            r["desc"] += bool(p.description)
            for k in extract(p).attrs:
                attr_cov[c][k] += 1
    out_csv = ROOT / "eval/dataset_quality.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["category", "n", "price%", "unit%", "brand%", "characteristics%",
                    "desc_only_pairs_products", "no_characteristics", "top_extracted_attrs"])
        for c, r in sorted(rows.items(), key=lambda x: -x[1]["n"]):
            n = r["n"]
            w.writerow([c, n, round(100 * r["price"] / n), round(100 * r["unit"] / n),
                        round(100 * r["brand"] / n), round(100 * r["chars"] / n),
                        only_desc[c], empty_chars[c],
                        ", ".join(f"{k}:{v}" for k, v in attr_cov[c].most_common(6))])
    n = len(products)
    tot = Counter()
    for r in rows.values():
        tot.update(r)
    ready = {}
    for name, (rx, need) in READY.items():
        import re

        pool = [p for p in products if re.search(rx, " ".join(p.category_path).lower())]
        ok = sum(1 for p in pool if need <= set(extract(p).attrs))
        ready[name] = (ok, len(pool))
    md = [
        "# Официальный набор products_final.json: отчёт о качестве (REAL)", "",
        f"- Товаров: **{n}** ({rep.read} прочитано, {rep.skipped} пропущено); категорий-листьев: "
        f"**{len(rows)}** (дерева в файле нет)",
        f"- Загрузка и нормализация: **{st_load.seconds:.1f} с**, пик RAM "
        f"**{st_load.peak_rss_mb / 1024:.2f} ГБ**; извлечение атрибутов по всем: "
        f"**{st_ext.seconds:.1f} с**",
        f"- Цена: {100 * tot['price'] / n:.1f}%; единица: {100 * tot['unit'] / n:.1f}%; бренд: "
        f"{100 * tot['brand'] / n:.1f}%; характеристики: {100 * tot['chars'] / n:.1f}%; "
        f"описание: {100 * tot['desc'] / n:.1f}%",
        f"- Товаров, у которых часть пар «ключ: значение» есть ТОЛЬКО в description: "
        f"{sum(only_desc.values())}; без characteristics вообще: {sum(empty_chars.values())}",
        f"- Замечания загрузчика: {'; '.join(rep.issues[:5]) or 'нет'}", "",
        "## Готовность к расчёту (атрибуты, нужные калькулятору, извлечены из карточки)", "",
        "| группа | готово | всего | доля |", "|---|---|---|---|",
        *[f"| {k} | {ok} | {tot_} | {100 * ok / max(tot_, 1):.0f}% |"
          for k, (ok, tot_) in ready.items()], "",
        "## Ключевые категории", "",
        "| категория | товаров | цена | бренд | извлечено (топ атрибутов) |",
        "|---|---|---|---|---|",
    ]
    for c in FOCUS:
        if c in rows:
            r = rows[c]
            md.append(f"| {c} | {r['n']} | {100 * r['price'] // r['n']}% | "
                      f"{100 * r['brand'] // r['n']}% | "
                      f"{', '.join(f'{k} {v}' for k, v in attr_cov[c].most_common(5))} |")
    md += ["", "Полная таблица по всем категориям: `eval/dataset_quality.csv`.", ""]
    (ROOT / "docs/DATASET_REPORT.md").write_text("\n".join(md), encoding="utf-8")
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out/ingest_dump.json").write_text(json.dumps({
        "products": n, "load_s": st_load.seconds, "load_peak_gb": st_load.peak_rss_mb / 1024,
        "extract_s": st_ext.seconds, "at": time.strftime("%Y-%m-%d")}, indent=2))
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
