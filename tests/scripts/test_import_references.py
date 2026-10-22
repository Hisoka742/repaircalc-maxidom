"""The reference sheet: template shape and import of a filled row into a runnable golden case."""
import csv
import importlib.util
import sys
from pathlib import Path

from maxicalc.golden import run_case

ROOT = Path(__file__).resolve().parents[2] / "scripts"


def load(name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def test_template_has_forty_rows_ten_per_calc(tmp_path: Path) -> None:
    mk = load("make_reference_template")
    out = tmp_path / "t.csv"
    sys.argv = ["x", "--out", str(out)]
    assert mk.main() == 0
    rows = list(csv.DictReader(out.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
    assert len(rows) == 40 and len({r["id"] for r in rows}) == 40
    for calc in ("wallpaper_rolls", "laminate_packs", "paint_liters", "tile_packs"):
        assert sum(r["calc"] == calc for r in rows) == 10
    assert all(r["calculator_url"] == "" and r["result_value"] == "" for r in rows)


def test_filled_row_becomes_a_runnable_verified_case(tmp_path: Path) -> None:
    imp = load("import_references")
    row = {"id": "ref-lam-01", "calc": "laminate_packs", "calculator_url": "https://example.test/c",
           "result_value": "8", "accessed_date": "2026-10-20", "note": "",
           "inputs_json": '{"area": 12, "layout": "straight"}', "m2_per_pack (fill)": "1,596"}
    case, why = imp.to_case(row)
    assert case and not why and case["verified"] is True and case["kind"] == "pack"
    assert case["inputs"]["m2_per_pack"] == 1.596
    assert run_case(case).actual is not None          # 12 m2 +7 % / 1.596 -> packs
    bad, reason = imp.to_case({**row, "calculator_url": ""})
    assert bad is None and "calculator_url" in reason
    missing, reason = imp.to_case({**row, "m2_per_pack (fill)": ""})
    assert missing is None and "m2_per_pack" in reason
