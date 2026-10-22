"""The organisers' official dataset `products_final.json` ({"products": [...]}, ~89k items, 274 MB).

Streamed with ijson (constant memory for the parse; only the normalized Products are kept).
Mapping (verified on the file, see docs/DATASET_REPORT.md):
  * `id` is the primary key (-> Product.product_id); `cod_good` is the sku (44 codes repeat: the
    repeats get `<cod_good>#<id>` so that sku stays unique), `id` is the last resort;
  * `price` is the selling price (this dump has no result_price / special prices / stocks);
  * `categories` holds exactly one {id: leaf name} and there is NO tree: the leaf is lifted onto
    the YML feed's tree (catalog/taxonomy_lift.py, 99% of products), else the path is [leaf];
  * `characteristics` and the `description` text ("Key: value<br>...") are BOTH parsed and merged
    (characteristics win on conflict); description is sometimes the only source;
  * values are bare numbers without units ("Расход материала": "140"); units are attached only
    by the evidence-based rules of knowledge/dataset_units.yaml (adapters/units.py);
    the original text is always kept in `characteristics` under "<name> (исходно)".
"""
import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import ijson

from maxicalc.catalog.adapters.units import normalize_consumption
from maxicalc.catalog.normalize import normalize_text, parse_number
from maxicalc.catalog.schema import IngestReport, Product
from maxicalc.catalog.taxonomy_lift import lift

_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_MARKETING = "Маркетинговое описание товара"
_UNIT_FIX = {"кв.м": "м2", "кв.м.": "м2", "кв. м": "м2", "п.м.": "м.п.", "шт.": "шт",
             "уп.": "уп", "рул.": "рулон", "к-т": "компл", "н-р": "компл", "кг.": "кг",
             "кор.": "уп", "пар": "пар", "м.": "м"}


def looks_like_dump(path: Path) -> bool:
    """`{"products": [{... "cod_good" ...` in the first KBs of a .json file."""
    if path.suffix.lower() != ".json":
        return False
    head = path.open("rb").read(4096).decode("utf-8", "replace")
    return head.lstrip().startswith("{") and '"products"' in head[:200] and '"cod_good"' in head


def normalize_unit(u: str | None) -> str | None:
    if not u:
        return None
    k = normalize_text(u).lower()
    return _UNIT_FIX.get(k, k.rstrip("."))


def parse_description_pairs(desc: str | None) -> dict[str, str]:
    """"Объем: 9<br>Вес: <br>Тип основы: акриловая" -> {"Объем": "9", "Тип основы": "акриловая"}.
    Empty values are dropped; the first occurrence of a key wins."""
    out: dict[str, str] = {}
    for part in _BR.split(desc or ""):
        k, sep, v = part.partition(":")
        k, v = normalize_text(k), normalize_text(v)
        if sep and k and v and len(k) <= 60 and k not in out:
            out[k] = v
    return out


def _s(v: Any) -> str:
    return "" if v is None else normalize_text(str(v))


def merged_characteristics(item: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """(merged, from_description_only). Characteristics win; description fills the gaps."""
    chars: dict[str, str] = {}
    for c in item.get("characteristics") or []:
        if isinstance(c, dict) and _s(c.get("name")) and _s(c.get("value")):
            chars.setdefault(_s(c["name"]), _s(c["value"]))
    only_desc: dict[str, str] = {}
    for k, v in parse_description_pairs(item.get("description")).items():
        if k not in chars:
            chars[k] = v
            only_desc[k] = v
    chars.pop(_MARKETING, None)   # duplicated in marketing_description
    return chars, only_desc


def item_to_product(item: dict[str, Any], sku: str) -> Product | None:
    name = _s(item.get("name"))
    if not name:
        return None
    cats = item.get("categories") or {}
    cat_names = [_s(v) for v in cats.values() if _s(v)]
    chars, _ = merged_characteristics(item)
    country = item.get("country")
    if isinstance(country, dict) and _s(country.get("name")):
        chars.setdefault("Страна производства", _s(country["name"]))
    if _s(item.get("collection")):
        chars.setdefault("Коллекция", _s(item["collection"]))
    price = item.get("price")
    try:
        dec = Decimal(str(price)) if price not in (None, "") else None
    except ArithmeticError:
        dec = None
    brand = item.get("brand")
    p = Product(
        sku=sku, name=name,
        category_path=(lift(cat_names[0]) if cat_names else None) or cat_names,
        brand=(_s(brand.get("name")) if isinstance(brand, dict) else _s(brand)) or None,
        price=dec, description=_s(item.get("marketing_description")),
        characteristics=chars, url=_s(item.get("url_key")) or None,
        unit=normalize_unit(item.get("unit")), product_id=_s(item.get("id")) or None,
        cod_good=_s(item.get("cod_good")) or None, list_price=dec)
    normalize_consumption(p.characteristics, " ".join(cat_names), name)
    category_id = next(iter(cats), None)
    if category_id is not None:
        p.characteristics.setdefault("category_id", str(category_id))
    return p


def pack_fields(p: Product) -> None:
    """Typed pack fields from the card: area per pack and pieces per pack (bare numbers; the
    unit of these two fields is fixed by the card's own name: "Площадь покрытия упаковкой"
    is m2, "Количество в упаковке" is pieces)."""
    for key in ("Площадь покрытия упаковкой", "Площадь упаковки"):
        v = p.characteristics.get(key)
        if v and p.package_area_m2 is None:
            try:
                num = parse_number(re.split(r"[-–/]", v)[0])
            except ValueError:
                continue
            if 0 < num < 1000:
                p.package_area_m2 = num
    v = p.characteristics.get("Количество в упаковке")
    if v and p.quantity_in_package is None:
        try:
            num = parse_number(v)
        except ValueError:
            return
        if 0 < num < 100000:
            p.quantity_in_package = num


def dump_items(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("rb") as f:
        yield from ijson.items(f, "products.item", use_float=True)


def load_dump(path: Path, report: IngestReport | None = None) -> tuple[list[Product], IngestReport]:
    rep = report or IngestReport()
    out: dict[str, Product] = {}
    seen_cod: dict[str, int] = {}
    for n, item in enumerate(dump_items(path), start=1):
        rep.read += 1
        pid = _s(item.get("id"))
        cod = _s(item.get("cod_good"))
        if not pid and not cod:
            rep.skipped += 1
            rep.add_issue(f"позиция {n}: нет id и cod_good, пропущена")
            continue
        sku = cod or pid
        if sku in seen_cod:
            seen_cod[sku] += 1
            sku = f"{cod}#{pid}"
        else:
            seen_cod[sku] = 1
        p = item_to_product(item, sku)
        if p is None:
            rep.skipped += 1
            rep.add_issue(f"позиция {n} (id {pid}): нет наименования, пропущена")
            continue
        pack_fields(p)
        if pid in out:
            rep.add_issue(f"повтор id {pid} заменён")
        out[pid or sku] = p
        rep.loaded += 1
    dup = sum(1 for v in seen_cod.values() if v > 1)
    if dup:
        rep.add_issue(f"cod_good повторяется у {dup} кодов: sku = cod_good#id")
    return list(out.values()), rep
