"""Embedding providers behind one interface (checklist G3).

* `HashingEmbedder`: deterministic character/word n-gram hashing. No model, no download: a
  baseline and the offline fallback. It is not a language model.
* `OllamaEmbedder`: an embedding model served by the local Ollama (closed contour).
* `SentenceTransformerEmbedder`: e5 / RuBERT / FRIDA / bge-m3 / Qwen3-Embedding through
  sentence-transformers, imported lazily (it is an optional heavy dependency).

`scripts/embed_bench.py` compares them by macro-F1 on the gold set; the best one is configured,
not hard-coded.
"""
import re
import zlib
from typing import Any, Protocol

import httpx
import numpy as np

from maxicalc.catalog.schema import Product


class Embedder(Protocol):
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray: ...


def product_text(p: Product) -> str:
    """What gets embedded: name, category path and the product's own characteristics."""
    chars = "; ".join(f"{k}: {v}" for k, v in list(p.characteristics.items())[:12])
    return " | ".join(x for x in (p.name, " > ".join(p.category_path), chars) if x)


def _l2(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(n == 0, 1, n)


_TOKEN = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)


class HashingEmbedder:
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for r, t in enumerate(texts):
            low = t.lower().replace("ё", "е")
            feats = [f"w:{w}" for w in _TOKEN.findall(low)]
            for w in _TOKEN.findall(low):
                padded = f"^{w}$"
                feats += [f"c:{padded[i:i + n]}" for n in (3, 4)
                          for i in range(len(padded) - n + 1)]
            for f in feats:
                h = zlib.crc32(f.encode())
                out[r, h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
        return _l2(out)


class OllamaEmbedder:
    """POST {base_url}/api/embed with {"model", "input": [...]}: Ollama's native embedding API."""

    def __init__(self, base_url: str, model: str, dim: int = 0, timeout: float = 60.0,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dim = dim
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def encode(self, texts: list[str]) -> np.ndarray:
        r = self._http.post(f"{self.base_url}/api/embed", json={"model": self.model,
                                                                "input": texts})
        r.raise_for_status()
        m = np.array(r.json()["embeddings"], dtype=np.float32)
        self.dim = int(m.shape[1])
        return _l2(m)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, prefix: str | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Нужен пакет sentence-transformers (uv add sentence-transformers)") from e
        self._model: Any = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())
        # e5 models were trained with "passage: " / "query: " prefixes
        self.prefix = prefix if prefix is not None else (
            "passage: " if "e5" in model_name.lower() else "")

    def encode(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - needs the model
        return _l2(np.asarray(self._model.encode([self.prefix + t for t in texts],
                                                 normalize_embeddings=True), dtype=np.float32))
