# Integrating the calculator into a Bitrix site

The service is a stateless REST/JSON microservice. The site keeps the catalog; the service gets it
by export or from the stand API. Everything below is under `/api/v1`; the original `/v1/...` paths
remain as aliases. CORS is open to the origins in `CORS_ORIGINS` (default `*`; set the shop's
origin in production).

## 1. Product card: "how many do I need?"

`{id}` is the product's **id in the catalog** (Bagisto/Bitrix element id the stand returns), not the
article. Put this in the product template (`/bitrix/templates/.../catalog.element/template.php`),
with `PRODUCT_ID` taken from the element:

```html
<div id="rc-calc" data-product="<?= (int)$arResult['ID'] ?>">
  <label>Ширина стены, м <input id="rc-w" type="number" step="0.1" value="4"></label>
  <label>Высота, м <input id="rc-h" type="number" step="0.1" value="2.6"></label>
  <div id="rc-out"></div>
</div>
<script>
(function () {
  var API = 'https://calc.example.ru';          // the service origin
  var box = document.getElementById('rc-calc'), out = document.getElementById('rc-out');
  var timer;
  function calc() {
    var body = JSON.stringify({wall: {width_m: document.getElementById('rc-w').value,
                                       height_m: document.getElementById('rc-h').value}});
    fetch(API + '/api/v1/product/' + box.dataset.product + '/calc', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: body
    }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.error) { out.textContent = j.error.message; return; }
      var l = j.basket.lines[0];
      out.textContent = 'Нужно: ' + l.qty_packs + ' ' + l.unit + ', ' +
                        l.line_total + ' ₽ (' + l.explain.join('; ') + ')';
    });
  }
  box.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(calc, 250); });
  calc();
})();
</script>
```

Request variants (exactly one): `{"wall": {"width_m", "height_m"}}` · `{"floor": {"length_m",
"width_m"}}` · `{"room": {"length_m", "width_m", "height_m", "openings": [...]}, "room_type"}`.
Optional: `humidity: "high"`. Money and quantities are **strings** (exact decimals).
Errors: HTTP 422 with `{"error": {"message": "...по-русски...", "details": [...]}}`; 404 when the
id is not in the catalog; a product without a calculator template gives a 422 that says so.

## 2. Room estimate / basket

```js
fetch(API + '/api/v1/calc/property', {method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({property_type: 'apartment', total_area_m2: '60',
                        renovation_class: 'major',
                        rooms: [{room_type: 'bathroom', area_m2: '6', humidity: 'high'}]})})
```

The response has `basket.lines[]` (`product_id`, `sku`, `url`, `qty_packs`, `unit`,
`unit_price`=`result_price`, `line_total`, `reason`, `explain`, `alternatives`, `group`,
`optimized`), `basket.groups[]` (floor / walls / wallpaper / electrical), `warnings`,
`assumptions`, `labor` (low/expected/high from the market benchmark in `work_rates.yaml`, labelled «рыночный ориентир, уточняется у Максидом»; null for classes without a sourced multiplier, `labor_note` says why; replace by official rates when provided, question #8).
Add the lines to the Bitrix basket by `product_id`. `POST /api/v1/estimate/{id}/export?format=xlsx|pdf`
returns the B2B estimate.

## 3. Free text → parameters

`POST /api/v1/parse {"text": "санузел 6 м², высокая влажность"}` → structured rooms plus `missing[]`
(what to ask the user). Works without the LLM (rules); the local model is only a fallback.

## 4. Operations

* `GET /health` (liveness), `GET /ready` (200 only with a catalog loaded), `GET /metrics`
  (Prometheus). Rate limit per client IP: `RATE_LIMIT_PER_MIN`.
* Catalog changed on the site: re-export it (or `scripts/ingest_stand.py`), then
  `POST /api/v1/catalog/rematch`. Human bindings from the admin always win over ML.
* Calculations never depend on the LLM: with Ollama down, estimates are identical and the
  explanation falls back to a template (`method: "template"`).
