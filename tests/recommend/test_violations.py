"""Automated hard-rule violation checker: no recommendation may break a room rule.

Truth = GOLD labels. A catalog built from gold labels must give zero violations (the
selector logic is sound); the pipeline-predicted catalog is measured in eval/REPORT.md.
"""
import pytest

from maxicalc.ml.synth import SynthItem, generate
from maxicalc.recommend.recommend_eval import (
    count_violations,
    entries_from_gold,
    rubric_relevance,
)
from maxicalc.recommend.rules_kb import load_room_rules
from maxicalc.recommend.select import recommend

ROOMS = ["bathroom", "kitchen", "kids", "balcony", "hallway", "living", "bedroom"]


@pytest.fixture(scope="module")
def items() -> list[SynthItem]:
    return generate(2500, seed=21)


def test_gold_catalog_has_zero_hard_rule_violations(items: list[SynthItem]) -> None:
    entries = entries_from_gold(items)
    gold = {i.product.sku: i.gold for i in items}
    calcs = sorted({e.calc for e in entries})
    returned = violations = 0
    for room in ROOMS:
        for calc in calcs:
            r = recommend(entries, room, calc=calc, top_k=50)
            n, bad = count_violations(room, r.items, gold)
            returned += n
            violations += len(bad)
            assert not bad, (room, calc, bad[:3])
    assert returned > 200, "test is vacuous: too few recommendations were produced"
    assert violations == 0


def test_every_hard_rule_actually_excludes_something(items: list[SynthItem]) -> None:
    """Guards against rules that never fire (e.g. a label typo making them vacuous)."""
    entries = entries_from_gold(items)
    kb = load_room_rules()
    for room, rr in kb.rooms.items():
        for rule in rr.hard:
            fired = False
            for calc in rule.calc:
                r = recommend(entries, room, calc=calc, top_k=1)
                fired |= any(why == rule.reason for _, why in r.excluded)
            # a rule may legitimately be idle only if the catalog has no such product
            has_product = any(e.calc in rule.calc for e in entries)
            assert fired or not has_product, (room, rule.reason)


def test_rubric_relevance_basics(items: list[SynthItem]) -> None:
    it = next(i for i in items if i.gold.calc == "paint" and "washable" in i.gold.props)
    assert rubric_relevance("kitchen", "paint", it.gold) >= 1
    assert rubric_relevance("kitchen", "grout", it.gold) == 0  # wrong product type
    plain = next(i for i in items if i.gold.calc == "paint" and not i.gold.props)
    assert rubric_relevance("kitchen", "paint", plain.gold) == 0  # violates 'washable'
