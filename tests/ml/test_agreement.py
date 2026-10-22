"""Agreement statistics against hand-computed values."""
import pytest

from maxicalc.ml.agreement import (
    cohen_kappa_binary,
    krippendorff_alpha,
    majority_vote,
    pairwise_kappa,
    per_class_kappa,
)


def test_cohen_kappa_textbook_example() -> None:
    # 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> po = .7, pe = .5, kappa = .4
    a = [True] * 25 + [False] * 25
    b = [True] * 20 + [False] * 5 + [True] * 10 + [False] * 15
    assert cohen_kappa_binary(a, b) == pytest.approx(0.4)


def test_perfect_and_chance_agreement() -> None:
    x = [True, False, True, False]
    assert cohen_kappa_binary(x, x) == 1.0
    assert cohen_kappa_binary(x, [not v for v in x]) == pytest.approx(-1.0)


def test_pairwise_and_per_class_on_label_sets() -> None:
    labels = {"a": [{"tile_laying"}, {"priming"}, set(), {"tile_laying", "grouting"}],
              "b": [{"tile_laying"}, {"priming"}, set(), {"tile_laying"}]}
    classes = ["tile_laying", "priming", "grouting"]
    k = pairwise_kappa(labels, classes)
    assert 0.7 < k[("a", "b")] < 1.0
    pc = per_class_kappa(labels, classes)
    assert pc["tile_laying"] == 1.0 and pc["priming"] == 1.0 and pc["grouting"] < 1.0


def test_krippendorff_alpha_known_values() -> None:
    same = {"a": [{"w"}, set(), {"w"}], "b": [{"w"}, set(), {"w"}], "c": [{"w"}, set(), {"w"}]}
    assert krippendorff_alpha(same, ["w"]) == pytest.approx(1.0)
    # two annotators, 4 units, one disagreement
    two = {"a": [{"w"}, {"w"}, set(), set()], "b": [{"w"}, set(), set(), set()]}
    # coincidences: units agree twice-(T,T) once, (F,F) twice; one (T,F) pair. n=8
    # d_obs = 2/8 = .25; n_t = 3, n_f = 5; d_exp = 2*3*5/(8*7) = .5357; alpha = .5333
    assert krippendorff_alpha(two, ["w"]) == pytest.approx(1 - 0.25 / (30 / 56), abs=1e-6)


def test_majority_vote_and_ties() -> None:
    votes = [{"a", "b"}, {"a"}, {"a", "c"}, {"b", "c"}]
    chosen, ties = majority_vote(votes, ["a", "b", "c", "d"])
    assert chosen == {"a"} and ties == {"b", "c"}
