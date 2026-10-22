"""LLM-inferred attributes are kept apart from facts and used only above a confidence threshold.

A catalog entry has `attrs` (facts: the card's characteristics, regex over name/description) and
`inferred` (what the LLM read out of the text, each with source="llm", a confidence and the
quote it came from). The calculators see facts plus those inferred values whose confidence reaches
`min_confidence`; every such use is stated in the line's explain. A fact is never overwritten.
"""
import os
from dataclasses import replace

from maxicalc.recommend.defaults import default_for
from maxicalc.recommend.select import CatalogEntry

CONF_RANK = {"low": 0, "medium": 1, "high": 2}
DEFAULT_MIN_CONFIDENCE = "medium"   # LLM values are born "low": not used until calibrated


def min_confidence() -> str:
    v = os.environ.get("INFERRED_MIN_CONFIDENCE", DEFAULT_MIN_CONFIDENCE)
    return v if v in CONF_RANK else DEFAULT_MIN_CONFIDENCE


def effective_entry(
    entry: CatalogEntry, threshold: str | None = None
) -> tuple[CatalogEntry, list[str], list[str]]:
    """(entry with usable inferred values merged into attrs, explain notes, names held back)."""
    thr = threshold or min_confidence()
    merged = dict(entry.attrs)
    notes: list[str] = []
    held: list[str] = []
    for name, inf in sorted(entry.inferred.items()):
        if name in entry.attrs:
            continue                      # a fact wins
        if CONF_RANK.get(inf.confidence, 0) >= CONF_RANK[thr]:
            merged[name] = inf.value
            notes.append(f"Значение «{name}» = {inf.value} получено моделью из текста карточки "
                         f"(цитата: «{inf.evidence}», уверенность {inf.confidence}, порог {thr}); "
                         "в карточке такого поля нет")
        else:
            held.append(name)
    # last resort: a sourced manufacturer default for this product type (brand+type, then type)
    hit = default_for(entry.product, entry.calc)
    if hit and hit.attr not in merged:
        merged[hit.attr] = hit.value
        notes.append(hit.explain())
    if merged == entry.attrs:
        return entry, notes, held
    return replace(entry, attrs=merged), notes, held
