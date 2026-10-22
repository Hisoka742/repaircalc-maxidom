"""Turn the filled data/reference_cases_todo.csv into verified golden cases.

    uv run python scripts/import_references.py data/reference_cases_todo.csv \
        [--out tests/golden/golden_imported.yaml]

A row becomes a case only if `calculator_url` (http...), `result_value` (a number) and
`accessed_date` are filled and the product columns its calc needs are present; every other row is
listed with the reason and skipped. Imported cases are `verified: true`,
`source: manufacturer-calculator`, and are loaded by `maxicalc.golden.load_cases`.
"""
import argparse
import csv
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

PACK_CALCS = {"wallpaper_rolls", "laminate_packs", "tile_packs"}
DEFAULT_TOL = {"paint_liters": "0.05"}   # a calculator shows litres rounded to 2 decimals


def num(s: str) -> Decimal | None:
    s = (s or "").strip().replace(",", ".").replace(" ", "")
    try:
        return Decimal(s) if s else None
    except InvalidOperation:
        return None


def to_case(r: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    cid, calc = r["id"].strip(), r["calc"].strip()
    url = r["calculator_url"].strip()
    res = num(r["result_value"])
    if not re.match(r"https?://", url):
        return None, "нет calculator_url"
    if res is None:
        return None, "нет result_value"
    if not r["accessed_date"].strip():
        return None, "нет accessed_date"
    inputs: dict[str, Any] = json.loads(r["inputs_json"])
    need: dict[str, str] = {
        "wallpaper_rolls": {"roll_width_m (fill)": "roll_width",
                            "roll_length_m (fill)": "roll_length"},
        "laminate_packs": {"m2_per_pack (fill)": "m2_per_pack"},
        "paint_liters": {"coverage_m2_per_l (fill)": "spread"},
        "tile_packs": {"m2_per_pack (fill)": "m2_per_pack"},
    }.get(calc, {})  # type: ignore[assignment]
    for col, key in need.items():
        v = num(r.get(col, ""))
        if v is None:
            return None, f"нет {col}"
        inputs[key] = float(v)
    if calc == "paint_liters":
        inputs.setdefault("layers", 2)
    kind = "pack" if calc in PACK_CALCS else "continuous"
    case: dict[str, Any] = {
        "id": cid, "calc": calc, "kind": kind, "inputs": inputs,
        "expected": int(res) if kind == "pack" else float(res),
        "tolerance": float(DEFAULT_TOL.get(calc, "0")),
        "source": "manufacturer-calculator", "verified": True, "source_url": url,
        "accessed": r["accessed_date"].strip(),
    }
    if r.get("note", "").strip():
        case["note"] = r["note"].strip()
    return case, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--out", default="tests/golden/golden_imported.yaml")
    a = ap.parse_args()
    text = Path(a.csv).read_text(encoding="utf-8-sig")
    delim = ";" if text.split("\n", 1)[0].count(";") else ","
    cases, skipped = [], []
    for r in csv.DictReader(text.splitlines(), delimiter=delim):
        c, why = to_case(r)
        if c:
            cases.append(c)
        else:
            skipped.append((r["id"], why))
    for cid, why in skipped:
        print(f"пропущено {cid}: {why}")
    if not cases:
        print("ничего не импортировано")
        return 2
    out = Path(a.out)
    out.write_text("# Imported by scripts/import_references.py from the filled reference sheet.\n"
                   + yaml.safe_dump({"cases": cases}, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    print(f"импортировано {len(cases)} случаев -> {out}; пропущено {len(skipped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
