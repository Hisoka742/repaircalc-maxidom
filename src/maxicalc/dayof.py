"""Day-of pipeline: organiser catalog -> labelled catalog + readiness + human spot-check.

    uv run python scripts/dayof.py run <catalog> [--model m.joblib] [--out data/dayof]
    uv run python scripts/dayof.py score data/dayof/spot_check.csv

Honesty design: there are no gold labels for an unseen catalog, so thresholds cannot be
calibrated on it. By default only the rules label products (high precision by construction).
Precision is then MEASURED, not assumed: a random sample of auto-accepted items is exported,
a human marks each right/wrong, and `score` reports precision with a Wilson interval.
"""
import csv
import io
import json
import math
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from maxicalc.catalog.adapters import load_catalog, peek_headers
from maxicalc.catalog.adapters.base import map_headers
from maxicalc.catalog.adapters.tabular import _decode
from maxicalc.catalog.schema import Product
from maxicalc.ml.classify import MatchModel
from maxicalc.ml.extract import extract
from maxicalc.ml.match import Matcher, MatchResult
from maxicalc.ml.readiness import Readiness, readiness_report
from maxicalc.recommend.build import to_entries

MAX_SKIPPED_SHARE = 0.5
YES = {"да", "yes", "y", "1", "true", "верно", "+"}
NO = {"нет", "no", "n", "0", "false", "неверно", "-"}


@dataclass
class DayOfResult:
    out_dir: Path
    loaded: int
    skipped: int
    issues_total: int
    auto: int
    review: int
    timings: dict[str, float] = field(default_factory=dict)
    readiness: dict[str, Readiness] = field(default_factory=dict)
    model_used: bool = False
    priced: int = 0


def _check_headers(path: Path) -> tuple[dict[str, str], list[str]]:
    headers = peek_headers(path)
    if not headers:
        return {}, []
    mapped, unmapped = map_headers(headers)
    fields = set(mapped.values())
    if "sku" not in fields or "name" not in fields:
        raise ValueError(
            "Не найдены столбцы артикула (sku) и/или наименования (name). "
            f"Найденные заголовки: {headers}. Добавьте их синонимы в ALIASES "
            "(src/maxicalc/catalog/adapters/base.py) и повторите.")
    return mapped, unmapped


def _row(p: Product, r: MatchResult) -> dict[str, object]:
    attrs = {k: str(a.value) for k, a in extract(p).attrs.items()}
    c = r.calc_template
    return {
        "sku": p.sku, "name": p.name, "category": " > ".join(p.category_path),
        "status": r.status,
        "calc_template": c.label if c else None, "calc_accepted": bool(c and c.accepted),
        "confidence": round(c.confidence, 4) if c else 0.0,
        "work_categories": sorted(r.accepted("work_categories")),
        "room_types": sorted(r.accepted("room_types")),
        "properties": sorted(r.accepted("properties")),
        "reason": c.reason if c else "", "reasons": r.reasons, "attrs": attrs,
    }


