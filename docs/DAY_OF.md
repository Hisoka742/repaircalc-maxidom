# Hackathon day runbook (7 Nov): stand URL → ingest → match → eval → metrics, under 1 hour

Times are measured on the mock stand with a synthetic 10 000-product catalog (re-match 4 s,
dayof pipeline ≤ 20 s). **The real stand's response time is unknown**, so the fetch step is the
only one that can blow the budget: it is cached on disk and rate-limited, so a restart does not
start over.

| # | Step | Command | Expected | Look at |
|---|---|---|---|---|
| 0 | Point at the stand | `.env`: `STAND_BASE_URL`, `STAND_TOKEN`, `STAND_REGION_ID` | 2 min | `curl $STAND_BASE_URL/api/regions` returns JSON |
| 1 | Full ingest (fetch, cards, normalize, extract, match, readiness) | `make ingest-stand` | stand-bound; local part < 1 min | `data/stand/quality.md` (field coverage, unit parse rate), `data/stand/report.md` |
| 2 | Read the readiness verdict | open `report.md` | 5 min | calculators marked **blocking** (< 50 % of their products have the needed attributes) |
| 3 | If a field is missing under another name | add the name to `CHAR_KEYS` in `ml/extract.py` (and a test), re-run step 1 (cache makes it fast) | 10 min | coverage rises in `quality.md` |
| 4 | Start the service on the stand catalog | `CATALOG_PATH=data/stand/stand.jsonl OVERRIDES_PATH=data/overrides.jsonl uv run uvicorn maxicalc.api.main:app` | 1 min | `GET /ready` → `catalog_size` |
| 5 | Smoke test | `uv run python scripts/smoke.py` | 1 min | 9/9 checks |
| 6 | Organiser reference values → golden | convert to `tests/golden` format, `GOLDEN_EXTRA=data/organizer_golden.yaml make eval` | 10 min | MAE of packs, failures list (expected vs actual) |
| 7 | Hand-verified sample for matching quality | `uv run python scripts/make_gold_sample.py data/stand/stand.jsonl --n 300 --out data/gold_todo.csv` → team fills `verified_calc` → `uv run python scripts/score_gold.py data/gold_todo.csv --split test` | 30 min of human work | per-class F1 (target ≥ 0.8), accuracy |
| 8 | Precision of auto-labels | `scripts/dayof.py score data/stand/spot_check.csv` | 10 min of human work | lower bound of the 95 % interval |
| 9 | Refresh the pitch | `make pitch` | 1 min | `docs/PITCH_METRICS.md` — only measured numbers; unmeasured say "не измерено" |
| 10 | Load test (optional, if time) | `uv run python scripts/load_test.py --rps 200 --seconds 60 --scenario mixed --procs 4` | 2 min | p95 < 100 ms, 0 × 5xx |

## If something fails

| Symptom | Cause | Action |
|---|---|---|
| `ingest-stand` exits 2 with a URL error | wrong `STAND_BASE_URL` / token | step 0; the message names the request |
| Fetch is slow | stand rate | `STAND_MIN_INTERVAL_S` up, `--limit 5000` for a first pass; the disk cache keeps progress |
| Many products have no price | `result_price` empty in the region | ask question #2 in `OPEN_QUESTIONS.md`; prices fall back to `price` |
| Calculator "blocking" | cards lack consumption / pack data | step 3; or accept: those lines are warnings, never invented numbers |
| LLM unreachable | Ollama down / wrong URL | nothing breaks: parse uses rules, explanations use templates |
| Demo needs the offline fallback | no network to the stand | `make mock-stand` (synthetic data) and set `STAND_BASE_URL` to it |

## What may be said on stage

Only what `docs/PITCH_METRICS.md` prints as measured. Synthetic-data figures are labelled
СИНТЕТИЧЕСКИЕ there and must be said as such. See `docs/RUNBOOK.md` for the long form
(file-based catalogs, failure table, Windows equivalents of `make`).
