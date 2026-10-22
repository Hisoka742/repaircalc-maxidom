# Server runbook: benchmarks and model choice

One script does the whole sequence; nothing is measured here yet (no GPU or Ollama on the
development laptop), so the numbers in `docs/LLM.md` / `eval/REPORT.md` appear only after a run.

## RTX 3090 + Ollama box (target)

```bash
git pull && bash scripts/server_bench.sh --gpu
```

What it does, in order:

1. `docker compose up -d` (api, worker, postgres, redis, ollama).
2. Pulls the LLM candidates: `qwen3:14b`, `qwen3:8b`, GigaChat 3.1 Lightning GGUF
   (`hf.co/ai-sage/GigaChat3.1-10B-A1.8B-GGUF:Q8_0`) and the `bge-m3` embedder into Ollama.
3. `scripts/embed_bench.py`: hashing baseline, `ollama:bge-m3`, `st:intfloat/multilingual-e5-base`,
   `st:ai-forever/FRIDA`, `st:Qwen/Qwen3-Embedding-0.6B` -> macro-F1 / accuracy / seconds on the
   product-type task (synthetic split unless you pass `--gold-csv` with the team's labels).
4. `scripts/llm_bench.py`: parse-the-request pass rate, latency and the explanation check per model.
5. `scripts/pick_winners.py`: best embedder (macro-F1, then speed) -> `EMBEDDER=` in `.env`; best
   LLM (parsed requests, explanation, then latency) -> `LLM_MODEL=`; both tables are appended to
   `docs/LLM.md` and `eval/REPORT.md`; `HARDWARE_TIER=gpu24` is set. A model the benchmark skipped
   never wins.

Afterwards run the recommendation ablation with the winner (the offline hashing run did not prove
"relevance does not hurt", see `eval/REPORT.md`):

```bash
EMBEDDER=$(grep ^EMBEDDER= .env | cut -d= -f2) make eval
```

Output of every run is kept under `out/bench-<timestamp>/` (`embed.txt`, `llm.txt`).

## CPU-only fallback (laptop)

```bash
bash scripts/server_bench.sh --cpu            # light set: e5-small, bge-m3 on CPU; qwen3:4b / 1.7b
```

Matching is batch/offline, so CPU is acceptable for the embedder; the LLM part needs a running
Ollama (`ollama serve`) — without one the script says so, skips the LLM benchmark and still
benchmarks the embedders. Expect several minutes for the first model download.

## Kaggle / bare Python (no docker)

```bash
pip install -e . sentence-transformers
bash scripts/server_bench.sh --cpu --no-docker      # or --gpu on a Kaggle GPU notebook
```

Kaggle has no Ollama by default; install it (`curl -fsSL https://ollama.com/install.sh | sh;
ollama serve &`) to get the LLM table too. Everything stays inside the notebook; nothing is sent
to a remote LLM API.

## What to do with the result

- `.env` now holds `EMBEDDER`, `LLM_MODEL`, `HARDWARE_TIER`; restart `docker compose up -d api`.
- Commit `docs/LLM.md` and `eval/REPORT.md` so the pitch numbers cite a dated run.
- If the winning LLM's explanation check fails on any request, keep `LLM_ENABLED=true` only with the
  template fallback (the app already falls back); do not raise `INFERRED_MIN_CONFIDENCE` above its
  default until a benchmark of LLM extraction accuracy exists.
