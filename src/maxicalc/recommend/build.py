"""Build CatalogEntry rows (accepted labels + extracted attributes) from matching results.

Facts (card characteristics, regex over name/description) go to `attrs`. If an LLM client is
given, attributes the calculator still lacks are asked of it and stored SEPARATELY in `inferred`
(source=llm, confidence, quote); the engine merges them only above a confidence threshold
(`recommend/inferred.py`).
"""
from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import ExtractionResult, extract, extract_with_llm
from maxicalc.ml.llm_client import LLMClient
from maxicalc.ml.match import MatchResult
from maxicalc.ml.roles import product_role
from maxicalc.recommend.select import CatalogEntry, Inferred
from maxicalc.service.requirements import REQUIREMENTS


def _needed(calc: str) -> list[str]:
    required, any_of = REQUIREMENTS.get(calc, ((), ()))
    return [*required, *any_of]


def _split(res: ExtractionResult) -> tuple[dict, dict[str, Inferred]]:  # type: ignore[type-arg]
    facts = {k: a.value for k, a in res.attrs.items() if a.source != "llm"}
    inferred = {k: Inferred(a.value, a.confidence, a.evidence, a.source)
                for k, a in res.attrs.items() if a.source == "llm"}
    return facts, inferred


def to_entries(
    products: list[Product], results: list[MatchResult], llm: LLMClient | None = None
) -> list[CatalogEntry]:
    out: list[CatalogEntry] = []
    for p, r in zip(products, results, strict=True):
        calc = r.calc_template
        label = calc.label if calc and calc.accepted else "none"
        res = extract(p)
        if llm is not None and label in REQUIREMENTS:
            res = extract_with_llm(p, llm, _needed(label), base=res)
        facts, inferred = _split(res)
        out.append(CatalogEntry(
            product=p,
            work=r.accepted("work_categories"),
            rooms=r.accepted("room_types") or {"any"},
            props=r.accepted("properties"),
            calc=label,
            status=r.status,
            attrs=facts,
            inferred=inferred,
            role=product_role(p).role,
        ))
    return out
