"""Benchmark embedding models for product-type matching (checklist G3).

    uv run python scripts/embed_bench.py hashing ollama:bge-m3 st:intfloat/multilingual-e5-base \
        st:ai-forever/FRIDA st:Qwen/Qwen3-Embedding-0.6B [--n 3000] [--ollama http://localhost:11434]

Candidates are `hashing` (offline baseline, no model), `ollama:<model>` (served by the local
Ollama) and `st:<hf model>` (sentence-transformers). A model that cannot be loaded is reported and
skipped; nothing is faked. Data is the SYNTHETIC generator unless you pass --gold-csv with
hand-verified rows from scripts/make_gold_sample.py (then train on dev, score on test).
"""
import argparse
import sys

from maxicalc.ml.embed import (
    Embedder,
    HashingEmbedder,
    OllamaEmbedder,
    SentenceTransformerEmbedder,
)
from maxicalc.ml.embed_match import benchmark
from maxicalc.ml.synth import generate, split_by_group


def build(spec: str, ollama: str) -> Embedder:
    if spec == "hashing":
        return HashingEmbedder(512)
    if spec.startswith("ollama:"):
        return OllamaEmbedder(ollama, spec[7:])
    if spec.startswith("st:"):
        return SentenceTransformerEmbedder(spec[3:])
    raise ValueError(f"Неизвестная модель: {spec}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--ollama", default="http://localhost:11434")
    a = ap.parse_args()
    train, _dev, test = split_by_group(generate(a.n, seed=0))
    print(f"train {len(train)}, test {len(test)} (SYNTHETIC; unseen product groups in test)")
    print(f"{'модель':48} {'macro-F1':>9} {'accuracy':>9} {'с':>7}")
    for spec in a.models:
        try:
            emb = build(spec, a.ollama)
            rep = benchmark({spec: emb}, train, test)[spec]
        except Exception as e:
            print(f"{spec:48} пропущена: {str(e)[:70]}")
            continue
        print(f"{spec:48} {rep.macro_f1:9.3f} {rep.accuracy:9.3f} {rep.seconds:7.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
