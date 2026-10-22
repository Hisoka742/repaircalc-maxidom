#!/usr/bin/env bash
# One command on the RTX 3090 + Ollama box (or a CPU-only laptop / Kaggle):
#   docker compose up -> embedder benchmark -> LLM benchmark -> winners into .env,
#   results appended to docs/LLM.md and eval/REPORT.md.
#
#   bash scripts/server_bench.sh              # auto: GPU if nvidia-smi works, else CPU
#   bash scripts/server_bench.sh --gpu        # force the 3090 model set
#   bash scripts/server_bench.sh --cpu        # light models, no GPU needed
#   bash scripts/server_bench.sh --no-docker  # Kaggle / bare python: skip compose, use the
#                                             # Ollama already running (or none: LLM part skipped)
# See docs/SERVER_RUNBOOK.md.
set -u
cd "$(dirname "$0")/.."

MODE=auto
DOCKER=1
for a in "$@"; do
  case "$a" in
    --gpu) MODE=gpu ;;
    --cpu) MODE=cpu ;;
    --no-docker) DOCKER=0 ;;
    *) echo "unknown flag $a"; exit 64 ;;
  esac
done
if [ "$MODE" = auto ]; then
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then MODE=gpu; else MODE=cpu; fi
fi
echo "== mode: $MODE, docker: $DOCKER"

PY="${PYTHON:-python}"
command -v uv >/dev/null 2>&1 && PY="uv run python"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
OUT="out/bench-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"

if [ "$MODE" = gpu ]; then
  EMBEDDERS="hashing ollama:bge-m3 st:intfloat/multilingual-e5-base st:ai-forever/FRIDA st:Qwen/Qwen3-Embedding-0.6B"
  LLMS="qwen3:14b qwen3:8b hf.co/ai-sage/GigaChat3.1-10B-A1.8B-GGUF:Q8_0"
  TIER=gpu24
else
  EMBEDDERS="hashing st:intfloat/multilingual-e5-small st:BAAI/bge-m3"
  LLMS="qwen3:4b qwen3:1.7b"
  TIER=cpu
fi

if [ "$DOCKER" = 1 ]; then
  echo "== docker compose up"
  docker compose up -d || { echo "docker compose failed"; exit 1; }
fi

ollama_up() { curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; }
for i in $(seq 1 30); do ollama_up && break; sleep 2; done
HAVE_OLLAMA=0; ollama_up && HAVE_OLLAMA=1
if [ "$HAVE_OLLAMA" = 1 ]; then
  for m in $LLMS bge-m3; do
    echo "== pull $m"
    if [ "$DOCKER" = 1 ] && docker compose ps --services 2>/dev/null | grep -qx ollama; then
      docker compose exec -T ollama ollama pull "$m" || echo "   (pull failed: $m)"
    else
      ollama pull "$m" || echo "   (pull failed: $m)"
    fi
  done
else
  echo "!! Ollama not reachable at $OLLAMA_URL: LLM and ollama:* embedders are skipped"
fi

echo "== embedder benchmark"
$PY scripts/embed_bench.py $EMBEDDERS --ollama "$OLLAMA_URL" | tee "$OUT/embed.txt"

LLM_ARG=""
if [ "$HAVE_OLLAMA" = 1 ]; then
  echo "== LLM benchmark"
  $PY scripts/llm_bench.py $LLMS --base-url "$OLLAMA_URL/v1" | tee "$OUT/llm.txt"
  LLM_ARG="--llm $OUT/llm.txt"
fi

echo "== recommendation ablation with the winning embedder is run by 'make eval' afterwards"
touch .env
$PY scripts/pick_winners.py --embed "$OUT/embed.txt" $LLM_ARG --env .env
grep -q '^HARDWARE_TIER=' .env && sed -i "s/^HARDWARE_TIER=.*/HARDWARE_TIER=$TIER/" .env || echo "HARDWARE_TIER=$TIER" >> .env
echo "== done: raw output in $OUT, winners in .env; docs/LLM.md and eval/REPORT.md updated"
