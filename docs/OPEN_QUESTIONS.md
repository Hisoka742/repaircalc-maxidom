# Open questions for the organizers

Each question lists the assumption the code currently makes, where it is configurable, and what
it blocks. Ask them in the case chat; when an answer arrives, change the setting and delete the
assumption here.

| # | Question | Assumption in the code | Where to change | Blocks |
|---|---|---|---|---|
| 1 | Base URL and auth for the catalog stand. When does access open? | A `STAND_BASE_URL` (+ optional `STAND_TOKEN`) is the only difference between the mock and the real stand. The client has never run against the real stand. | `.env`: `STAND_BASE_URL`, `STAND_TOKEN`; `catalog/stand_client.py` | Real-data ingest, every real-catalog metric (F1, auto share, readiness), the gold set |
| 2 | How is the region context chosen for `result_price` and stock? | Price shown = `result_price` as returned. Stock is filtered by `region_id` only when the caller gives one; `StandClient.default_region_id()` returns the region flagged `is_default`. | `.env`: `STAND_REGION_ID`; `recommend/select.py` (`Constraints.region_id`) | Correct regional prices and availability |
| 3 | Is there a **margin** field for ranking? | No margin field exists. The ranking weight is `margin_weight = 0` (inactive); `Product.margin` (0..1) is read when present. | `.env`: `MARGIN_WEIGHT`; adapter mapping in `catalog/adapters/maxidom_api.py` | Margin-aware ranking (case §3.2) |
| 4 | Is there **order data** to learn the waste/cutting coefficients? | No. The shipped `WasteTable` is the norm defaults and says so in every `explain`. | `knowledge/waste_coefficients.yaml`; `scripts/fit_waste.py orders.csv` | Case §3.3 "learned coefficients" with real data |
| 5 | Will **reference estimates** be provided to measure the quantity MAE? | MAE is measured against our own golden cases (independent re-derivations + 16 manufacturer-sheet cases). | `GOLDEN_EXTRA=<file>` (same format) | The case's accuracy metric on organiser references |
| 6 | Closed-loop server: may we run our own Docker containers next to Ollama, or only Ollama models? Which Ollama version? | Our containers run next to Ollama (`docker-compose.yml`); the LLM is reached only through Ollama's OpenAI-compatible API; embeddings through Ollama `/api/embed` or the `inference` service. If only Ollama is allowed, run the API on the same host without compose. | `.env`: `LLM_BASE_URL`, `LLM_MODEL`, `EMBEDDER` | Deployment shape; which embedding models can be benchmarked |
| 7 | Is code written before 7 Nov allowed? | Assumed yes (it already exists). | — | Everything, if the answer is no |
| 8 | Labor rates: is there a price list for works (₽/m², ₽/m, ₽/point) and class multipliers? | None. `knowledge/work_rates.yaml` has no values, so labor is never estimated and the response says why (`labor_note`). Public contractor listings were found but are minimums from individual contractors, not a source we can cite. | `knowledge/work_rates.yaml` (value + `source` required) | Labor cost range in the estimate (checklist C7) |
| 9 | Which `characteristics` codes carry consumption, pack size and tile/roll dimensions in the real cards? | Names are matched by Russian text ("Площадь упаковки", "Расход"...), plus package fields of the API. | `ml/extract.py` (`CHAR_KEYS`) | Calculator readiness on the real catalog |
| 10 | Do `propertiesBottom` values ever contradict `characteristics`? | `characteristics` win; `propertiesBottom` only fills gaps. | `catalog/adapters/maxidom_api.py` | Data quality |
