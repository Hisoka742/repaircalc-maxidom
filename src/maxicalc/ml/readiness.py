"""Calculator readiness: how much of a catalog the quantity calculators can serve.

A product is "ready" when its card has every attribute its calculator needs. Only products
whose labels are trusted (status auto / verified) are counted, because those are the ones
the recommender would actually offer.
"""
from collections import Counter
from dataclasses import dataclass, field

from maxicalc.ml.roles import main_calcs
from maxicalc.recommend.inferred import effective_entry
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.requirements import REQUIREMENTS, missing_attrs

BLOCKING_SHARE = 0.5   # below this, baskets for the type will mostly be warnings


@dataclass
class Readiness:
    calc: str
    total: int = 0
    ready: int = 0
    top_missing: list[tuple[str, int]] = field(default_factory=list)

    @property
    def share(self) -> float:
        return self.ready / self.total if self.total else 1.0

    @property
    def blocking(self) -> bool:
        return self.total > 0 and self.share < BLOCKING_SHARE


def readiness_report(entries: list[CatalogEntry]) -> dict[str, Readiness]:
    rep: dict[str, Readiness] = {}
    missing: dict[str, Counter[str]] = {}
    for e in entries:
        if e.status == "review" or e.calc not in REQUIREMENTS:
            continue
        if e.role != "main" and e.calc in main_calcs():
            continue   # accessories / tools / consumables are not the main product of a calculator
        r = rep.setdefault(e.calc, Readiness(e.calc))
        r.total += 1
        miss = missing_attrs(e.calc, effective_entry(e)[0].attrs)
        if miss:
            missing.setdefault(e.calc, Counter()).update(miss)
        else:
            r.ready += 1
    for calc, r in rep.items():
        r.top_missing = missing.get(calc, Counter()).most_common(5)
    return rep
