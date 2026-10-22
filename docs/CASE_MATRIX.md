# Case requirements matrix

Every requirement and metric of the case text («RepairCalc — микросервис умных калькуляторов
ремонта и стоимости работ»), mapped to code, endpoint and test. "Not in MVP" rows follow the case.

## Scenarios (case §2)

| Requirement | Module | Endpoint | Test |
|---|---|---|---|
| General calculator: object type, renovation class, areas, rooms → estimate (floor, walls, wallpaper, electrical) + approximate cost | `service/property_calc.py`, `service/room_calc.py`, `service/basket.py` (groups), `service/labor_calc.py` | `POST /api/v1/calc/property` | `tests/service/test_property_calc.py`, `tests/service/test_basket_groups_optimizer.py`, `tests/e2e/test_demo.py` |
| Room-specific calculator: humidity, load, purpose → materials | `recommend/rules_kb.py`, `knowledge/room_rules.yaml` (rooms + overlays) | `POST /api/v1/calc/room`, `POST /api/v1/recommend` | `tests/api/test_card_endpoint.py`, `tests/recommend/test_violations.py` |
| Product-card calculation, product bound in admin or auto-bound | `service/room_calc.plan_product`, `engine/geometry.WallSurface` | `POST/GET /api/v1/product/{id}/calc` (`id` = Bagisto id) | `tests/api/test_card_endpoint.py`, `tests/e2e/test_demo.py` |
| Key link: admin binds products, ML automates binding | `ml/match.py`, `api/state.py` (overrides win, survive re-match) | `GET /api/v1/catalog/products`, `…/review-queue`, `POST …/review/{sku}`, `POST …/rematch`, `POST …/catalog/match` | `tests/api/test_overrides.py`, `tests/ml/test_matching.py` |

## ML (case §3)

| Requirement | Module | Test / metric |
|---|---|---|
| 3.1 classification / matching of catalog to work types | `ml/rules.py`, `ml/classify.py`, `ml/calibrate.py`, `ml/match.py` | `tests/ml/test_match_pipeline.py`; eval/REPORT.md (synthetic) |
| 3.1 embeddings (e5/RuBERT family vs FRIDA/bge-m3/Qwen3) | `ml/embed.py`, `ml/embed_match.py`, `scripts/embed_bench.py` | `tests/ml/test_embeddings_vectors_judge_gold.py`; baseline measured, models need the server (OPEN_QUESTIONS) |
| 3.1 LLM judge for the uncertain zone | `ml/judge.py` | same test file |
| 3.2 recommendation under constraints, ranking by rating | `recommend/select.py` (`recsys_rating`, `rating`, stock, region, margin weight) | `tests/recommend/test_select.py`, `test_margin_weight.py`, `test_violations.py` |
| 3.2 RAG: norms + recommendations → LLM explanation | `recommend/rag.py`, `knowledge/guides.yaml`, `knowledge/docs/*.md` | `POST /api/v1/estimate/{id}/explain`; `tests/ml/test_parse_and_rag.py`, `test_rag_docs.py` |
| 3.3 consumption formulas (baseline) | `engine/materials/*` | `tests/engine/*`, `tests/golden/*` (224 cases) |
| 3.3 learnable correction coefficients | `engine/materials/waste.py` (`WasteTable`), `ml/waste_fit.py`, `scripts/fit_waste.py` | `tests/ml/test_waste_fit.py`; no order data yet (OPEN_QUESTIONS) |
| 3.4 CV on floor plans | — | not in MVP (case §6) |

## Architecture (case §4), data (§5), scope (§6), stack (§7)

| Requirement | Module / file |
|---|---|
| Stateless microservice, REST/JSON, Docker | `api/`, `Dockerfile`, `docker-compose.yml` |
| ML models behind a separate inference layer | `inference/app.py` (compose service `inference`) |
| Catalog is the site's source of truth, read via API | `catalog/stand_client.py`, `catalog/adapters/maxidom_api.py`, `scripts/ingest_stand.py` |
| Catalog API: tree, categories, products (to `last_page`), full card, regions | `catalog/stand_client.py` — `tests/catalog/test_stand.py`, `test_stand_ingest.py` |
| Data rules: `id` key, `result_price`, characteristics ≠ filters, special price rule, units | `catalog/adapters/maxidom_api.py` — same tests |
| Knowledge base of consumption norms (СНиП / manufacturer) | `knowledge/guides.yaml`, `knowledge/docs/` (Ceresit CR 65, CM 11), `knowledge/norms.yaml` |
| MVP must-have: general calculator, card endpoint, ML matching on a subset, room rules | see scenarios above |
| Nice to have: RAG, admin hints, text → parameters (LLM) | `recommend/rag.py`, `/api/v1/catalog/products` + frontend admin, `POST /api/v1/parse` |
| Not in MVP: CV, production load | — |
| Stack: FastAPI, Docker, embeddings, sklearn/CatBoost, LLM+RAG, vector store | all present; vector store `ml/vectorstore.py` (numpy; pgvector later) |

## Metrics (case §8)

| Case metric | Where it is produced | Current value |
|---|---|---|
| Matching P/R/F1, target F1 ≥ 0.8 on top categories | `eval/REPORT.md`, `scripts/score_gold.py` | synthetic only; **real: not measured** |
| MAE of quantity vs reference estimates | `eval/run_eval.py` → `docs/PITCH_METRICS.md` §0 | 0.000 packs on 10 pack cases (own golden); organisers' estimates not received |
| % auto-bound without manual labeling; estimate time | `docs/PITCH_METRICS.md` §0, §3 | synthetic; see file |
| Clicks from "выбрал комнату" to "готовая корзина" | `docs/PITCH_METRICS.md` §0 | 3 |

## Demo script (case §9)

`tests/e2e/test_demo.py` runs all four steps against the mock stand with the network blocked.
Hardware / closed contour (case §10): `config.py` (Ollama URL and model from `.env`),
`docs/LLM.md` (VRAM budget), `tests/test_offline.py`.
