"""Catalog adapters: any supported file -> normalized Products + validation report."""
import json
from pathlib import Path

from maxicalc.catalog.adapters.base import rows_to_products
from maxicalc.catalog.adapters.maxidom_api import api_items, items_to_products, looks_like_api
from maxicalc.catalog.adapters.products_dump import load_dump, looks_like_dump
from maxicalc.catalog.adapters.tabular import _decode, csv_rows, json_rows, xlsx_rows
from maxicalc.catalog.adapters.yml_feed import yml_rows
from maxicalc.catalog.schema import IngestReport, Product


def load_catalog(path: str | Path) -> tuple[list[Product], IngestReport]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".gz" and p.name.lower().endswith((".xml.gz", ".yml.gz")):
        ext = ".xml"
    if looks_like_dump(p):   # official 274 MB dump: streamed, never read whole
        report = IngestReport()
        return load_dump(p, report)[0], report
    if ext in (".json", ".jsonl"):
        # the organisers' stand API (Bagisto) is recognised by its field names
        try:
            items = list(api_items(p, _decode(p.read_bytes())))
        except json.JSONDecodeError:
            items = []
        if items and looks_like_api(items):
            report = IngestReport()
            return items_to_products(items, report), report
    if ext in (".csv", ".tsv", ".txt"):
        rows = csv_rows(p)
    elif ext in (".xlsx", ".xlsm"):
        rows = xlsx_rows(p)
    elif ext in (".json", ".jsonl"):
        rows = json_rows(p)
    elif ext in (".xml", ".yml"):
        rows = yml_rows(p)
    else:
        raise ValueError(f"Неподдерживаемый формат каталога: {ext or p.name}")
    report = IngestReport()
    return rows_to_products(rows, report), report


def peek_headers(path: str | Path) -> list[str]:
    """Column names of a tabular catalog (CSV / XLSX / JSON). YML feeds have a fixed schema."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".csv", ".tsv", ".txt"):
        from maxicalc.catalog.adapters.tabular import _decode

        lines = _decode(p.read_bytes()).splitlines()
        head = lines[0] if lines else ""
        delim = max(";,\t|", key=head.count)
        return [h.strip() for h in head.split(delim)]
    if ext in (".xlsx", ".xlsm"):
        first = next(iter(xlsx_rows(p)), None)
        return list(first) if first else []
    if ext == ".json":
        first = next(iter(json_rows(p)), None)
        return list(first) if first else []
    return []


__all__ = ["load_catalog", "peek_headers"]
