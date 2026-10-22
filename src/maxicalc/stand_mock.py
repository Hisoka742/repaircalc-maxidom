"""A stand-in for the organisers' catalog API, built from any normalized catalog.

Serves the same five endpoints and field names as the case brief (`/api/catalog/categories/tree`,
`/api/catalog/categories`, `/api/catalog/products`, `/api/catalog/products/{id}`, `/api/regions`),
so the client, the adapter and the whole pipeline can be exercised end to end before the real
stand is reachable. Data is whatever catalog it is built from (the demo one is SYNTHETIC).

    uv run uvicorn maxicalc.stand_mock:app --port 9000   # needs STAND_MOCK_CATALOG=<file>
"""
import os
import re
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from maxicalc.catalog.schema import Product

_AREA = re.compile(r"в\s*упаковке\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*м2", re.IGNORECASE)
REGIONS = [
    {"id": 1, "code": "msk", "name": "Москва", "oracle_cod_city": 1, "priority": 0,
     "status": True, "is_default": True, "warehouses_count": 2},
    {"id": 2, "code": "spb", "name": "Санкт-Петербург", "oracle_cod_city": 2, "priority": 1,
     "status": True, "is_default": False, "warehouses_count": 1},
]


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def to_item(p: Product, n: int, cat_ids: dict[tuple[str, ...], int]) -> dict[str, Any]:
    """One Bagisto-style product (list shape). Deterministic from the product and its index."""
    price = p.price if p.price is not None else Decimal(0)
    area = None
    m = _AREA.search(p.description or "")
    if m:
        area = _num(m.group(1))
    path = tuple(p.category_path)
    tree = [{"id": cat_ids[path[: i + 1]], "name": name, "depth": i + 1}
            for i, name in enumerate(path)]
    qty = 12 + (n * 7) % 40
    rating = round(3.6 + ((n * 13) % 15) / 10, 1)
    return {
        "id": 100000 + n, "sku": p.sku, "cod_good": f"{900000 + n}", "name": p.name,
        "marketing_description": p.description, "type": "simple",
        "url_key": f"/catalog/item-{100000 + n}/",
        "price": float(price * Decimal("1.1")), "result_price": float(price), "currency": "RUB",
        "quantity_in_package": 1 if area else None, "package_area": area,
        "price_per_m2": round(float(price) / area, 2) if area else None,
        "price_per_m2_unit": "₽/м2" if area else None,
        "qty": qty, "stocks": [{"warehouse_id": 1, "warehouse_name": "Склад 1", "region_id": 1,
                                "qty": qty}],
        "in_stock": True, "status": True,
        "brand": {"id": 1, "name": p.brand} if p.brand else None,
        "categories": {str(t["id"]): t["name"] for t in tree[-1:]},
        "categories_tree": tree, "unit": "упак.", "matrix_type": 1,
        "is_purchasable_online": True, "ratings": {"rating": rating},
        "recsys_rating": round(0.5 + ((n * 29) % 100) / 100, 6),
        "propertiesBottom": [], "created_at": "2026-01-15 12:00:00",
    }


def build_stand_app(products: list[Product]) -> FastAPI:
    cat_ids: dict[tuple[str, ...], int] = {}
    parent: dict[int, int] = {}
    for p in products:
        path = tuple(p.category_path) or ("Без категории",)
        p.category_path = list(path)
        for i in range(len(path)):
            key = path[: i + 1]
            if key not in cat_ids:
                cat_ids[key] = 100 + len(cat_ids)
                parent[cat_ids[key]] = cat_ids[key[:-1]] if i else 1
    items = [to_item(p, n, cat_ids) for n, p in enumerate(products)]
    by_id = {str(it["id"]): it for it in items}
    cards = {str(100000 + n): {**items[n], "description": p.description,
                               "weight": None, "updated_at": "2026-09-01 12:00:00",
                               "characteristics": [{"code": f"c{i}", "name": k, "value": v}
                                                   for i, (k, v) in enumerate(
                                                       p.characteristics.items())]}
             for n, p in enumerate(products)}
    own: dict[int, list[dict[str, Any]]] = {}
    for it in items:
        own.setdefault(it["categories_tree"][-1]["id"] if it["categories_tree"] else 1,
                       []).append(it)

    def node(cid: int, name: str, depth: int) -> dict[str, Any]:
        kids = [(k, c) for k, c in cat_ids.items() if parent.get(c) == cid and len(k) == depth + 1]
        count = len(own.get(cid, []))
        child_nodes = [node(c, k[-1], depth + 1) for k, c in kids]
        return {"id": cid, "parent_id": parent.get(cid, 0), "name": name, "url_key": f"c{cid}",
                "status": True, "depth_level": depth, "product_count": count,
                "product_count_all_children": count + sum(
                    c["product_count_all_children"] for c in child_nodes),
                "children": child_nodes}

    roots = [node(c, k[0], 1) for k, c in cat_ids.items() if len(k) == 1]
    app = FastAPI(title="Stand mock (synthetic)")

    @app.get("/api/catalog/categories/tree")
    def tree(category_id: int = 1, depth_level: int = 20, locale: str = "ru") -> dict[str, Any]:
        return {"data": roots}

    @app.get("/api/catalog/categories")
    def categories(parent_id: int = 1, depth_level: int = 2) -> dict[str, Any]:
        flat = [{"id": c, "parent_id": parent.get(c), "name": k[-1], "url_key": f"c{c}",
                 "status": True, "depth_level": len(k), "description": "", "is_hide": "no",
                 "dat_show_b": None, "dat_show_e": None,
                 "product_count": len(own.get(c, [])),
                 "product_count_all_children": len(own.get(c, []))}
                for k, c in cat_ids.items()]
        return {"data": flat}

    @app.get("/api/catalog/products")
    def products_ep(
        category_id: int | None = None, include_subsections: int = 0,
        include_categories_tree: int = 1, per_page: int = Query(20, ge=1, le=500),
        page: int = Query(1, ge=1), locale: str = "ru",
    ) -> dict[str, Any]:
        pool = items if category_id is None else own.get(category_id, [])
        total = len(pool)
        last = max(1, -(-total // per_page))
        chunk = pool[(page - 1) * per_page: page * per_page]
        return {"items": chunk, "properties": [], "generated_url": "/",
                "meta": {"total": total, "per_page": per_page, "current_page": page,
                         "last_page": last}}

    @app.get("/api/catalog/products/{product_id}")
    def card(product_id: str, locale: str = "ru") -> dict[str, Any]:
        if product_id not in cards:
            raise HTTPException(404, "Товар не найден")
        return {"data": cards[product_id]}

    @app.get("/api/regions")
    def regions() -> dict[str, Any]:
        return {"data": REGIONS}

    app.state.items_by_id = by_id
    return app


def _from_env() -> FastAPI:
    path = os.environ.get("STAND_MOCK_CATALOG")
    if not path:
        return FastAPI(title="Stand mock (set STAND_MOCK_CATALOG)")
    from maxicalc.catalog.adapters import load_catalog

    return build_stand_app(load_catalog(path)[0])


app = _from_env()
