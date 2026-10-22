import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import openpyxl


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def csv_rows(path: Path) -> Iterator[dict[str, Any]]:
    text = _decode(path.read_bytes())
    header = text.split("\n", 1)[0]
    delim = max(";,\t|", key=header.count)
    yield from csv.DictReader(io.StringIO(text), delimiter=delim)


def xlsx_rows(path: Path) -> Iterator[dict[str, Any]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return
    it = ws.iter_rows(values_only=True)
    headers = next(it, None)
    if headers is None:
        return
    for row in it:
        if any(c is not None for c in row):
            yield {str(h): v for h, v in zip(headers, row, strict=False) if h is not None}


def json_rows(path: Path) -> Iterator[dict[str, Any]]:
    data = json.loads(_decode(path.read_bytes()))
    if isinstance(data, dict):
        for key in ("products", "items", "offers", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("JSON: ожидается список товаров или объект с ключом products/items")
    for r in data:
        if isinstance(r, dict):
            yield r
