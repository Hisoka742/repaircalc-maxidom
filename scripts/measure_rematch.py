"""Time a full catalog (re)load + match, as the API does at startup / re-match.

    uv run python scripts/measure_rematch.py <catalog> [--model m.joblib]
Writes data/rematch.json (read by scripts/pitch_metrics.py).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from maxicalc.api.state import AppState
from maxicalc.config import Settings


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("catalog")
    ap.add_argument("--model")
    ap.add_argument("--out", default="data/rematch.json")
    a = ap.parse_args()
    t = time.perf_counter()
    st = AppState.from_settings(Settings(catalog_path=a.catalog, model_path=a.model,
                                         rate_limit_per_min=0, log_json=False))
    secs = time.perf_counter() - t
    n = len(st.index)
    auto = sum(e.status != "review" for e in st.index.entries)
    res = {"products": n, "seconds": round(secs, 2), "auto": auto,
           "skus_per_second": round(n / secs), "model": bool(a.model)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"{n} SKUs re-matched in {secs:.1f}s ({n / secs:.0f} SKU/s); auto {auto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
