"""Checklist G2/G3/G6: vector store, embeddings + benchmark, LLM judge, gold-set tooling."""
import csv
import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.embed import HashingEmbedder, OllamaEmbedder, product_text
from maxicalc.ml.embed_match import benchmark, fit_embedding_classifier
from maxicalc.ml.gold import sample_for_labeling, score_gold, split_of
from maxicalc.ml.judge import judge_uncertain
from maxicalc.ml.llm_client import LLMClient
from maxicalc.ml.synth import generate
from maxicalc.ml.vectorstore import VectorStore


# ---------------- vector store ----------------
def test_vector_store_finds_the_nearest_and_persists(tmp_path: Path) -> None:
    emb = HashingEmbedder(dim=256)
    names = ["краска для стен моющаяся", "ламинат 32 класс", "гипсокартон влагостойкий"]
    vs = VectorStore(dim=256)
    vs.add(["paint", "lam", "drywall"], emb.encode(names))
    hit = vs.search(emb.encode(["краска моющаяся для стен 9 л"])[0], k=1)
    assert hit[0].id == "paint" and hit[0].score > 0.3
    p = tmp_path / "v.npz"
    vs.save(p)
    back = VectorStore.load(p)
    assert len(back) == 3
    assert back.search(emb.encode(["ламинат"])[0], k=1)[0].id == "lam"


def test_vector_store_rejects_the_wrong_dimension() -> None:
    vs = VectorStore(dim=8)
    with pytest.raises(ValueError):
        vs.add(["a"], np.zeros((1, 9), dtype=np.float32))


def test_add_replaces_an_existing_id() -> None:
    vs = VectorStore(dim=4)
    vs.add(["a"], np.array([[1, 0, 0, 0]], dtype=np.float32))
    vs.add(["a"], np.array([[0, 1, 0, 0]], dtype=np.float32))
    assert len(vs) == 1
    assert vs.search(np.array([0, 1, 0, 0], dtype=np.float32), k=1)[0].score > 0.99


# ---------------- embedders ----------------
def test_hashing_embedder_is_deterministic_and_normalised() -> None:
    e = HashingEmbedder(dim=128)
    a, b = e.encode(["краска"]), e.encode(["краска"])
    assert np.allclose(a, b) and abs(float(np.linalg.norm(a[0])) - 1.0) < 1e-5


def test_ollama_embedder_uses_the_local_api() -> None:
    seen: list[dict] = []  # type: ignore[type-arg]

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0], [0.0, 2.0]]})

    e = OllamaEmbedder("http://ollama:11434", "bge-m3", transport=httpx.MockTransport(handler))
    v = e.encode(["a", "b"])
    assert seen[0]["model"] == "bge-m3" and seen[0]["input"] == ["a", "b"]
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0)       # normalised


def test_product_text_uses_name_category_and_characteristics() -> None:
    p = Product(sku="1", name="Краска", category_path=["Краски", "Для стен"],
                characteristics={"Цвет": "белый"})
    t = product_text(p)
    assert "Краска" in t and "Для стен" in t and "белый" in t


# ---------------- embedding classifier + benchmark ----------------
def test_embedding_classifier_beats_chance_and_benchmark_reports_f1() -> None:
    items = generate(900, seed=3)
    train, test = items[:600], items[600:]
    clf = fit_embedding_classifier(HashingEmbedder(dim=512), [i.product for i in train],
                                   [i.gold.calc for i in train])
    pred = clf.predict([i.product for i in test])
    acc = np.mean([p == i.gold.calc for p, i in zip(pred, test, strict=True)])
    assert acc > 0.6
    rep = benchmark({"hashing-512": HashingEmbedder(dim=512)}, train, test)
    assert 0 < rep["hashing-512"].macro_f1 <= 1 and rep["hashing-512"].n_test == len(test)


# ---------------- LLM judge ----------------
def llm_json(payload: dict) -> LLMClient:  # type: ignore[type-arg]
    def h(req: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"content": json.dumps(payload)}}]}
        return httpx.Response(200, json=body)

    return LLMClient("http://x/v1", "m", retries=0, transport=httpx.MockTransport(h))


def test_judge_picks_only_among_the_offered_candidates() -> None:
    p = Product(sku="1", name="Эмаль белая 0,9 л", category_path=["Краски"])
    ok = judge_uncertain(p, ["paint", "primer"], llm_json({"calc": "paint", "reason": "эмаль"}))
    assert ok is not None and ok.calc == "paint"
    bad = judge_uncertain(p, ["paint", "primer"], llm_json({"calc": "tile", "reason": "?"}))
    assert bad is None                      # an answer outside the candidates is discarded


def test_judge_failure_is_none_not_an_exception() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    llm = LLMClient("http://x/v1", "m", retries=0, transport=httpx.MockTransport(boom))
    assert judge_uncertain(Product(sku="1", name="x"), ["paint"], llm) is None


# ---------------- gold tooling ----------------
def test_sampling_is_stratified_and_the_split_is_stable() -> None:
    items = generate(1500, seed=5)
    ps = [i.product for i in items]
    calc = {i.product.sku: i.gold.calc for i in items}
    rows = sample_for_labeling(ps, lambda p: calc[p.sku], n=300, seed=1)
    assert 280 <= len(rows) <= 300
    by: dict[str, int] = {}
    for r in rows:
        by[r.predicted_calc] = by.get(r.predicted_calc, 0) + 1
    assert len(by) >= 8 and max(by.values()) < 0.4 * len(rows)     # no single class dominates
    assert {split_of(r.sku) for r in rows} == {"dev", "test"}
    assert split_of("A-1") == split_of("A-1")


def test_score_gold_reports_per_class_f1_and_ignores_unverified(tmp_path: Path) -> None:
    f = tmp_path / "gold.csv"
    rows = [
        ("1", "paint", "paint"), ("2", "paint", "paint"), ("3", "paint", "primer"),
        ("4", "tile", "tile"), ("5", "tile", "tile"), ("6", "primer", ""),   # not verified yet
    ]
    with f.open("w", encoding="utf-8", newline="") as h:
        w = csv.writer(h)
        w.writerow(["sku", "predicted_calc", "verified_calc"])
        w.writerows(rows)
    rep = score_gold(f)
    assert rep.verified == 5 and rep.skipped == 1
    assert rep.per_class["tile"].f1 == 1.0
    # predicted paint 3 times, 2 were paint; both true paints were found
    assert abs(rep.per_class["paint"].precision - 2 / 3) < 1e-9
    assert abs(rep.per_class["paint"].recall - 1.0) < 1e-9
    assert 0 < rep.macro_f1 <= 1
