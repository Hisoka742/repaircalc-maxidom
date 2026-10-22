# MaksiDom Smart Repair Calculator — API v1

Base URL: `http://<host>:8000`. Interactive docs: `/docs` (Swagger), schema: `/openapi.json`.
All user-facing text is Russian. No authentication (internal microservice; put it behind the
site's gateway).

## Principles

* **Quantities come from a deterministic engine** (`Decimal`, no ML/LLM arithmetic). Packs are
  rounded up **once, at the very end**, after summing the need of all rooms per SKU in base units.
* Every basket line carries `explain` (calculation trace) and `reason` (why this product).
* **Honesty over completeness:** if a product card lacks data a formula needs, the line is
  skipped and a `warnings[]` entry says what is missing. Defaults the engine had to assume are
  listed in `assumptions[]`. Labor cost is `null` (no sourced rates yet) with a warning.
* JSON money/quantities that are not integers are **strings** (exact decimals).

## Endpoints

| Method & path | Purpose |
|---|---|
| `POST /v1/calc/property` | Property type + area + renovation class → rooms → materials basket |
| `POST /v1/calc/room` | One room with real geometry (openings, L-shapes) → materials basket |
| `POST /v1/products/{sku}/quantity` | Product-card calculator: packs of *this* SKU + companion items |
| `POST /v1/recommend` | Products for a room type / need, ranked, with reasons and exclusions |
| `POST /v1/catalog/match` | Label products (calc template, work categories, rooms, properties) |
| `GET /v1/catalog/jobs/{id}` | Result of a large match batch (> `SYNC_MATCH_LIMIT`, HTTP 202) |
| `GET /v1/catalog/review-queue` | Low-confidence items for human review (least confident first) |
| `POST /v1/catalog/review/{sku}` | Confirm / correct labels; updates the live catalog |
| `POST /v1/estimate/{id}/export?format=xlsx\|pdf` | B2B смета |
| `GET /health`, `GET /metrics` | Ops (Prometheus text format) |

### `POST /v1/calc/property`

```json
{ "property_type": "apartment", "total_area_m2": "60", "renovation_class": "cosmetic",
  "tier": "standard" }
```
`property_type`: `apartment | studio | house`. `renovation_class`: `cosmetic | major | designer`
(`designer` defaults to the `premium` tier). `tier`: `economy | standard | premium`.
Optional `rooms: [{room_type, area_m2, height_m?}]` replaces the preset room layout;
`ceiling_height_m` overrides the default 2.7 m.

### `POST /v1/calc/room`

```json
{ "room": { "length_m": "4", "width_m": "3", "height_m": "2.5",
            "openings": [{"kind": "door", "width_m": "0.9", "height_m": "2.05", "wall": 0}] },
  "room_type": "living", "renovation_class": "cosmetic", "include_ceiling": true }
```
Use `vertices: [[x, y], ...]` (metres) instead of `length_m`/`width_m` for non-rectangular rooms.
`wall` is the index of the edge starting at vertex `wall`. `room_type`:
`living | bedroom | kitchen | bathroom | kids | hallway | balcony`.

### `POST /v1/products/{sku}/quantity`

Same `room` geometry plus `room_type`. Supported product types: paint, primer, putty, wallpaper,
laminate, underlay, skirting, tile (adds adhesive and grout), self-leveling mix, waterproofing.
A product that breaks a room rule (e.g. non-washable paint for a kitchen) is still calculated,
with a warning explaining why it is not recommended.

### `POST /api/v1/product/{id}/calc` (and `GET`)

The product-card calculator from the case brief. `{id}` is the stand's product `id` (an article
`sku` also works). The customer types the dimensions of ONE surface or a whole room; exactly one of:

```json
{"wall": {"width_m": "4.2", "height_m": "2.6"}}
{"floor": {"length_m": "4", "width_m": "3"}}
{"room": {"length_m": "4", "width_m": "3", "height_m": "2.7"}, "room_type": "kitchen"}
```

Optional: `room_type` (default `living`), `humidity: "high"`, `load: "high"`. A wall for a floor
product (laminate, underlay, skirting, self-leveling, waterproofing) or a floor for a wall product
(paint, primer, putty, wallpaper) is a 422 with a plain Russian message. The response is the same
estimate object as the other calculators (the chosen product first, then companions), with `explain`.
`GET` takes `wall_width_m`, `wall_height_m`, `floor_length_m`, `floor_width_m`, `room_type`,
`humidity` as query parameters for embedding without a JS client.

### `POST /v1/parse`

Free text -> calculator input. `{"text": "Квартира, капитальный ремонт, санузел 6 м², высокая
влажность"}` returns `property_type`, `renovation_class`, `tier`, `total_area_m2`, `rooms[]`
(`room_type`, `area_m2`, `humidity`), `missing[]` (what must be asked), `ready` and `method`
(`rules` or `llm`). Rules run first; the local LLM is used only when the rules find no room, and its
output is validated like rule output (unknown room types and implausible areas are dropped).

### `POST /v1/estimate/{estimate_id}/explain`

"Why these materials": retrieval over `knowledge/guides.yaml` by product type, room and overlay,
then the local LLM phrases it. `method` says which path produced the text: `llm`, or `template`
(model unavailable, cited an unknown fact, or named a number that is not in the data). The model
never calculates.

