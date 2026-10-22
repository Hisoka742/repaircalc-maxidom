"""Evaluate attribute extraction against a gold file (per-field precision / recall)."""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract

GOLD = Path(__file__).resolve().parents[3] / "eval" / "gold" / "extraction_cases.yaml"


@dataclass
class FieldStats:
    tp: int = 0       # extracted and equal to gold
    wrong: int = 0    # extracted, gold has the field, different value
    fp: int = 0       # extracted, gold has no such field
    fn: int = 0       # gold has the field, nothing extracted

    @property
    def precision(self) -> float:
        n = self.tp + self.wrong + self.fp
        return self.tp / n if n else 1.0

    @property
    def recall(self) -> float:
        n = self.tp + self.wrong + self.fn
        return self.tp / n if n else 1.0


@dataclass
class ExtractionEval:
    cases: int = 0
    fields: dict[str, FieldStats] = field(default_factory=lambda: defaultdict(FieldStats))
    errors: list[str] = field(default_factory=list)

    def micro(self) -> tuple[float, float]:
        tp = sum(s.tp for s in self.fields.values())
        n_ext = sum(s.tp + s.wrong + s.fp for s in self.fields.values())
        n_gold = sum(s.tp + s.wrong + s.fn for s in self.fields.values())
        return (tp / n_ext if n_ext else 1.0), (tp / n_gold if n_gold else 1.0)


def _equal(a: object, b: object) -> bool:
    if isinstance(a, (Decimal, int, float)) and isinstance(b, (Decimal, int, float)):
        return Decimal(str(a)) == Decimal(str(b))
    return a == b


def to_product(c: dict[str, Any]) -> Product:
    cat = c.get("category", "")
    return Product(
        sku=str(c["id"]), name=c["name"], description=c.get("description", ""),
        category_path=[x.strip() for x in cat.split(">") if x.strip()],
        characteristics={k: str(v) for k, v in (c.get("characteristics") or {}).items()},
    )


def run(path: Path = GOLD) -> ExtractionEval:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = ExtractionEval()
    for c in data["cases"]:
        out.cases += 1
        got = {k: a.value for k, a in extract(to_product(c)).attrs.items()}
        exp = c.get("expected") or {}
        for k in exp.keys() | got.keys():
            st = out.fields[k]
            if k in exp and k in got:
                if _equal(got[k], exp[k]):
                    st.tp += 1
                else:
                    st.wrong += 1
                    out.errors.append(f"{c['id']}: {k} = {got[k]}, ожидалось {exp[k]}")
            elif k in got:
                st.fp += 1
                out.errors.append(f"{c['id']}: лишнее {k} = {got[k]}")
            else:
                st.fn += 1
                out.errors.append(f"{c['id']}: не найдено {k} (ожидалось {exp[k]})")
    return out
