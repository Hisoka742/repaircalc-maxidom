"""Shared row -> Product mapping. Format adapters only produce dict rows."""
import re
from collections.abc import Iterable, Mapping
from typing import Any

from maxicalc.catalog.normalize import normalize_text, parse_number, split_category_path
from maxicalc.catalog.schema import IngestReport, Product

ALIASES: dict[str, tuple[str, ...]] = {
    "sku": ("sku", "артикул", "код", "код товара", "id", "offer id", "offer_id",
            "артикул товара", "артикул поставщика", "код номенклатуры", "код 1с", "арт."),
    "name": ("name", "наименование", "название", "товар", "title", "номенклатура",
             "наименование товара", "название товара", "полное наименование"),
    "category": ("category", "категория", "раздел", "путь", "category_path", "группа",
                 "группа товаров", "раздел каталога", "категория товара", "иерархия",
                 "номенклатурная группа"),
    "brand": ("brand", "бренд", "производитель", "vendor", "торговая марка", "марка"),
    "price": ("price", "цена", "стоимость", "розничная цена", "цена, руб", "цена, руб.",
              "цена руб", "цена с ндс", "цена розничная", "цена продажи"),
    "description": ("description", "описание", "описание товара", "краткое описание"),
    "url": ("url", "ссылка", "link", "ссылка на товар"),
    "image_url": ("image", "image_url", "picture", "фото", "изображение", "ссылка на фото"),
    "in_stock": ("in_stock", "available", "в наличии"),
    "unit": ("unit", "ед. изм.", "ед.изм.", "единица", "единица измерения", "ед изм"),
}
_LOOKUP = {alias: field for field, al in ALIASES.items() for alias in al}
_UNIT_SUFFIX = re.compile(r"\s*[,(].*$")


def field_for(header: str) -> str | None:
    """Canonical field for a column header; tolerates unit/qualifier suffixes
    ("Розничная цена, руб." -> "розничная цена")."""
    key = normalize_text(str(header)).lower()
    if key in _LOOKUP:
        return _LOOKUP[key]
    return _LOOKUP.get(_UNIT_SUFFIX.sub("", key))


def map_headers(headers: Iterable[str]) -> tuple[dict[str, str], list[str]]:
    """(header -> canonical field for recognised columns, unrecognised headers).

    Unrecognised columns are not lost (they become product characteristics); this only helps
    diagnose a catalog whose key columns (sku / name) use names we do not know yet."""
    mapped: dict[str, str] = {}
    unmapped: list[str] = []
    for h in headers:
        f = field_for(h)
        if f is not None:
            mapped[normalize_text(str(h))] = f
        else:
            unmapped.append(normalize_text(str(h)))
    return mapped, unmapped


def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return normalize_text(str(v))


def _flag(v: str | None) -> bool | None:
    if not v:
        return None
    return v.strip().lower() in ("true", "1", "да", "yes", "y")


def rows_to_products(
    rows: Iterable[Mapping[str, Any]], report: IngestReport
) -> list[Product]:
    out: list[Product] = []
    for n, row in enumerate(rows, start=2):  # row 1 is the header
        report.read += 1
        core: dict[str, str] = {}
        chars: dict[str, str] = {}
        for key, val in row.items():
            if key is None:
                continue
            k = normalize_text(str(key))
            fld = field_for(k)
            if fld is not None:
                core[fld] = _s(val)
            elif k.lower() in ("characteristics", "характеристики") and isinstance(val, dict):
                chars.update({normalize_text(str(a)): _s(b) for a, b in val.items() if _s(b)})
            elif _s(val):
                chars[k] = _s(val)
        if not core.get("sku"):
            report.skipped += 1
            report.add_issue(f"строка {n}: нет артикула (sku), пропущена")
            continue
        if not core.get("name"):
            report.skipped += 1
            report.add_issue(f"строка {n}: нет наименования (name), пропущена")
            continue
        price = None
        if core.get("price"):
            try:
                price = parse_number(core["price"])
            except ValueError:
                report.add_issue(f"строка {n}: цена не распознана: {core['price']!r}")
        out.append(Product(
            sku=core["sku"], name=core["name"],
            category_path=split_category_path(core.get("category", "")),
            brand=core.get("brand") or None, price=price,
            description=core.get("description", ""), characteristics=chars,
            url=core.get("url") or None, image_url=core.get("image_url") or None,
            unit=core.get("unit") or None,
            in_stock=_flag(core.get("in_stock")),
        ))
        report.loaded += 1
    return out
