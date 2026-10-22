"""Smoke checks against a running API (httpx.Client with base_url, or a Starlette TestClient).

Every check is independent: a failure is reported with a reason and the rest still run, so the
operator sees the full picture in one pass.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ROOM = {"room": {"length_m": "4", "width_m": "3", "height_m": "2.7"}, "room_type": "living",
        "renovation_class": "cosmetic"}


@dataclass
class SmokeResult:
    name: str
    ok: bool
    detail: str = ""


def run_smoke(c: Any) -> list[SmokeResult]:
    out: list[SmokeResult] = []
    state: dict[str, Any] = {}

    def check(name: str, fn: Callable[[], str]) -> None:
        try:
            out.append(SmokeResult(name, True, fn()))
        except Exception as e:  # report and carry on
            out.append(SmokeResult(name, False, str(e) or type(e).__name__))

    def need(resp: Any, code: int = 200) -> Any:
        if resp.status_code != code:
            body = resp.text[:200] if hasattr(resp, "text") else ""
            raise AssertionError(f"HTTP {resp.status_code}: {body}")
        return resp

    def health() -> str:
        j = need(c.get("/health")).json()
        state["catalog_size"] = j["catalog_size"]
        if j["catalog_size"] == 0:
            raise AssertionError("каталог пуст (CATALOG_PATH не задан или файл не загрузился)")
        return f"{j['catalog_size']} товаров, версия {j['catalog_version']}"

    def recommend() -> str:
        for calc in ("paint", "laminate", "tile", "wallpaper", "drywall"):
            j = need(c.post("/v1/recommend", json={"room_type": "living", "calc": calc,
                                                    "top_k": 3})).json()
            if j["items"]:
                state["sku"], state["calc"] = j["items"][0]["sku"], calc
                return f"{calc}: {len(j['items'])} товаров, первый {j['items'][0]['sku']}"
        raise AssertionError("не найден ни один товар для типовых запросов (каталог пуст "
                             "или не размечен)")

    def calc_room() -> str:
        j = need(c.post("/v1/calc/room", json=ROOM)).json()
        state["estimate_id"] = j["estimate_id"]
        return f"{len(j['basket']['lines'])} позиций, итого {j['basket']['materials_total']} ₽, " \
               f"предупреждений {len(j['warnings'])}"

    def calc_property() -> str:
        j = need(c.post("/v1/calc/property", json={
            "property_type": "apartment", "total_area_m2": "60",
            "renovation_class": "cosmetic"})).json()
        return f"{len(j['basket']['lines'])} позиций, итого {j['basket']['materials_total']} ₽"

    def product_quantity() -> str:
        if "sku" not in state:
            raise AssertionError("нет SKU из шага recommend")
        j = need(c.post(f"/v1/products/{state['sku']}/quantity", json={
            "room": ROOM["room"], "room_type": "living"})).json()
        if not j["basket"]["lines"]:
            raise AssertionError(f"нет позиций; предупреждения: {j['warnings'][:2]}")
        return f"{state['sku']}: {j['basket']['lines'][0]['qty_packs']} уп."

    def match() -> str:
        j = need(c.post("/v1/catalog/match", json={"products": [
            {"sku": "smoke", "name": "Обои флизелиновые 1,06х10,05 м",
             "category_path": ["Обои"]}]})).json()
        label = j["results"][0]["calc_template"]["label"]
        if label != "wallpaper":
            raise AssertionError(f"ожидался wallpaper, получено {label}")
        return "wallpaper → auto"

    def review() -> str:
        j = need(c.get("/v1/catalog/review-queue?limit=5")).json()
        return f"в очереди (первые 5): {len(j)}"

    def export() -> str:
        if "estimate_id" not in state:
            raise AssertionError("нет estimate_id из шага calc/room")
        r = need(c.post(f"/v1/estimate/{state['estimate_id']}/export?format=xlsx"))
        if not r.content.startswith(b"PK"):
            raise AssertionError("ответ не похож на XLSX")
        return f"{len(r.content)} байт"

    def metrics() -> str:
        t = need(c.get("/metrics")).text
        if "http_requests_total" not in t:
            raise AssertionError("нет метрик")
        return "ok"

    check("health", health)
    check("recommend", recommend)
    check("calc/room", calc_room)
    check("calc/property", calc_property)
    check("product quantity", product_quantity)
    check("catalog/match", match)
    check("review-queue", review)
    check("export xlsx", export)
    check("metrics", metrics)
    return out
