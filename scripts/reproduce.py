"""One command from a clean clone to the work-type numbers (make reproduce).

    uv sync && uv run python scripts/reproduce.py [--catalog data/feed/latest.xml.gz]

1. get the feed snapshot (downloads it if `data/feed/latest.xml.gz` is absent);
2. ingest + repair-scope report (timing);
3. rule labels -> train on part of the categories -> evaluate on HELD-OUT categories
   (scripts/train_worktypes.py; SILVER because labels are rules) -> retrain on everything;
4. if the human gold set exists: scripts/eval_worktypes.py (REAL numbers);
5. write eval/REPRODUCE.md with the results, timings, CPU / RAM / GPU and model size.
Everything runs on a laptop CPU; there is no network use except step 1.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    print("$", *args, flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--catalog", default="data/feed/latest.xml.gz")
    a = ap.parse_args()
    t0 = time.perf_counter()
    cat = ROOT / a.catalog
    if not cat.exists():
        run("scripts/ingest_feed.py")
    else:
        run("scripts/ingest_feed.py", "--file", a.catalog)
    run("scripts/train_worktypes.py", "--catalog", a.catalog)
    gold = ROOT / "eval/gold/worktype_gold.csv"
    gold_md = ""
    if gold.exists():
        run("scripts/eval_worktypes.py", "--catalog", a.catalog)
        gold_md = (ROOT / "eval/WORKTYPES.md").read_text(encoding="utf-8")
    rep = json.loads((ROOT / "out/train_worktypes.json").read_text(encoding="utf-8"))
    (ROOT / "eval/worktypes_run.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1),
                                                  encoding="utf-8")   # input of make pitch
    h, st, m = rep["holdout"], rep["stages"], rep["machine"]
    L = ["# Reproduction report (`make reproduce`)", "",
         f"- Catalog: {rep['products']} products; total wall time {time.perf_counter() - t0:.0f} s",
         f"- Machine: {m['cpu']}, {m['cores_physical']} cores / {m['cores_logical']} threads, "
         f"{m['ram_gb']} GB RAM, GPU: {m['gpu'] or 'none (CPU only)'}",
         f"- Model size: {rep['model_mb']} MB", "",
         "## Held-out categories (SILVER: labels are the rules)", "",
         f"- {h['held_categories']} categories never seen in training, {h['n']} products: "
         f"micro-F1 **{h['micro_f1']:.3f}**, macro-F1 {h['macro_f1']:.3f}, sample-F1 "
         f"{h['samples_f1']:.3f}, Hamming loss {h['hamming_loss']:.4f}",
         f"- Name has no keyword of the work ({int(h['non_literal']['pairs'])} pairs): F1 "
         f"{h['non_literal']['f1']:.3f}",
         "", "## Timings and resources", "",
         "| step | seconds | items | s per 1k items | peak RAM, MB |", "|---|---|---|---|---|"]
    for k, s in st.items():
        per = s["seconds"] / s["items"] * 1000 if s["items"] else 0.0
        L.append(f"| {k} | {s['seconds']:.1f} | {s['items']} | {per:.2f} "
                 f"| {s['peak_rss_mb']:.0f} |")
    if gold_md:
        L += ["", gold_md]
    else:
        L += ["", "## Human gold set", "",
              "- `eval/gold/worktype_gold.csv` not found: the REAL micro-F1 is **not measured**. "
              "Label the sheets (docs/EVAL_METHODOLOGY.md), run scripts/merge_worktype_gold.py."]
    (ROOT / "eval/REPRODUCE.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
