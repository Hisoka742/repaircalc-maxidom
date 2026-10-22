from pathlib import Path

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.match import Matcher, ModelScores
from maxicalc.ml.review import ReviewQueue
from maxicalc.ml.synth import Labels, generate, split_by_group
from maxicalc.ml.taxonomy import load_taxonomy


def prod(name: str, cat: str = "", sku: str = "1") -> Product:
    return Product(sku=sku, name=name, category_path=[x.strip() for x in cat.split(">") if x])


class StubScorer:
    """Returns fixed calibrated probabilities for every product."""

    def __init__(self, calc: dict[str, float], tau: float = 0.8) -> None:
        self.calc, self.tau = calc, tau

    def score(self, products: list[Product]) -> list[ModelScores]:
        thr = {"calc_template": {k: self.tau for k in self.calc}}
        return [ModelScores({"calc_template": dict(self.calc)}, thr) for _ in products]


# ---------- synthetic data ----------
def test_synth_is_deterministic_and_labels_are_valid() -> None:
    a = generate(200, seed=1)
    b = generate(200, seed=1)
    assert [x.product.name for x in a] == [x.product.name for x in b]
    t = load_taxonomy()
    for item in a:
        g: Labels = item.gold
        assert g.work <= set(t.work_categories) and g.rooms <= set(t.room_types)
        assert g.props <= set(t.properties) and g.calc in t.calc_templates


def test_synth_includes_miscategorised_and_keyword_free_items() -> None:
    items = generate(1500, seed=2)
    assert any(i.miscategorised for i in items)
    assert any(i.keyword_free for i in items)


def test_split_is_by_group_not_by_item() -> None:
    items = generate(900, seed=3)
    train, dev, test = split_by_group(items, seed=3)
    groups = [{i.group for i in part} for part in (train, dev, test)]
    assert not (groups[0] & groups[1]) and not (groups[0] & groups[2])
    assert not (groups[1] & groups[2])
    assert len(train) > len(dev) > 0 and len(test) > 0


# ---------- decision logic (no trained model) ----------
def test_clean_rule_hit_is_auto_accepted() -> None:
    r = Matcher().match([prod("Обои флизелиновые 1,06х10,05 м", "Обои > Флизелиновые")])[0]
    assert r.status == "auto"
    assert r.calc_template is not None and r.calc_template.label == "wallpaper"
    assert r.calc_template.source == "rule" and r.calc_template.accepted
    assert [d.label for d in r.room_types if d.accepted] == ["any"]


def test_conflicting_category_goes_to_review() -> None:
    r = Matcher().match([prod("Клей для обоев Метилан", "Краски")])[0]
    assert r.status == "review"
    assert any("конфликт" in x for x in r.reasons)


def test_nothing_known_goes_to_review() -> None:
    r = Matcher().match([prod("Ceresit CM 11 PRO 25 кг")])[0]
    assert r.status == "review"
    assert r.calc_template is None or not r.calc_template.accepted


def test_model_fills_in_when_rules_are_silent() -> None:
    m = Matcher(StubScorer({"tile_adhesive": 0.97, "grout": 0.02}))
    r = m.match([prod("Ceresit CM 11 PRO 25 кг")])[0]
    assert r.calc_template is not None
    assert (r.calc_template.label, r.calc_template.source) == ("tile_adhesive", "model")
    assert r.calc_template.accepted


def test_low_confidence_model_is_only_a_suggestion() -> None:
    m = Matcher(StubScorer({"tile_adhesive": 0.6, "grout": 0.3}, tau=0.8))
    r = m.match([prod("Ceresit CM 11 PRO 25 кг")])[0]
    assert r.status == "review"
    assert r.calc_template is not None and not r.calc_template.accepted
    assert r.calc_template.label == "tile_adhesive"  # shown as the suggested label


def test_model_contradicting_rule_goes_to_review() -> None:
    m = Matcher(StubScorer({"paint": 0.99}))
    r = m.match([prod("Обои флизелиновые 1,06х10,05 м", "Обои")])[0]
    assert r.status == "review"
    assert any("противореч" in x for x in r.reasons)


# ---------- review queue ----------
def test_review_queue_roundtrip(tmp_path: Path) -> None:
    f = tmp_path / "feedback.jsonl"
    q = ReviewQueue(f)
    results = Matcher().match([prod("Ceresit CM 11 PRO", sku="a"), prod("Обои", "Обои", sku="b")])
    q.add(results)
    assert [x.sku for x in q.pending()] == ["a"]  # only the review item
    q.resolve("a", Labels(work={"wall_tile"}, rooms={"any"}, props=set(), calc="tile_adhesive"),
              reviewer="ivan")
    assert q.pending() == []
    # persisted: a fresh queue sees the feedback
    q2 = ReviewQueue(f)
    fb = q2.feedback()
    assert fb["a"].calc == "tile_adhesive" and fb["a"].work == {"wall_tile"}


def test_review_queue_orders_least_confident_first() -> None:
    q = ReviewQueue()
    low = Matcher(StubScorer({"grout": 0.3}, tau=0.8)).match([prod("X", sku="low")])
    mid = Matcher(StubScorer({"grout": 0.7}, tau=0.8)).match([prod("Y", sku="mid")])
    q.add(mid + low)
    assert [x.sku for x in q.pending()] == ["low", "mid"]


def test_resolve_unknown_sku() -> None:
    with pytest.raises(KeyError):
        ReviewQueue().resolve("nope", Labels(set(), {"any"}, set(), "none"), reviewer="x")
