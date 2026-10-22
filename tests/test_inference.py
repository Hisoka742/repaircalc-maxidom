"""The inference service answers /embed and /health with the offline default embedder."""
from fastapi.testclient import TestClient

from maxicalc.inference.app import app


def test_embed_returns_unit_vectors() -> None:
    c = TestClient(app)
    r = c.post("/embed", json={"texts": ["краска для стен", "ламинат 32 класс"]})
    assert r.status_code == 200
    j = r.json()
    assert j["dim"] == len(j["vectors"][0]) == 512 and len(j["vectors"]) == 2
    assert abs(sum(x * x for x in j["vectors"][0]) - 1.0) < 1e-4


def test_health_names_the_embedder() -> None:
    j = TestClient(app).get("/health").json()
    assert j["status"] == "ok" and j["embedder"] == "hashing"


def test_empty_batch_is_rejected() -> None:
    assert TestClient(app).post("/embed", json={"texts": []}).status_code == 422
