"""Inference service: embeddings behind HTTP, scaled separately from the API (checklist K1).

The case asks for the ML models behind a separate inference layer. This service owns the embedder
(`EMBEDDER`: `hashing`, `ollama:<model>`, `st:<sentence-transformers model>`) so the calc API stays
stateless and light; the API (or the batch matcher) calls it, and it can be given the GPU alone.

    uvicorn maxicalc.inference.app:app --port 8100
"""
import os
import time
from functools import cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from maxicalc.ml.embed import Embedder, HashingEmbedder, OllamaEmbedder, SentenceTransformerEmbedder

app = FastAPI(title="Maxicalc inference", version="0.1.0")


@cache
def embedder() -> Embedder:
    spec = os.environ.get("EMBEDDER", "hashing")
    if spec == "hashing":
        return HashingEmbedder(int(os.environ.get("EMBED_DIM", "512")))
    if spec.startswith("ollama:"):
        return OllamaEmbedder(os.environ.get("OLLAMA_URL", "http://ollama:11434"), spec[7:])
    if spec.startswith("st:"):
        return SentenceTransformerEmbedder(spec[3:])
    raise ValueError(f"Неизвестный EMBEDDER: {spec}")


class EmbedIn(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=512)


class EmbedOut(BaseModel):
    dim: int
    vectors: list[list[float]]
    seconds: float


@app.get("/health")
def health() -> dict[str, str | int]:
    e = embedder()
    return {"status": "ok", "embedder": os.environ.get("EMBEDDER", "hashing"), "dim": e.dim}


@app.post("/embed", response_model=EmbedOut)
def embed(body: EmbedIn) -> EmbedOut:
    t0 = time.perf_counter()
    try:
        v = embedder().encode(body.texts)
    except Exception as e:  # model missing / Ollama down: say so, do not 500 blindly
        raise HTTPException(503, f"Модель эмбеддингов недоступна: {e}") from e
    return EmbedOut(dim=int(v.shape[1]), vectors=v.tolist(),
                    seconds=round(time.perf_counter() - t0, 4))
