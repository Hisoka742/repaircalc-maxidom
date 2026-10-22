"""Score the FROZEN test set (eval/gold/frozen_test_d.csv) and log the access.

    python scripts/eval_frozen.py [--note "what changed since the last look"]

Honesty guard (docs/TUNING_LOG.md): this set is labelled once, committed with its SHA-256, and is
never used to change a rule, a threshold or a model. Every run appends a line to
docs/TEST_ACCESS_LOG.md (time, git commit, file hash, systems, micro-F1) so an unusual number of
looks is visible to anyone reading the repo. Tuning happens on dev data only.
"""
import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

import joblib

from maxicalc.catalog.adapters import load_catalog
from maxicalc.ml.worktype_report import load_gold, markdown, run_gold_eval

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "eval/gold/frozen_test_d.csv"
LOG = ROOT / "docs/TEST_ACCESS_LOG.md"
EXPECTED = "ef3e32dd40bce89ae252d55a96d7675f8004ea3be0d40b83179575b36858349c"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", default=str(ROOT / "data/raw/products_final.json"))
    ap.add_argument("--model", default=str(ROOT / "data/models/worktypes.joblib"))
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    digest = hashlib.sha256(FROZEN.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if digest != EXPECTED:
        print(f"ОШИБКА: замороженный набор изменён (sha256 {digest[:12]} != {EXPECTED[:12]})")
        return 2
    products, _ = load_catalog(a.catalog)
    items = load_gold(FROZEN, {p.sku: p for p in products})
    model = joblib.load(a.model) if Path(a.model).exists() else None
    ev = run_gold_eval(items, model)
    md = "\n".join(markdown(ev, pilot=True))
    print(md[:2500])
    head = subprocess.run(["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True, cwd=ROOT).stdout.strip()
    dirty = bool(subprocess.run(["git", "-c", "safe.directory=*", "status", "--porcelain", "src"],
                                capture_output=True, text=True, cwd=ROOT).stdout.strip())
    cells = "; ".join(f"{k} {r.micro_f1:.3f}" for k, r in ev.systems.items())
    amb = f"{ev.ambiguous.micro_f1:.3f}" if ev.ambiguous else "-"
    line = (f"| {time.strftime('%Y-%m-%d %H:%M')} | {head}{'+dirty' if dirty else ''} | "
            f"{digest[:10]} | n={ev.n_test} | {cells} | amb {amb} | {a.note or '-'} |\n")
    if not LOG.exists():
        LOG.write_text("# Журнал обращений к замороженному тесту\n\n"
                       "| время | коммит | sha256 набора | строк | micro-F1 по системам | "
                       "неоднозначные | примечание |\n|---|---|---|---|---|---|---|\n",
                       encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
