import csv
import json
from pathlib import Path

import pytest

from maxicalc.catalog.adapters.base import map_headers
from maxicalc.dayof import SpotCheckScore, run_dayof, score_spot_check, wilson_interval
from maxicalc.ml.synth import generate

CARD = {"paint": "Расход 10 м2/л", "primer": "Расход 0,15 л/м2"}


def write_catalog(path: Path, n: int = 400) -> None:
    items = generate(n, seed=5)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["sku", "name", "category", "brand", "price", "description"])
        for it in items:
            p = it.product
            fam = it.group.split(":")[0]
            w.writerow([p.sku, p.name, " > ".join(p.category_path), p.brand or "", 500,
                        CARD.get(fam.replace("paint_wall", "paint"), "")])


# ---------- header diagnostics ----------
def test_map_headers_reports_mapped_and_unmapped() -> None:
    mapped, unmapped = map_headers(["Артикул", "Наименование", "Цена", "Вес, кг", "Раздел"])
    assert mapped == {"Артикул": "sku", "Наименование": "name", "Цена": "price",
                      "Раздел": "category"}
    assert unmapped == ["Вес, кг"]


# ---------- wilson interval ----------
def test_wilson_interval_known_value() -> None:
    lo, hi = wilson_interval(95, 100)
    assert lo == pytest.approx(0.8883, abs=1e-3) and hi == pytest.approx(0.9785, abs=1e-3)
    assert wilson_interval(0, 0) == (0.0, 1.0)
    lo, hi = wilson_interval(100, 100)
    assert hi == pytest.approx(1.0) and lo < 1.0     # never claim certainty from a sample


# ---------- the pipeline ----------
def test_run_dayof_produces_all_artifacts(tmp_path: Path) -> None:
    cat = tmp_path / "organiser.csv"
    write_catalog(cat)
    out = tmp_path / "out"
    res = run_dayof(cat, out, sample_size=50, seed=1)
    assert res.loaded == 400 and res.skipped == 0
    for name in ("matched.jsonl", "review_queue.csv", "spot_check.csv", "readiness.json",
                 "report.md"):
        assert (out / name).exists(), name
    assert set(res.timings) >= {"ingest", "extract+match", "readiness"}
    report = (out / "report.md").read_text(encoding="utf-8")
    for section in ("Загрузка каталога", "Разметка", "Готовность калькуляторов",
                    "Контрольная выборка"):
        assert section in report
    rows = [json.loads(line) for line in (out / "matched.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert len(rows) == 400 and {"sku", "status", "calc_template", "attrs"} <= set(rows[0])


def test_spot_check_sample_is_only_auto_accepted_items(tmp_path: Path) -> None:
    cat = tmp_path / "c.csv"
    write_catalog(cat)
    out = tmp_path / "o"
    run_dayof(cat, out, sample_size=40, seed=2)
    matched = {r["sku"]: r for r in map(json.loads, (out / "matched.jsonl").read_text(
        encoding="utf-8").splitlines())}
    with (out / "spot_check.csv").open(encoding="utf-8") as f:
        sample = list(csv.DictReader(f))
    assert 0 < len(sample) <= 40
    assert all(matched[r["sku"]]["status"] == "auto" for r in sample)
    assert "correct" in sample[0] and all(r["correct"] == "" for r in sample)   # for the human
    # review queue holds exactly the review items, least confident first
    with (out / "review_queue.csv").open(encoding="utf-8") as f:
        queue = list(csv.DictReader(f))
    assert {r["sku"] for r in queue} == {s for s, r in matched.items() if r["status"] == "review"}


def test_run_dayof_is_deterministic(tmp_path: Path) -> None:
    cat = tmp_path / "c.csv"
    write_catalog(cat)
    run_dayof(cat, tmp_path / "a", sample_size=30, seed=3)
    run_dayof(cat, tmp_path / "b", sample_size=30, seed=3)
    assert (tmp_path / "a" / "spot_check.csv").read_text(encoding="utf-8") == (
        tmp_path / "b" / "spot_check.csv").read_text(encoding="utf-8")


def test_unrecognised_columns_abort_with_a_clear_message(tmp_path: Path) -> None:
    f = tmp_path / "weird.csv"
    f.write_text("Номенклатура;Группа;Стоимость\nабв;x;10\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        run_dayof(f, tmp_path / "o")
    msg = str(e.value)
    # shows what was found and what is needed
    assert "Номенклатура" in msg and "артикул" in msg.lower()


def test_empty_or_garbage_catalog_aborts(tmp_path: Path) -> None:
    f = tmp_path / "empty.csv"
    f.write_text("sku;name\n", encoding="utf-8")
    with pytest.raises(ValueError, match="пуст"):
        run_dayof(f, tmp_path / "o")


# ---------- scoring the human spot check ----------
def test_score_spot_check(tmp_path: Path) -> None:
    f = tmp_path / "spot.csv"
    rows = [("a", "paint", "да")] * 18 + [("b", "tile", "нет")] * 2 + [("c", "tile", "1")] * 10 \
        + [("d", "grout", "")]                                      # unmarked -> not counted
    with f.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sku", "name", "calc_template", "work_categories", "correct"])
        for i, (_, calc, mark) in enumerate(rows):
            w.writerow([f"s{i}", "n", calc, "x", mark])
    s: SpotCheckScore = score_spot_check(f)
    assert (s.checked, s.correct, s.unmarked) == (30, 28, 1)
    assert s.precision == pytest.approx(28 / 30)
    assert s.low < s.precision < s.high
    assert s.by_calc["tile"] == (12, 10)       # (checked, correct)
    # the interval's lower bound must clear the target, not the point estimate
    assert not s.meets(0.95)


def test_score_spot_check_rejects_unreadable_marks(tmp_path: Path) -> None:
    f = tmp_path / "spot.csv"
    f.write_text("sku,calc_template,correct\na,paint,maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="maybe"):
        score_spot_check(f)


def test_report_warns_loudly_when_prices_were_not_recognised(tmp_path: Path) -> None:
    f = tmp_path / "noprice.csv"
    f.write_text("sku;name;category;Прайс-лист\n1;Обои флизелиновые 1,06х10,05 м;Обои;100\n"
                 "2;Краска 2,5 л;Краски;200\n", encoding="utf-8")
    res = run_dayof(f, tmp_path / "o", sample_size=5)
    report = (tmp_path / "o" / "report.md").read_text(encoding="utf-8")
    assert res.loaded == 2
    assert "⚠" in report and "цен" in report.lower()
    assert "Прайс-лист" in report          # the unrecognised column is named, so it can be mapped


def test_report_shows_price_coverage_when_prices_are_fine(tmp_path: Path) -> None:
    f = tmp_path / "ok.csv"
    f.write_text("sku;name;category;price\n1;Обои 1,06х10,05 м;Обои;100\n", encoding="utf-8")
    run_dayof(f, tmp_path / "o", sample_size=5)
    report = (tmp_path / "o" / "report.md").read_text(encoding="utf-8")
    assert "с ценой: 1 из 1" in report and "⚠ Цены" not in report