def run_dayof(
    catalog: Path, out_dir: Path, model_path: Path | None = None,
    sample_size: int = 150, seed: int = 0,
) -> DayOfResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    t = time.perf_counter()
    mapped, unmapped = _check_headers(catalog)
    products, rep = load_catalog(catalog)
    timings["ingest"] = time.perf_counter() - t
    if rep.loaded == 0:
        raise ValueError(f"Каталог пуст или не распознан: загружено 0 из {rep.read} строк. "
                         f"Проблемы: {rep.issues[:5]}")
    if rep.skipped / max(rep.read, 1) > MAX_SKIPPED_SHARE:
        raise ValueError(f"Пропущено {rep.skipped} из {rep.read} строк — вероятно, неверно "
                         f"определены столбцы. Проблемы: {rep.issues[:5]}")

    t = time.perf_counter()
    model = MatchModel.load(model_path) if model_path else None
    results = Matcher(model).match(products)
    rows = [_row(p, r) for p, r in zip(products, results, strict=True)]
    timings["extract+match"] = time.perf_counter() - t

    t = time.perf_counter()
    entries = to_entries(products, results)
    ready = readiness_report(entries)
    timings["readiness"] = time.perf_counter() - t

    with (out_dir / "matched.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    review = sorted((r for r in rows if r["status"] == "review"),
                    key=lambda r: (float(r["confidence"]), str(r["sku"])))  # type: ignore[arg-type]
    with (out_dir / "review_queue.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "name", "category", "suggested_calc", "confidence", "reasons"])
        for r in review:
            w.writerow([r["sku"], r["name"], r["category"], r["calc_template"] or "",
                        r["confidence"], "; ".join(r["reasons"])])  # type: ignore[arg-type]

    auto = sorted((r for r in rows if r["status"] == "auto"), key=lambda r: str(r["sku"]))
    sample = sorted(random.Random(seed).sample(auto, min(sample_size, len(auto))),
                    key=lambda r: str(r["sku"]))
    with (out_dir / "spot_check.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "name", "category", "calc_template", "work_categories", "reason",
                    "correct"])
        for r in sample:
            w.writerow([r["sku"], r["name"], r["category"], r["calc_template"],
                        ",".join(r["work_categories"]), r["reason"], ""])  # type: ignore[arg-type]

    priced_n = sum(1 for p in products if p.price is not None)
    (out_dir / "summary.json").write_text(json.dumps(
        {"products": len(products), "auto": len(auto), "review": len(review), "priced": priced_n,
         "by_calc": dict(Counter(str(r["calc_template"]) for r in auto))},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "readiness.json").write_text(json.dumps(
        {c: {"total": x.total, "ready": x.ready, "share": round(x.share, 4),
             "blocking": x.blocking, "top_missing": x.top_missing}
         for c, x in ready.items()}, ensure_ascii=False, indent=2), encoding="utf-8")

    res = DayOfResult(out_dir, rep.loaded, rep.skipped, rep.issues_total, len(auto), len(review),
                      timings, ready, model is not None,
                      sum(p.price is not None for p in products))
    (out_dir / "report.md").write_text(
        _report(res, rep.issues, mapped, unmapped, rows, len(sample)), encoding="utf-8")
    return res


def _report(
    res: DayOfResult, issues: list[str], mapped: dict[str, str], unmapped: list[str],
    rows: list[dict[str, object]], sample_n: int,
) -> str:
    n = res.loaded
    mode = ("правила + модель (НЕ откалибрована на этом каталоге)" if res.model_used
            else "только правила (высокая точность, ниже охват)")
    by_calc = Counter(str(r["calc_template"]) for r in rows if r["status"] == "auto")
    L = ["# Отчёт: загрузка каталога организаторов", "",
         "## Загрузка каталога", "",
         f"- Загружено товаров: {res.loaded}, пропущено строк: {res.skipped}, "
         f"замечаний: {res.issues_total}",
         f"- Распознанные столбцы: {mapped or '(формат с фиксированной схемой)'}",
         f"- Нераспознанные столбцы (сохранены как характеристики): {unmapped or '—'}",
         f"- Товаров с ценой: {res.priced} из {res.loaded}"]
    if res.priced < res.loaded * 0.5:
        L += ["", f"⚠ Цены распознаны только у {res.priced} из {res.loaded} товаров: стоимость "
              "смет будет неверной. Проверьте столбцы выше — вероятно, столбец цены назван "
              "иначе (добавьте в ALIASES, src/maxicalc/catalog/adapters/base.py)."]
    L += [f"  - {i}" for i in issues[:10]]
    L += ["", "## Разметка", "",
          f"- Режим: {mode}",
          f"- Размечено автоматически: {res.auto} ({100 * res.auto / n:.1f}%), "
          f"на ручную проверку: {res.review} ({100 * res.review / n:.1f}%)",
          "- По типам калькулятора (авто): "
          + ", ".join(f"{k}: {v}" for k, v in by_calc.most_common()),
          "", "## Готовность калькуляторов", "",
          "Доля товаров, у которых в карточке есть все данные для расчёта количества.", "",
          "| тип | товаров | готово | доля | чего не хватает |", "|---|---|---|---|---|"]
    for calc, r in sorted(res.readiness.items()):
        miss = ", ".join(f"{a} ({c})" for a, c in r.top_missing) or "—"
        flag = " ⚠" if r.blocking else ""
        L.append(f"| {calc}{flag} | {r.total} | {r.ready} | {100 * r.share:.0f}% | {miss} |")
    blocking = [c for c, r in res.readiness.items() if r.blocking]
    if blocking:
        L += ["", f"⚠ Для типов {', '.join(blocking)} большинство карточек без данных для "
              "расчёта: корзины по ним будут в основном предупреждениями. Найдите, в каком "
              "поле каталога лежит расход/фасовка, и добавьте его разбор."]
    L += ["", "## Контрольная выборка", "",
          f"- Файл `spot_check.csv`: {sample_n} случайных автоматически размеченных товаров.",
          "- Отметьте в столбце `correct` «да»/«нет» (≈10 минут), затем:",
          "  `uv run python scripts/dayof.py score <out>/spot_check.csv` — точность авто-разметки "
          "с доверительным интервалом.", "", "## Время шагов", ""]
    L += [f"- {k}: {v:.2f} с" for k, v in res.timings.items()]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------- spot-check scoring
def wilson_interval(correct: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion; (0, 1) when nothing was checked."""
    if n == 0:
        return 0.0, 1.0
    p = correct / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


@dataclass
class SpotCheckScore:
    checked: int
    correct: int
    unmarked: int
    by_calc: dict[str, tuple[int, int]]     # calc -> (checked, correct)
    low: float
    high: float

    @property
    def precision(self) -> float:
        return self.correct / self.checked if self.checked else 0.0

    def meets(self, target: float = 0.95) -> bool:
        """True only if the interval's LOWER bound clears the target (a sample, not a census)."""
        return self.checked > 0 and self.low >= target


def score_spot_check(path: Path) -> SpotCheckScore:
    text = _decode(path.read_bytes())
    head = text.split("\n", 1)[0]
    delim = max(";,\t|", key=head.count)
    checked = correct = unmarked = 0
    by_calc: dict[str, list[int]] = {}
    for row in csv.DictReader(io.StringIO(text), delimiter=delim):
        mark = (row.get("correct") or "").strip().lower()
        if not mark:
            unmarked += 1
            continue
        if mark in YES:
            ok = True
        elif mark in NO:
            ok = False
        else:
            raise ValueError(f"Не удалось прочитать отметку «{mark}» для SKU {row.get('sku')}: "
                             "используйте да/нет")
        checked += 1
        correct += ok
        c = by_calc.setdefault(row.get("calc_template") or "?", [0, 0])
        c[0] += 1
        c[1] += ok
    lo, hi = wilson_interval(correct, checked)
    return SpotCheckScore(checked, correct, unmarked,
                          {k: (v[0], v[1]) for k, v in by_calc.items()}, lo, hi)
