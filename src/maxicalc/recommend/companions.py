from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from maxicalc.recommend.select import Candidate, CatalogEntry

FILE = Path(__file__).resolve().parents[1] / "knowledge" / "companions.yaml"


@cache
def _load() -> dict[str, list[str]]:
    return {k: list(v) for k, v in yaml.safe_load(FILE.read_text(encoding="utf-8")).items()}


def companions_for(calc: str) -> list[str]:
    """Calc templates that should be offered together with `calc` (cross-sell)."""
    return list(_load().get(calc, []))


def pick_companions(
    accessories: list["CatalogEntry"], ppe: list["CatalogEntry"],
    n_accessories: int = 5, n_ppe: int = 3,
) -> list["Candidate"]:
    """Accessories of the asked calculator (profiles, corners, fasteners...) and protective gear,
    best-described and in-stock first. Quantities are not computed here (engine's job)."""
    from maxicalc.recommend.select import Candidate, completeness

    def usable(e: "CatalogEntry") -> bool:
        p = e.product
        return p.price is not None and p.in_stock is not False and p.active is not False

    def top(es: list["CatalogEntry"], n: int, why: str) -> list[Candidate]:
        ranked = sorted((e for e in es if usable(e)),
                        key=lambda e: (-completeness(e), e.product.sku))[:n]
        return [Candidate(e, round(completeness(e), 4), [why]) for e in ranked]

    return top(accessories, n_accessories, "сопутствующий товар (аксессуар)") + top(
        ppe, n_ppe, "средства защиты при работах")
