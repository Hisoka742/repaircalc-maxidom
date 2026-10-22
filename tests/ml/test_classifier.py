from pathlib import Path

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.classify import MatchModel, weak_labels
from maxicalc.ml.match import Matcher
from maxicalc.ml.synth import SynthItem, generate, split_by_group

Split = tuple[list[SynthItem], list[SynthItem], list[SynthItem]]


@pytest.fixture(scope="module")
def data() -> Split:
    return split_by_group(generate(2400, seed=11), seed=11)


@pytest.fixture(scope="module")
def model(data: Split) -> MatchModel:
    train, dev, _ = data
    prods, labels = weak_labels([i.product for i in train])
    return MatchModel().fit(prods, labels, [i.product for i in dev], [i.gold for i in dev])


def strip_category(p: Product) -> Product:
    return p.model_copy(update={"category_path": []})


def test_weak_labels_skip_rule_silent_and_conflicting() -> None:
    ok = Product(sku="1", name="Обои флизелиновые 1,06х10,05 м", category_path=["Обои"])
    silent = Product(sku="2", name="Ceresit CM 11 PRO 25 кг")
    conflict = Product(sku="3", name="Клей для обоев Метилан", category_path=["Краски"])
    prods, labels = weak_labels([ok, silent, conflict])
    assert [p.sku for p in prods] == ["1"]
    assert labels[0].calc == "wallpaper"


def test_model_learns_calc_template_without_category(model: MatchModel, data: Split) -> None:
    _, _, test = data
    scores = model.score([strip_category(i.product) for i in test])
    hits = 0
    for it, sc in zip(test, scores, strict=True):
        top = max(sc.probs["calc_template"].items(), key=lambda kv: kv[1])[0]
        hits += top == it.gold.calc
    assert hits / len(test) > 0.6  # sanity floor on unseen models, name-only


def test_probabilities_are_valid(model: MatchModel, data: Split) -> None:
    _, _, test = data
    for sc in model.score([i.product for i in test[:50]]):
        for head in ("work_categories", "room_types", "properties", "calc_template"):
            assert all(0.0 <= p <= 1.0 for p in sc.probs[head].values())
        assert "any" not in sc.probs["room_types"]  # 'any' is a default, not predicted


def test_accepted_calc_is_precise_on_test(model: MatchModel, data: Split) -> None:
    _, _, test = data
    results = Matcher(model).match([strip_category(i.product) for i in test])
    accepted = [(r.calc_template.label, i.gold.calc)
                for r, i in zip(results, test, strict=True)
                if r.calc_template is not None and r.calc_template.accepted]
    assert accepted, "nothing was auto-accepted"
    precision = sum(a == g for a, g in accepted) / len(accepted)
    assert precision >= 0.9  # target is 0.95 on dev; allow slack on unseen test models


def test_miscategorised_items_are_not_silently_accepted(model: MatchModel, data: Split) -> None:
    _, _, test = data
    bad = [i for i in test if i.miscategorised and i.keyword_free]
    assert len(bad) >= 5
    results = Matcher(model).match([i.product for i in bad])
    wrong_auto = sum(
        r.status == "auto" and r.calc_template is not None and r.calc_template.label != i.gold.calc
        for r, i in zip(results, bad, strict=True))
    assert wrong_auto / len(bad) <= 0.25  # most wrong-category items must not pass as 'auto'


def test_save_load_roundtrip(tmp_path: Path, model: MatchModel, data: Split) -> None:
    _, _, test = data
    f = tmp_path / "m.joblib"
    model.save(f)
    again = MatchModel.load(f)
    prods = [i.product for i in test[:20]]
    assert [s.probs["calc_template"] for s in model.score(prods)] == [
        s.probs["calc_template"] for s in again.score(prods)]
