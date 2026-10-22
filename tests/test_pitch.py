from maxicalc.dayof import SpotCheckScore
from maxicalc.pitch import build_pitch, hours_saved

EVAL = {
    "generated": "2026-10-09T12:00:00Z",
    "golden": {"cases": 29, "verified": 16, "pack_exact": [10, 10], "mape_pct": 0.765,
               "failures": 0},
    "extraction": {"cases": 28, "precision": 1.0, "recall": 0.97},
    "matching": {"items": 3000, "test": 611, "scenarios": [
        {"name": "rules + model, category present", "calc_p_at_1": 0.982, "coverage": 0.944,
         "auto_precision": 0.951, "work_macro_f1": 0.87}]},
    "recommendation": {"queries": 61,
                       "gold": {"ndcg5": 1.0, "violations": 0, "recommended": 297},
                       "pipeline": {"ndcg5": 0.995, "violations": 0, "recommended": 295}},
}
LOAD = [{"label": "soak mixed", "scenario": "mixed", "rps": 200, "seconds": 600,
         "requests": 120000, "ok": 120000, "errors_5xx": 0, "p50": 7.8, "p95": 15.6,
         "p99": 23.5, "max": 294.3}]
REMATCH = {"products": 10000, "seconds": 4.2}


def spot(correct: int, n: int, low: float, high: float) -> SpotCheckScore:
    return SpotCheckScore(n, correct, 0, {}, low, high)


def test_hours_saved_formula() -> None:
    assert hours_saved(9000, 1.5) == 225.0
    assert hours_saved(0, 1.5) == 0.0


def test_pitch_contains_measured_numbers() -> None:
    md = build_pitch(EVAL, LOAD, REMATCH, None)
    assert "29" in md and "16" in md and "0.765" in md
    assert "10/10" in md
    assert "120000" in md or "120 000" in md
    assert "15.6" in md and "23.5" in md
    assert "10000" in md and "4.2" in md


def test_synthetic_figures_are_labelled_synthetic() -> None:
    md = build_pitch(EVAL, LOAD, REMATCH, None)
    assert md.count("СИНТЕТИЧЕСК") >= 3          # extraction, matching, recommendation, load


def test_without_a_spot_check_precision_is_explicitly_not_measured() -> None:
    md = build_pitch(EVAL, LOAD, REMATCH, None)
    assert "не измерено" in md.lower()
    assert "95% точности" not in md              # no claim without evidence


def test_precision_claim_only_when_lower_bound_clears_target() -> None:
    good = build_pitch(EVAL, LOAD, REMATCH, spot(148, 150, 0.953, 0.996))
    assert "95.3" in good and "99.6" in good and "98.7" in good
    assert "достигнут" in good.lower()
    bad = build_pitch(EVAL, LOAD, REMATCH, spot(138, 150, 0.865, 0.954))
    assert "92.0" in bad and "не достигнут" in bad.lower()


def test_hours_saved_states_its_assumption() -> None:
    md = build_pitch(EVAL, LOAD, REMATCH, None, n_auto=9000, minutes_per_label=1.5)
    assert "225" in md and "допущение" in md.lower() and "1.5" in md


def test_hours_saved_uses_measured_lower_bound_when_available() -> None:
    md = build_pitch(EVAL, LOAD, REMATCH, spot(148, 150, 0.953, 0.996),
                     n_auto=9000, minutes_per_label=1.5)
    # only correctly labelled items save work: 9000 * 0.953 * 1.5 / 60
    assert f"{9000 * 0.953 * 1.5 / 60:.0f}" in md


def test_limitations_section_is_always_present() -> None:
    md = build_pitch(EVAL, LOAD, REMATCH, None)
    assert "Что не доказано" in md
    assert "ставки работ" in md.lower()


def test_failures_are_not_hidden() -> None:
    bad_eval = {**EVAL, "golden": {**EVAL["golden"], "failures": 2}}
    md = build_pitch(bad_eval, LOAD, REMATCH, None)
    assert "расхождени" in md.lower()


def test_parse_load_text_roundtrip() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "pitch_metrics", Path(__file__).resolve().parents[1] / "scripts" / "pitch_metrics.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = ("scenario=mixed target=200 rps x 600s (4 client procs) -> 120000 requests, "
            "achieved 200 rps\nlatency ms: p50=7.8 p95=15.6 p99=23.5 max=294.3\n"
            "status codes: {200: 120000}\n")
    r = mod.parse_load_text(text, "soak", "mixed")
    assert (r["rps"], r["seconds"], r["requests"], r["ok"], r["errors_5xx"]) == (
        200, 600, 120000, 120000, 0)
    assert (r["p50"], r["p95"], r["p99"], r["max"]) == (7.8, 15.6, 23.5, 294.3)
    assert mod.parse_load_text("garbage", "x", "mixed") is None
    bad = text.replace("{200: 120000}", "{200: 119000, 500: 1000}")
    assert mod.parse_load_text(bad, "x", "mixed")["errors_5xx"] == 1000


def test_the_four_case_metrics_are_in_section_zero() -> None:
    ev = {**EVAL, "golden": {**EVAL["golden"], "mae_packs": 0.0, "max_pack_error": 0.0}}
    md = build_pitch(ev, LOAD, REMATCH, None)
    head = md.split("## 1.")[0]
    for needle in ("Качество матчинга", "MAE по количеству", "авто-привязанных",
                   "Время формирования сметы", "Клики"):
        assert needle in head, needle
    assert "СИНТЕТИКА" in head and "не получены" in head       # nothing presented as real
    assert "95.1" in head                                      # auto share meets the 95% target


def test_without_a_mae_the_row_says_not_measured() -> None:
    md = build_pitch(EVAL, LOAD, REMATCH, None)
    assert "MAE по количеству к эталону | не измерено" in md
