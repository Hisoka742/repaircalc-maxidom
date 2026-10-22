# `uv run` when uv is installed, plain python otherwise (CI, pip users): make RUN= to force plain python
RUN ?= $(if $(shell command -v uv 2>/dev/null),uv run,)
PIP ?= $(if $(shell command -v uv 2>/dev/null),uv sync,pip install -e ".[dev]")
CATALOG ?= data/raw/products_final.json
MODEL ?=
OUT ?= data/dayof

.PHONY: install lint typecheck test eval run serve smoke ingest demo load loadpy up down \
        demo-data dayof score rematch pitch feed reproduce worktypes-eval dump-report category-map full-run
install:
	$(PIP)
lint:
	$(RUN) ruff check src tests eval scripts
typecheck:
	$(RUN) mypy
test: lint typecheck
	$(RUN) pytest
# golden cases, extraction, matching, recommendation -> eval/REPORT.md
eval:
	$(RUN) python eval/run_eval.py
run:
	$(RUN) uvicorn maxicalc.api.main:app --reload --port 8000
# serve a catalog: make serve CATALOG=data/raw/products_final.json
serve:
	CATALOG_PATH=$(CATALOG) $(if $(MODEL),MODEL_PATH=$(MODEL)) $(RUN) uvicorn maxicalc.api.main:app --port 8000
smoke:
	$(RUN) python scripts/smoke.py
# data-quality report of the official dataset (data/raw/products_final.json) -> docs/DATASET_REPORT.md
ingest:
	$(RUN) python scripts/ingest_dump.py
# start the service on the dataset, run the end-to-end scenario (estimate, upload job, new product), stop
demo:
	$(RUN) python scripts/demo.py
load:
	k6 run scripts/load_test.js
loadpy:
	$(RUN) python scripts/load_test.py --rps 200 --seconds 30 --scenario mixed
up:
	docker compose up -d --build
down:
	docker compose down

# ---- synthetic demo data and hackathon day ----
feed:
	$(RUN) python scripts/ingest_feed.py
demo-data:
	$(RUN) python scripts/make_demo_catalog.py --n 10000
dayof:
	$(RUN) python scripts/dayof.py run $(CATALOG) --out $(OUT) $(if $(MODEL),--model $(MODEL))
score:
	$(RUN) python scripts/dayof.py score $(OUT)/spot_check.csv
rematch:
	$(RUN) python scripts/measure_rematch.py $(CATALOG) $(if $(MODEL),--model $(MODEL))
pitch:
	$(RUN) python scripts/pitch_metrics.py --spot $(OUT)/spot_check.csv
reproduce:
	$(RUN) python scripts/reproduce.py
worktypes-eval:
	$(RUN) python scripts/eval_worktypes.py
dump-report: ingest
category-map:
	$(RUN) python scripts/build_category_map.py
full-run:
	$(RUN) python scripts/full_run.py
