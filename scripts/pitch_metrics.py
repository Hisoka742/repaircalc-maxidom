"""Generate docs/PITCH_METRICS.md from measured outputs.

    uv run python scripts/pitch_metrics.py [--spot data/dayof/spot_check.csv] [--n-auto N]
                                           [--minutes 1.5]

Inputs (all optional except eval): eval/results.json (make eval), data/load_results/*.json
(scripts/load_test.py --out), data/rematch.json (scripts/measure_rematch.py), the human-marked
spot-check CSV from the day-of run. Missing inputs are reported as "не измерено", never faked.
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

from maxicalc.dayof import score_spot_check
from maxicalc.pitch import build_pitch

ROOT = Path(__file__).resolve().parents[1]


def parse_load_text(text: str, label: str, scenario: str) -> dict | None:  # type: ignore[type-arg]
    """Parse the plain-text summary printed by an earlier load_test run (e.g. the soak)."""
    head = re.search(r"target=(\d+) rps x (\d+)s .*?-> (\d+) requests", text)
    lat = re.search(r"p50=([\d.]+) p95=([\d.]+) p99=([\d.]+) max=([\d.]+)", text)
    codes = re.search(r"status codes: (\{.*\})", text)
    if not (head and lat and codes):
        return None
    status = ast.literal_eval(codes.group(1))
    ok = sum(v for k, v in status.items() if isinstance(k, int) and 200 <= k < 300)
    srv = sum(v for k, v in status.items() if isinstance(k, int) and k >= 500)
    n = int(head.group(3))
    return {"label": label, "scenario": scenario, "rps": int(head.group(1)),
            "seconds": int(head.group(2)), "requests": n, "ok": ok, "errors_5xx": srv,
            "other_failures": n - ok - srv, "p50": float(lat.group(1)),
            "p95": float(lat.group(2)), "p99": float(lat.group(3)), "max": float(lat.group(4))}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--spot", help="human-marked spot_check.csv")
    ap.add_argument("--real", default=str(ROOT / "data" / "dayof_real"),
                    help="dayof.py output dir of the REAL (scraped) catalog")
    ap.add_argument("--n-auto", type=int, help="auto-labelled products in the real catalog")
    ap.add_argument("--minutes", type=float, default=1.5,
                    help="ASSUMED minutes of manual labelling per product")
    ap.add_argument("--out", default=str(ROOT / "docs" / "PITCH_METRICS.md"))
    a = ap.parse_args()

    results = ROOT / "eval" / "results.json"
    if not results.exists():
        print("ОШИБКА: нет eval/results.json — сначала `make eval`.")
        return 2
    ev = json.loads(results.read_text(encoding="utf-8"))

    load = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((ROOT / "data" / "load_results").glob("*.json"))]
    soak = ROOT / "data" / "soak_result.txt"
    if soak.exists() and not any("soak" in r["label"].lower() for r in load):
        parsed = parse_load_text(soak.read_text(encoding="utf-8"),
                                 "10-минутный soak, смешанный трафик", "mixed")
        if parsed:
            load.append(parsed)
    rem_path = ROOT / "data" / "rematch.json"
    rematch = json.loads(rem_path.read_text(encoding="utf-8")) if rem_path.exists() else None

    spot = None
    if a.spot:
        if Path(a.spot).exists():
            spot = score_spot_check(Path(a.spot))
        else:
            print(f"предупреждение: {a.spot} не найден — точность на реальном каталоге "
                  "будет «не измерено»")
    n_auto = a.n_auto
    if n_auto is None and spot is not None and rematch:
        n_auto = rematch["auto"]
    real = None
    rdir = Path(a.real)
    if (rdir / "summary.json").exists() and (rdir / "readiness.json").exists():
        real = {"summary": json.loads((rdir / "summary.json").read_text(encoding="utf-8")),
                "readiness": json.loads((rdir / "readiness.json").read_text(encoding="utf-8"))}
    wt_path = ROOT / "eval" / "worktypes_run.json"
    wt = json.loads(wt_path.read_text(encoding="utf-8")) if wt_path.exists() else None
    full_path = ROOT / "eval" / "full_run.json"
    full = json.loads(full_path.read_text(encoding="utf-8")) if full_path.exists() else None
    md = build_pitch(ev, load, rematch, spot, n_auto, a.minutes, real, wt, full)
    Path(a.out).write_text(md, encoding="utf-8")
    # the same measured numbers, for the frontend's Method page (single source of truth)
    fe = ROOT / "frontend" / "src" / "data"
    if fe.exists():
        (fe / "metrics.json").write_text(
            json.dumps({"eval": ev, "load": load, "rematch": rematch}, ensure_ascii=False,
                       indent=2), encoding="utf-8")
    print(f"записано {a.out}: load={len(load)}, rematch={'да' if rematch else 'нет'}, "
          f"spot-check={'да' if spot else 'нет'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
