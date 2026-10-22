"""Hackathon-day commands.

    uv run python scripts/dayof.py run <catalog.csv|xlsx|json|xml> [--model m.joblib]
                                       [--out data/dayof] [--sample 150]
    uv run python scripts/dayof.py score data/dayof/spot_check.csv [--target 0.95]

`run`   ingest -> label -> calculator readiness -> review queue + spot-check sample + report.md
`score` precision of the auto labels from the human-marked spot-check sample (Wilson interval)
Exit codes: 0 ok, 2 the catalog could not be used (message explains what to fix).
"""
import argparse
import sys
from pathlib import Path

from maxicalc.dayof import run_dayof, score_spot_check


def cmd_run(a: argparse.Namespace) -> int:
    try:
        res = run_dayof(Path(a.catalog), Path(a.out), Path(a.model) if a.model else None,
                        a.sample, a.seed)
    except (ValueError, FileNotFoundError) as e:
        print(f"ОШИБКА: {e}")
        return 2
    n = res.loaded
    print(f"Загружено {n} товаров (пропущено {res.skipped}); "
          f"авто {res.auto} ({100 * res.auto / n:.1f}%), на проверку {res.review}")
    for k, v in res.timings.items():
        print(f"  {k}: {v:.2f} с")
    blocking = [c for c, r in res.readiness.items() if r.blocking]
    if blocking:
        print(f"⚠ Калькуляторы без данных в карточках: {', '.join(blocking)} (см. report.md)")
    print(f"Отчёт: {Path(a.out) / 'report.md'}")
    print("Запуск API на этих данных:")
    print(f"  CATALOG_PATH={a.catalog} " + (f"MODEL_PATH={a.model} " if a.model else "")
          + "uv run uvicorn maxicalc.api.main:app --port 8000")
    return 0


def cmd_score(a: argparse.Namespace) -> int:
    try:
        s = score_spot_check(Path(a.file))
    except ValueError as e:
        print(f"ОШИБКА: {e}")
        return 2
    if s.checked == 0:
        print("Нет отмеченных строк: заполните столбец correct (да/нет).")
        return 2
    print(f"Проверено {s.checked} (не отмечено: {s.unmarked}); верно {s.correct}")
    print(f"Точность авто-разметки: {100 * s.precision:.1f}% "
          f"(95% интервал {100 * s.low:.1f}–{100 * s.high:.1f}%)")
    for calc, (n, ok) in sorted(s.by_calc.items()):
        print(f"  {calc:16s} {ok}/{n}")
    verdict = "ДА" if s.meets(a.target) else "НЕТ"
    print(f"Нижняя граница интервала ≥ {100 * a.target:.0f}%: {verdict}")
    return 0 if s.meets(a.target) else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("catalog")
    r.add_argument("--model")
    r.add_argument("--out", default="data/dayof")
    r.add_argument("--sample", type=int, default=150)
    r.add_argument("--seed", type=int, default=0)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("score")
    s.add_argument("file")
    s.add_argument("--target", type=float, default=0.95)
    s.set_defaults(fn=cmd_score)
    a = ap.parse_args()
    return int(a.fn(a))


if __name__ == "__main__":
    raise SystemExit(main())
