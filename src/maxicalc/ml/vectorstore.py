"""Vector store behind a small interface (checklist G6).

An exact cosine search over a numpy matrix: at the catalog's size (10^4 - 10^5 SKUs of 384-1024
dimensions) a brute-force dot product is milliseconds and has no moving parts. The interface
(`add`, `search`, `save`, `load`) is what a pgvector/FAISS/Qdrant implementation would replace;
nothing else in the code depends on how vectors are stored.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Hit:
    id: str
    score: float


class VectorStore:
    def __init__(self, dim: int) -> None:
        self.dim = dim
        self._ids: list[str] = []
        self._pos: dict[str, int] = {}
        self._m = np.zeros((0, dim), dtype=np.float32)

    def __len__(self) -> int:
        return len(self._ids)

    @staticmethod
    def _unit(v: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(v, axis=-1, keepdims=True)
        return v / np.where(n == 0, 1, n)

    def add(self, ids: list[str], vectors: np.ndarray) -> None:
        v = np.asarray(vectors, dtype=np.float32)
        if v.ndim != 2 or v.shape[1] != self.dim or v.shape[0] != len(ids):
            raise ValueError(f"Ожидается матрица {len(ids)} x {self.dim}, получено {v.shape}")
        v = self._unit(v)
        fresh_ids: list[str] = []
        fresh: list[np.ndarray] = []
        for i, row in zip(ids, v, strict=True):
            if i in self._pos:
                self._m[self._pos[i]] = row          # replace in place
            else:
                fresh_ids.append(i)
                fresh.append(row)
        if fresh:
            start = len(self._ids)
            self._ids.extend(fresh_ids)
            for k, i in enumerate(fresh_ids):
                self._pos[i] = start + k
            self._m = np.vstack([self._m, np.stack(fresh)])

    def search(self, vector: np.ndarray, k: int = 5) -> list[Hit]:
        if not self._ids:
            return []
        q = self._unit(np.asarray(vector, dtype=np.float32).reshape(1, -1))[0]
        scores = self._m @ q
        k = min(k, len(self._ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [Hit(self._ids[i], float(scores[i])) for i in top]

    def save(self, path: Path) -> None:
        np.savez_compressed(path, ids=np.array(self._ids, dtype=object), m=self._m,
                            dim=np.array(self.dim))

    @classmethod
    def load(cls, path: Path) -> "VectorStore":
        z = np.load(path, allow_pickle=True)
        vs = cls(int(z["dim"]))
        vs._ids = [str(x) for x in z["ids"]]
        vs._pos = {i: k for k, i in enumerate(vs._ids)}
        vs._m = z["m"].astype(np.float32)
        return vs
