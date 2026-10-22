"""Correction coefficients by work x material x condition (pure; the table is data).

    table.find("wall_painting", "water_dispersion_paint", surface="absorbent")
        -> Correction(effect="consumption_multiplier", value=1.43, reason=..., source=...)

A lookup that has no entry raises KeyError with the choices that exist, never a silent 1.0.
`explain()` is what the estimate shows: the coefficient, the reason and the source.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Source:
    kind: str          # manufacturer | third_party | derived
    name: str
    url: str
    quote: str
    note: str = ""


@dataclass(frozen=True)
class Correction:
    id: str
    work: str
    material: str
    condition: tuple[tuple[str, str], ...]
    effect: str                      # consumption_multiplier | thickness_mm
    value: Decimal
    reason: str
    source: Source

    def explain(self) -> str:
        unit = "мм" if self.effect == "thickness_mm" else "×"
        cond = ", ".join(f"{k}={v}" for k, v in self.condition)
        return (f"Поправка [{self.work}/{self.material}: {cond}] = {self.value} {unit}: "
                f"{self.reason} (источник: {self.source.name}, «{self.source.quote}», "
                f"{self.source.url})")


@dataclass(frozen=True)
class CorrectionTable:
    entries: tuple[Correction, ...]

    def find(self, work: str, material: str, **conditions: str) -> Correction:
        want = tuple(sorted(conditions.items()))
        for c in self.entries:
            if c.work == work and c.material == material and tuple(sorted(c.condition)) == want:
                return c
        have = sorted({f"{dict(c.condition)}" for c in self.entries
                       if c.work == work and c.material == material})
        raise KeyError(f"нет поправки для {work}/{material} при {dict(conditions)}; есть: {have}")
