"""Full run on the whole official dump: ingest -> extraction -> matching -> readiness, timed.

    python scripts/full_run.py [--catalog data/raw/products_final.json]
        [--model data/models/worktypes.joblib] [--out out/full_run.json]

Every stage is wrapped in resources.Stage (wall time, peak RSS, CPU%). The numbers are written to
out/full_run.json and docs/FULL_RUN.md; scripts/pitch_metrics.py quotes them in PITCH_METRICS.md.
Run on the laptop that will be used on stage: the numbers describe THAT machine.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import joblib

from maxicalc.catalog.adapters import load_catalog
from maxicalc.ml.category_baseline import table as category_table
from maxicalc.ml.extract import extract
from maxicalc.ml.match import Matcher
from maxicalc.ml.readiness import readiness_report
from maxicalc.ml.worktypes import WorkMatcher
from maxicalc.recommend.build import to_entries
from maxicalc.recommend.inferred import effective_entry
from maxicalc.resources import Stage, machine
from maxicalc.service.requirements import missing_attrs

ROOT = Path(__file__).resolve().parents[1]
# main interior-calculator categories (leaf of the dump) -> the calculator type expected for them
FOCUS = {"Краски для стен и потолков": "paint", "Грунтовка": "primer", "Обои": "wallpaper",
         "Ламинат 33 класса": "laminate", "Ламинат 32 класса": "laminate",
         "Керамогранит напольный": "tile", "Плитка настенная для ванной": "tile",
         "Шпатлевки сухие гипсовые": "putty", "Шпатлевки готовые": "putty"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", default=str(ROOT / "data/raw/products_final.json"))
    ap.add_argument("--model", default=str(ROOT / "data/models/worktypes.joblib"))
    ap.add_argument("--out", default=str(ROOT / "out/full_run.json"))
    a = ap.parse_args()
    stages: dict[str, dict[str, float]] = {}

    def record(st: Stage, n: int) -> None:
        st.items = n
        stages[st.name] = {"seconds": round(st.seconds, 2), "peak_rss_mb": round(st.peak_rss_mb),
                           "cpu_percent": round(st.cpu_percent), "items": n,
                           "per_1000_s": round(st.seconds / max(n, 1) * 1000, 3)}
        print(f"{st.name}: {st.seconds:.1f} s, peak {st.peak_rss_mb:.0f} MB, "
              f"{st.seconds / max(n, 1) * 1000:.2f} s per 1000", flush=True)

    t0 = time.perf_counter()
    with Stage("1 ingest + normalize") as st:
        products, rep = load_catalog(a.catalog)
    record(st, len(products))
    n = len(products)
    with Stage("2 attribute extraction (regex)") as st:
        extracted = [extract(p) for p in products]
    record(st, n)
    with Stage("3 calculator-type matching (rules)") as st:
        results = Matcher(None).match(products)
    record(st, n)
    model = joblib.load(a.model) if Path(a.model).exists() else None
    with Stage("4 work-type matching (rules + model)") as st:
        preds = WorkMatcher(model).predict(products)
    record(st, n)
    with Stage("5 entries + calculator readiness") as st:
        entries = to_entries(products, results)
        ready = readiness_report(entries)
    record(st, n)
    total = time.perf_counter() - t0
    focus: dict[str, dict[str, int | str]] = {}
    for e in entries:
        leaf = e.product.category_path[-1] if e.product.category_path else ""
        want = FOCUS.get(leaf)
        if want is None:
            continue
        f = focus.setdefault(leaf, {"calc": want, "total": 0, "typed": 0, "ready": 0})
        f["total"] += 1
        if e.calc == want:
            f["typed"] += 1
            f["ready"] += not missing_attrs(want, effective_entry(e)[0].attrs)

    work_count = Counter(len(p.works) for p in preds)
    cat = category_table()
    scope = [(cat.get(p.characteristics.get("category_id", "")) or None) for p in products]
    in_scope = [i for i, r in enumerate(scope) if r is not None and r.scope == "repair"]
    out = {
        "products": n, "skipped": rep.skipped, "total_seconds": round(total, 1),
        "machine": machine(), "stages": stages,
        "with_work_types": sum(1 for p in preds if p.works),
        "review_queue": sum(1 for p in preds if p.review),
        "works_per_product": dict(sorted(work_count.items())),
        "attrs_extracted_products": sum(1 for e in extracted if e.attrs),
        "readiness": {c: {"total": r.total, "ready": r.ready, "share": round(r.share, 3)}
                      for c, r in sorted(ready.items())},
        "in_scope_products": len(in_scope),
        "out_of_scope_products": n - len(in_scope),
        "in_scope_with_work_types": sum(1 for i in in_scope if preds[i].works),
        "calc_auto": sum(1 for r in results if r.status == "auto"),
        "calc_review_in_scope": sum(1 for i in in_scope if results[i].status == "review"),
        "calc_auto_in_scope": sum(1 for i in in_scope if results[i].status == "auto"),
        "focus_readiness": focus,
        "date": time.strftime("%Y-%m-%d"),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    m = out["machine"]
    md = [
        "# Полный прогон на официальном наборе (REAL, измерено)", "",
        f"- Товаров: **{n}**, пропущено: {rep.skipped}; общее время **{total:.0f} с** "
        f"({total / 60:.1f} мин)",
        f"- Машина: {m['cpu']}, ядер {m['cores_physical']}/{m['cores_logical']}, "
        f"RAM {m['ram_gb']} ГБ, GPU: {m['gpu'] or 'нет (CPU)'}",
        f"- Виды работ найдены у **{out['with_work_types']}** товаров "
        f"({100 * out['with_work_types'] / n:.1f}%), очередь проверки: {out['review_queue']}",
        f"- Ремонтных категорий (карта категорий): {out['in_scope_products']} товаров, "
        f"остальные {out['out_of_scope_products']} — не ремонт (метка «нет работ»)",
        f"- Среди ремонтных: виды работ у {out['in_scope_with_work_types']} "
        f"({100 * out['in_scope_with_work_types'] / max(out['in_scope_products'], 1):.1f}%); "
        f"тип калькулятора авто {out['calc_auto_in_scope']}, на проверку "
        f"{out['calc_review_in_scope']}", "",
        "| шаг | секунд | пик RAM, МБ | с на 1000 товаров |", "|---|---|---|---|",
        *[f"| {k} | {v['seconds']} | {v['peak_rss_mb']} | {v['per_1000_s']} |"
          for k, v in stages.items()], "",
        "## Готовность основных категорий (карточка + извлечение + задокументированные умолчания)",
        "", "| категория | товаров | тип калькулятора определён | готово к расчёту |",
        "|---|---|---|---|",
        *[f"| {k} | {v['total']} | {v['typed']} | {v['ready']} |" for k, v in focus.items()], "",
        "## Готовность калькуляторов по всем товарам типа (включая аксессуары, ошибочно "
        "отнесённые к типу)", "",
        "| калькулятор | товаров | готово | доля |", "|---|---|---|---|",
        *[f"| {c} | {r['total']} | {r['ready']} | {100 * r['share']:.0f}% |"
          for c, r in out["readiness"].items()], ""]
    (ROOT / "docs/FULL_RUN.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