### Humidity and load

`humidity: "high"` on a room (property `rooms[]`, room calc, product card, recommend) applies the
`wet_zone` overlay of `room_rules.yaml` whatever the room is called; `load: "high"` applies
`heavy_traffic`. Overlays only add requirements. Capital and designer renovation also line the
walls of wet rooms with moisture-resistant drywall (`walls_drywall`).

### `GET /v1/catalog/products`

Catalog with labels for the admin page: `q` (name, article or id), `status`
(`auto|review|verified`), `calc`, `limit`, `offset`. Returns `total` and items with `product_id`,
`calc`, `work_categories`, `room_types`, `properties`, `status`, extracted `attributes`.

### Estimate response (all three calculators)

```json
{ "estimate_id": "95087c2ec9320166", "kind": "room", "catalog_version": "a310cf66bc10",
  "rooms": [{"room_type": "living", "area_m2": "12", "height_m": "2.5"}],
  "basket": {
    "lines": [{ "sku": "P1", "name": "...", "qty_packs": 4, "unit": "уп",
                "unit_price": "1000", "line_total": "4000",
                "reason": "подходит для гостиной", "explain": ["..."],
                "alternatives": [{"sku": "P2", "name": "...", "price": "900"}] }],
    "materials_total": "17300" },
  "labor": null, "warnings": ["Ставки работ не заданы — стоимость работ не рассчитана"],
  "assumptions": [], "electrical": [], "cached": false }
```

**Idempotency.** `estimate_id` is a hash of the canonical request and the catalog version, so
the same request always gives the same id and result (`cached: true` on repeats). When the
catalog changes (re-match, review feedback) the version and ids change.

### `POST /v1/recommend`

```json
{ "room_type": "bathroom", "calc": "drywall", "tier": "standard", "top_k": 5 }
```
Provide `calc` (product type) or `work_category`. Optional `max_price`, `min_price`, `brands`.
The response lists `items` (with `score`, `reasons`, `price_tier`), `excluded` (up to 50 SKUs
with the reason, e.g. "В ванной нужен влагостойкий гипсокартон (ГКЛВ)") and `warnings`.
Hard room rules are never relaxed: if nothing qualifies you get an empty list and a warning.

### `POST /v1/catalog/match`

`{"products": [{"sku", "name", "category_path", "brand", "price", "description",
"characteristics"}]}` → per product: `status` (`auto` | `review`), `calc_template`,
`work_categories`, `room_types`, `properties` (each with `confidence`, `source`
`rule|model`, `accepted`, `reason`) and extracted `attributes`. Batches above
`SYNC_MATCH_LIMIT` (default 500) return **202** `{job_id}` — poll `/v1/catalog/jobs/{id}`.

### Export

`POST /v1/estimate/{estimate_id}/export?format=xlsx|pdf` returns the file for an estimate
calculated earlier (404 if it expired from the cache — recalculate). PDF needs a Cyrillic
TTF (`PDF_FONT_PATH`, or DejaVu on Linux / Arial on Windows); without one the endpoint
answers **501** with an explanation.

## Errors

Every error: `{"error": {"code", "message", "details": [{"field", "message"}]}}`, in Russian.

| HTTP | code | when |
|---|---|---|
| 422 | `validation_error` | bad/missing fields (`details` per field) |
| 422 | `invalid_request` | well-formed but impossible (e.g. "Проёмы шире стены") |
| 404 | `http_404` | unknown SKU / estimate / job |
| 429 | `rate_limited` | per-IP token bucket; `Retry-After` header |
| 501 | `http_501` | PDF without a Cyrillic font |
| 500 | `internal_error` | bug; logged with `request_id` |

Each response has `X-Request-ID` (send your own to correlate logs).

## Configuration (env / `.env`)

| Variable | Default | Meaning |
|---|---|---|
| `CATALOG_PATH` | – | CSV / XLSX / JSON / YML catalog loaded and matched at startup |
| `MODEL_PATH` | – | trained `MatchModel` (joblib); without it only rules label products |
| `REDIS_URL` | – | shared estimate cache; unreachable → falls back to in-memory with a warning |
| `RATE_LIMIT_PER_MIN` / `RATE_LIMIT_BURST` | 600 / 100 | per-IP limit; `0` disables |
| `CACHE_MAX_ITEMS`, `CACHE_TTL_S` | 5000, 86400 | in-memory cache size / lifetime |
| `SYNC_MATCH_LIMIT` | 500 | larger match batches become background jobs |
| `PDF_FONT_PATH` | – | Cyrillic TTF for PDF export |

Multi-worker deployments need `REDIS_URL`: with per-process memory caches an export request
can reach a worker that has not seen the estimate.

## Observability

Structured JSON access logs (`request_id`, `method`, `path`, `status`, `ms`); Prometheus at
`/metrics`: `http_requests_total`, `http_request_duration_seconds`, `estimate_cache_total`,
`rate_limited_total`, `catalog_products`, `review_queue_pending`.

## Known limitations

* Catalog state is held in memory (loaded at startup from `CATALOG_PATH`); PostgreSQL/pgvector
  is not wired in yet.
* No authentication; no labor prices; wallpaper is available only through the product-card
  calculator, not the renovation-class presets; the estimate path buys a single SKU per need
  (the multi-size pack optimizer in the engine is not used there yet).
