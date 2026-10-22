"""Embed every repair-scope product with a sentence-embedding model on CPU and cache to disk.

    PYTHONPATH=data/stlibs python scripts/embed_cache.py st:intfloat/multilingual-e5-base
    PYTHONPATH=data/stlibs python scripts/embed_cache.py st:ai-forever/FRIDA --prefix "categorize: "

Text = name + leaf category + the first parameters (short, 64 tokens), so a CPU run is affordable.
Resumable: chunks of 2 000 products go to data/emb/<model>/part_<n>.npy; a finished model has
`done.json` with seconds, products/s and peak RAM (REAL timings for PITCH_METRICS). The product order
is `data/emb/skus.txt` (written once, all products of category-map scope "repair", dump order).
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

from maxicalc.catalog.adapters import load_catalog
from maxicalc.ml.category_baseline import table
from maxicalc.ml.embed import SentenceTransformerEmbedder
from maxicalc.resources import Stage

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 2000


def text_of(p) -> str:  # type: ignore[no-untyped-def]
    params = "; ".join(f"{k}: {v}" for k, v in list(p.characteristics.items())[:6]
                       if len(v) < 40 and k != "category_id")
    return f"{p.name} | {p.category_path[-1] if p.category_path else ''} | {params}"[:400]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", help="st:<huggingface name>")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--max-len", type=int, default=64)
    ap.add_argument("--catalog", default=str(ROOT / "data/raw/products_final.json"))
    a = ap.parse_args()
    name = a.model.removeprefix("st:")
    out = ROOT / "data/emb" / re.sub(r"[^A-Za-z0-9]+", "_", name)
    out.mkdir(parents=True, exist_ok=True)
    products, _ = load_catalog(a.catalog)
    scope = table()
    rep = [p for p in products
           if (scope.get(p.characteristics.get("category_id", "")) or None) is not None
           and scope[p.characteristics["category_id"]].scope == "repair"]
    skus = ROOT / "data/emb/skus.txt"
    if not skus.exists():
        skus.write_text("\n".join(p.sku for p in rep), encoding="utf-8")
    emb = SentenceTransformerEmbedder(name, prefix=a.prefix)
    emb._model.max_seq_length = a.max_len
    todo = [rep[i:i + CHUNK] for i in range(0, len(rep), CHUNK)]
    t0 = time.perf_counter()
    done_items = 0
    with Stage("embed") as st:
        for n, chunk in enumerate(todo):
            f = out / f"part_{n:03d}.npy"
            if f.exists():
                continue
            vec = emb.encode([text_of(p) for p in chunk]).astype(np.float16)
            np.save(f, vec)
            done_items += len(chunk)
            el = time.perf_counter() - t0
            print(f"{name}: chunk {n + 1}/{len(todo)}  {done_items / el:.1f} products/s", flush=True)
    seconds = time.perf_counter() - t0
    (out / "done.json").write_text(json.dumps({
        "model": name, "products": len(rep), "newly_embedded": done_items,
        "seconds_this_run": round(seconds, 1), "products_per_s": round(done_items / max(seconds, 1), 1),
        "peak_rss_mb": round(st.peak_rss_mb), "max_len": a.max_len, "dim": emb.dim}, indent=2))
    print("готово", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
