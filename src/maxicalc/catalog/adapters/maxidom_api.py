"""The organisers' stand API (Bagisto-style `/api/catalog/products`) -> normalized Products.

Accepts one response (`{"items": [...]}` / `{"data": {...}}` / a bare list) or a JSONL dump of
cards. Rules taken from the case brief:
  * `id` is the product key; `sku` and `cod_good` are separate identifiers kept as strings;
  * the selling price is `result_price` (never the minimum of all price fields); `price` is kept
    as `list_price`;
  * `characteristics` (full card) are the product's own values; `propertiesBottom` are display
    properties; list-level `properties` are filter facets and are NOT copied onto products;
  * package data (`quantity_in_package`, `package_area`) is exposed as the characteristics the
    extractor already understands, with the original text kept.
"""
import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from maxicalc.catalog.normalize import normalize_text
from maxicalc.catalog.schema import IngestReport, Product

_API_MARKERS = ("result_price", "cod_good", "propertiesBottom", "quantity_in_package",
                "categories_tree", "recsys_rating")


def looks_like_api(items: Iterable[Any]) -> bool:
    for it in items:
        return isinstance(it, dict) and any(k in it for k in _API_MARKERS)
    return False


def _dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _s(v: Any) -> str:
    return "" if v is None else normalize_text(str(v))


def _named(v: Any) -> str:
    """`{"id": 46, "name": "Brand"}` -> "Brand"."""
    if isinstance(v, dict):
        return _s(v.get("name"))
    return _s(v)


def category_path(item: dict[str, Any]) -> list[str]:
    tree = item.get("categories_tree")
    if isinstance(tree, list) and tree:
        ordered = sorted((c for c in tree if isinstance(c, dict)), key=lambda c: c.get("depth", 0))
        return [n for n in (_s(c.get("name")) for c in ordered) if n]
    cats = item.get("categories")
    if isinstance(cats, dict):
        return [n for n in (_s(v) for v in cats.values()) if n]
    return []


def characteristics(item: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in item.get("characteristics") or []:
        if isinstance(c, dict) and _s(c.get("name")) and _s(c.get("value")):
            out[_s(c["name"])] = _s(c["value"])
    for c in item.get("propertiesBottom") or []:
        if isinstance(c, dict) and _s(c.get("name")) and _s(c.get("value")):
            out.setdefault(_s(c["name"]), _s(c["value"]))
    qty = _dec(item.get("quantity_in_package"))
    area = _dec(item.get("package_area"))
    if qty is not None and qty > 0:
        out.setdefault("Количество в упаковке", f"{qty.normalize():f} шт")
    if area is not None and area > 0:
        out.setdefault("Площадь упаковки", f"{area.normalize():f} м2")
    return out


def _when(v: Any) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("T", " "))
    except ValueError:
        return None


def effective_special_price(item: dict[str, Any], now: datetime | None = None) -> Decimal | None:
    """`special_price` counts only when `special_price_active` is true and `now` is inside
    [special_price_from, special_price_to] (an empty bound is open). The brief warns against
    picking the minimum of all price fields: this value is exposed, never substituted for
    `result_price`."""
    if item.get("special_price_active") is not True:
        return None
    sp = _dec(item.get("special_price"))
    if sp is None:
        return None
    t = now or datetime.now()
    start, end = _when(item.get("special_price_from")), _when(item.get("special_price_to"))
    if (start and t < start) or (end and t > end):
        return None
    return sp


def item_to_product(item: dict[str, Any], now: datetime | None = None) -> Product | None:
    pid, sku, name = _s(item.get("id")), _s(item.get("sku")), _s(item.get("name"))
    key = sku or _s(item.get("cod_good")) or pid
    if not key or not name:
        return None
    regions: dict[str, Decimal] = {}
    for st in item.get("stocks") or []:
        if isinstance(st, dict) and st.get("region_id") is not None:
            q = _dec(st.get("qty")) or Decimal(0)
            rid = str(st["region_id"])
            regions[rid] = regions.get(rid, Decimal(0)) + q
    rating = item.get("ratings")
    desc = " ".join(p for p in (_s(item.get("description")), _s(item.get("marketing_description")))
                    if p)
    price = _dec(item.get("result_price"))
    list_price = _dec(item.get("price"))
    return Product(
        sku=key, name=name, category_path=category_path(item),
        brand=_named(item.get("brand")) or None,
        price=price if price is not None else list_price,
        description=desc, characteristics=characteristics(item),
        url=_s(item.get("url_key")) or None, unit=_s(item.get("unit")) or None,
        product_id=pid or None, cod_good=_s(item.get("cod_good")) or None,
        list_price=list_price, special_price=effective_special_price(item, now),
        quantity_in_package=_dec(item.get("quantity_in_package")),
        package_area_m2=_dec(item.get("package_area")), price_per_m2=_dec(item.get("price_per_m2")),
        in_stock=item.get("in_stock") if isinstance(item.get("in_stock"), bool) else None,
        stock_qty=_dec(item.get("qty")), stock_regions=regions,
        rating=_dec(rating.get("rating")) if isinstance(rating, dict) else None,
        recsys_rating=_dec(item.get("recsys_rating")),
        active=item.get("status") if isinstance(item.get("status"), bool) else None,
    )


def items_to_products(items: Iterable[dict[str, Any]], report: IngestReport) -> list[Product]:
    out: dict[str, Product] = {}   # de-duplicated by Bagisto id, as the brief asks
    for n, it in enumerate(items, start=1):
        report.read += 1
        p = item_to_product(it)
        if p is None:
            report.skipped += 1
            report.add_issue(f"позиция {n}: нет артикула/id или наименования, пропущена")
            continue
        out[p.product_id or p.sku] = p
        report.loaded += 1
    if len(out) < report.loaded:
        report.add_issue(f"повторы по id удалены: {report.loaded - len(out)}")
        report.loaded = len(out)
    return list(out.values())


def api_items(path: Path, text: str) -> Iterator[dict[str, Any]]:
    """Yield product dicts from a response file or a JSONL dump."""
    if path.suffix.lower() == ".jsonl":
        for line in text.splitlines():
            line = line.strip()
            if line:
                yield from _unwrap(json.loads(line))
        return
    yield from _unwrap(json.loads(text))


def _unwrap(obj: Any) -> Iterator[dict[str, Any]]:
    if isinstance(obj, list):
        for x in obj:
            if isinstance(x, dict):
                yield x
    elif isinstance(obj, dict):
        for key in ("items", "products"):
            if isinstance(obj.get(key), list):
                yield from _unwrap(obj[key])
                return
        data = obj.get("data")
        if isinstance(data, list):
            yield from _unwrap(data)
        elif isinstance(data, dict):
            inner = data.get("items")
            yield from _unwrap(inner if isinstance(inner, list) else [data])
        else:
            yield obj
