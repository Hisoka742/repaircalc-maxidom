"""Consumption defaults by product type (knowledge/consumption_defaults.yaml).

Used last in the resolution order card fact -> LLM-inferred >= threshold -> brand+type default ->
type default. A default is a manufacturer figure with a URL and a quote; the explain line states
that it was used, which level, and the source. A product that matches no type gets no default
(the calculator then says what is missing, it never guesses).
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from maxicalc.catalog.schema import Product

FILE = Path(__file__).resolve().parents[1] / "knowledge" / "consumption_defaults.yaml"


@dataclass(frozen=True)
class DefaultHit:
    attr: str
    value: Decimal
    level: str        # "brand+type" | "type"
    type_id: str
    source: str
    url: str
    quote: str
    note: str = ""

    def explain(self) -> str:
        return (f"Расход «{self.attr}» = {self.value} принят по умолчанию "
                f"({'бренд+тип' if self.level == 'brand+type' else 'тип'}: {self.type_id}; "
                f"{self.source}: «{self.quote}», {self.url}"
                f"{'; ' + self.note if self.note else ''}); в карточке товара расхода нет")


@dataclass(frozen=True)
class _Type:
    id: str
    calc: str
    any: re.Pattern[str]
    exclude: re.Pattern[str] | None
    attr: str
    value: Decimal
    raw: dict[str, Any]


@cache
def _types() -> tuple[_Type, ...]:
    raw = yaml.safe_load(FILE.read_text(encoding="utf-8"))["types"]
    out = []
    for tid, t in raw.items():
        out.append(_Type(
            tid, t["calc"], re.compile(t["any"]),
            re.compile(t["not"]) if t.get("not") else None,
            t["attr"], Decimal(str(t["value"])), t))
    return tuple(out)


def _text(p: Product) -> str:
    return " ".join([p.name, *p.category_path]).lower().replace("ё", "е")


def default_for(p: Product, calc: str) -> DefaultHit | None:
    text = _text(p)
    brand = (p.brand or "").upper()
    for t in _types():
        if t.calc != calc or not t.any.search(text):
            continue
        if t.exclude and t.exclude.search(text):
            continue
        raw = t.raw
        brands = {str(k).upper(): Decimal(str(v)) for k, v in (raw.get("brands") or {}).items()}
        if brand in brands:
            src = (raw.get("brand_sources") or {}).get(brand, raw)
            return DefaultHit(t.attr, brands[brand], "brand+type", t.id, src["source"],
                              src["url"], src["quote"], raw.get("note", ""))
        return DefaultHit(t.attr, t.value, "type", t.id, raw["source"], raw["url"], raw["quote"],
                          raw.get("note", ""))
    return None
