"""Yandex Market YML feed (<yml_catalog><shop><categories>/<offers>): the organisers' data source.

Streamed with lxml.iterparse (constant memory; the full Maxidom SPb feed is ~95 MB, ~40 000 offers),
elements are cleared as they are read. Categories come before offers in the feed, so the category
tree is complete when the first offer arrives. A truncated file is read up to the last complete
offer (recover=True), the report is the caller's job. `.xml.gz` is read transparently.

Mapping: offer id -> sku, name, vendor -> brand, price, url, picture, categoryId -> category path,
description (`<br>` -> " | "), `available` -> in_stock, every <param name unit> -> a characteristic
(key "name, unit" when the unit is given; repeated names are joined with "; "), plus weight and
country_of_origin as characteristics. Raw params are kept, nothing is dropped.
"""
import gzip
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

from lxml import etree

from maxicalc.catalog.normalize import normalize_text

_BR = ("<br>", "<br/>", "<br />", "<BR>")


def _open(path: Path) -> IO[bytes]:
    return gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb")  # type: ignore[return-value]


def _txt(el: Any, tag: str) -> str:
    e = el.find(tag)
    return normalize_text(e.text) if e is not None and e.text else ""


def _description(el: Any) -> str:
    e = el.find("description")
    if e is None or not e.text:
        return ""
    raw = e.text
    for b in _BR:
        raw = raw.replace(b, " | ")
    return normalize_text(raw).strip(" |")


def feed_date(path: Path) -> str | None:
    """The `date` attribute of <yml_catalog> (when the feed was generated)."""
    with _open(path) as f:
        head = f.read(400).decode("utf-8", "replace")
    i = head.find('date="')
    return head[i + 6:i + 16] if i >= 0 else None


def yml_rows(path: Path) -> Iterator[dict[str, Any]]:
    cats: dict[str, tuple[str, str | None]] = {}
    memo: dict[str, str] = {}

    def cat_path(cid: str) -> str:
        if cid in memo:
            return memo[cid]
        names: list[str] = []
        seen: set[str] = set()
        cur = cid
        while cur in cats and cur not in seen:
            seen.add(cur)
            name, parent = cats[cur]
            names.append(name)
            cur = parent or ""
        memo[cid] = " > ".join(reversed(names))
        return memo[cid]

    with _open(path) as f:
        for _event, el in etree.iterparse(f, events=("end",), tag=("category", "offer"),
                                          recover=True, huge_tree=True):
            if el.tag == "category":
                cats[el.get("id", "")] = (normalize_text(el.text or ""), el.get("parentId"))
                el.clear()
                continue
            chars: dict[str, str] = {}
            for p in el.findall("param"):
                name = normalize_text(p.get("name", ""))
                val = normalize_text(p.text or "")
                if not name or not val:
                    continue
                unit = p.get("unit")
                key = f"{name}, {unit}" if unit else name
                if key not in chars:
                    chars[key] = val
                elif val not in chars[key].split("; "):
                    chars[key] += f"; {val}"
            for tag, label in (("weight", "Вес, кг"), ("country_of_origin", "Страна производства")):
                v = _txt(el, tag)
                if v and label not in chars:
                    chars[label] = v
            row: dict[str, Any] = {
                "sku": el.get("id", ""), "name": _txt(el, "name"),
                "category": cat_path(_txt(el, "categoryId")), "brand": _txt(el, "vendor"),
                "price": _txt(el, "price"), "url": _txt(el, "url"),
                "image_url": _txt(el, "picture"), "description": _description(el),
                "in_stock": el.get("available", ""), "characteristics": chars,
            }
            el.clear()
            while el.getprevious() is not None:
                del el.getparent()[0]
            yield row
