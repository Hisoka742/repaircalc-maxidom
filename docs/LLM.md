# Local LLM and models (Ollama, closed contour)

Target server: Core i7-14700K, 32 GB RAM, **RTX 3090 24 GB**, Ollama. No internet at runtime:
the app refuses an LLM URL that is not localhost, a LAN address or a bare service name
(`LLM_ALLOW_REMOTE=true` overrides, on purpose). Model name and URL come from `.env`
(`LLM_BASE_URL`, `LLM_MODEL`).

## What the LLM is used for (and not)

| Job | Where | If the model is down |
|---|---|---|
| Free text → structured room input | `ml/parse_request.py`, `POST /api/v1/parse` | rules only |
| "Why these materials" phrasing over retrieved facts | `recommend/rag.py` | template text |
| Extraction fallback for fields the regex missed (quote must occur in the card) | `ml/extract.py` | the field stays unknown |
| Judge for the uncertain zone (suggestion only, never auto-accepted) | `ml/judge.py` | stays in the review queue |

**Never**: arithmetic, prices, quantities. Every number in a response comes from the engine; an
explanation containing a number that is not in the data is rejected.

## Structured output

Requests send the JSON schema (`response_format: json_schema`), `temperature: 0` and
`reasoning_effort: none` (no thinking phase). The client validates the result against the schema
(required keys, types, enums), retries on a parse failure, and counts `parse_failures`,
`http_failures`, `failed_calls` (`LLMClient.stats`). Measure the real parse-failure rate with
`scripts/llm_bench.py` on the server.

## Choosing the model (not yet measured: no Ollama here)

Candidates: `qwen3:14b` (default), `qwen3:8b`, the GigaChat 3.1 Lightning GGUF
(`hf.co/ai-sage/GigaChat3.1-10B-A1.8B-GGUF`). Run:

```
uv run python scripts/llm_bench.py qwen3:14b qwen3:8b <gigachat tag>
```

Record accuracy, latency and `nvidia-smi` memory in the table below. Keep the better one in `.env`.

| model | parse 4/4 | s per request | explain ok | VRAM (nvidia-smi) |
|---|---|---|---|---|
| qwen3:14b | not measured | | | |
| qwen3:8b | not measured | | | |
| GigaChat 3.1 Lightning | not measured | | | |

## VRAM budget for 24 GB (engineering estimate, to be confirmed with `nvidia-smi`)

| Component | Approx. VRAM | Note |
|---|---|---|
| LLM, 14B at Q4_K_M | 9–10 GB + KV cache 1–3 GB (8k context) | the main consumer |
| Embedding model (bge-m3 / e5-base class, fp16) | 1–2 GB | `ollama:<model>` or the `inference` service |
| Reranker 0.6B (fp16) | ≈ 1.2 GB | optional |
| CUDA context and fragmentation | 1–2 GB | |
| **Total** | **≈ 14–18 GB** | fits with headroom for a second request |

Ollama unloads idle models after `OLLAMA_KEEP_ALIVE`; set it so the LLM stays resident during the
demo and the embedder is loaded on demand. A 32B model at Q4 (≈ 19–20 GB) leaves no room for the
others on 24 GB: either run it alone or do not use it.

## Embeddings

`scripts/embed_bench.py` compares `hashing` (offline baseline), `ollama:<model>` and
`st:<hf model>` (e5 / RuBERT / FRIDA / bge-m3 / Qwen3-Embedding) by macro-F1 of the product-type
classifier. Baseline on SYNTHETIC data (3000 items, unseen product groups in test): hashing
embedder macro-F1 **0.912**, accuracy 0.978. The sentence-transformer / Ollama models were not
run here (not installed, no model download); run the script on the server and keep the best by F1
on the hand-verified gold set (`scripts/make_gold_sample.py`, `scripts/score_gold.py`).
