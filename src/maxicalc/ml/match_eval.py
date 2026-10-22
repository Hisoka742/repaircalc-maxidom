"""Matching evaluation on the SYNTHETIC catalog (machinery check, not a quality claim).

Protocol: split by product group -> weak labels from rules on train -> calibrate / pick
thresholds on dev (gold) -> report on test (gold), never tuning on test.
"""
from dataclasses import dataclass, field

from maxicalc.catalog.schema import Product
from maxicalc.ml.classify import MatchModel, weak_labels
from maxicalc.ml.match import Matcher, MatchResult
from maxicalc.ml.metrics import coverage_at_precision, multilabel_scores
from maxicalc.ml.synth import Labels, SynthItem, generate, split_by_group

HEADS = ("work_categories", "room_types", "properties")


@dataclass
class ScenarioReport:
    name: str
    macro_f1: dict[str, float] = field(default_factory=dict)
    micro_f1: dict[str, float] = field(default_factory=dict)
    calc_p_at_1: float = 0.0           # accepted-or-suggested calc label is right
    coverage: float = 0.0              # share of items fully auto-accepted
    auto_precision: float = 0.0        # precision of those (calc and work categories correct)
    review_share: float = 0.0


def _gold_set(g: Labels, head: str) -> set[str]:
    return {"work_categories": g.work, "room_types": g.rooms, "properties": g.props}[head]


def evaluate(results: list[MatchResult], gold: list[Labels], name: str) -> ScenarioReport:
    rep = ScenarioReport(name)
    for head in HEADS:
        s = multilabel_scores([_gold_set(g, head) for g in gold],
                              [r.accepted(head) for r in results])
        rep.macro_f1[head] = s.macro_f1
        rep.micro_f1[head] = s.micro_f1
    rep.calc_p_at_1 = sum(
        r.calc_template is not None and r.calc_template.label == g.calc
        for r, g in zip(results, gold, strict=True)) / len(gold)
    auto = [r.status == "auto" for r in results]
    correct = [r.accepted("calc_template") == {g.calc} and r.accepted("work_categories") == g.work
               for r, g in zip(results, gold, strict=True)]
    rep.coverage, rep.auto_precision = coverage_at_precision(auto, correct)
    rep.review_share = 1 - rep.coverage
    return rep


def _strip(items: list[SynthItem]) -> list[Product]:
    return [i.product.model_copy(update={"category_path": []}) for i in items]


@dataclass
class MatchingEval:
    n_items: int
    n_train: int
    n_dev: int
    n_test: int
    reports: list[ScenarioReport]


def run(n: int = 3000, seed: int = 0) -> MatchingEval:
    train, dev, test = split_by_group(generate(n, seed=seed), seed=seed)
    prods, labels = weak_labels([i.product for i in train])
    model = MatchModel().fit(prods, labels, [i.product for i in dev], [i.gold for i in dev])
    gold = [i.gold for i in test]
    full, rules_only = Matcher(model), Matcher()
    with_cat = [i.product for i in test]
    no_cat = _strip(test)
    reports = [
        evaluate(rules_only.match(with_cat), gold, "rules only, category present"),
        evaluate(full.match(with_cat), gold, "rules + model, category present"),
        evaluate(rules_only.match(no_cat), gold, "rules only, category missing"),
        evaluate(full.match(no_cat), gold, "rules + model, category missing"),
    ]
    return MatchingEval(n, len(train), len(dev), len(test), reports)


def to_markdown(ev: MatchingEval) -> list[str]:
    lines = [
        "", "## Catalog matching (SYNTHETIC catalog; machinery check, not a quality claim)", "",
        f"- Items: {ev.n_items} (train {ev.n_train} / dev {ev.n_dev} / test {ev.n_test}, "
        "split by product group, test models unseen)",
        "- Train labels: weak (rules). Calibration + thresholds (target precision 0.95): dev gold.",
        "", "| scenario | work F1 (macro/micro) | room F1 | prop F1 | calc P@1 | auto coverage |"
        " auto precision |", "|---|---|---|---|---|---|---|"]
    for r in ev.reports:
        def f(h: str, r: ScenarioReport = r) -> str:
            return f"{r.macro_f1[h]:.2f}/{r.micro_f1[h]:.2f}"

        lines.append(
            f"| {r.name} | {f('work_categories')} | {f('room_types')} | {f('properties')} | "
            f"{r.calc_p_at_1:.3f} | {r.coverage:.3f} | {r.auto_precision:.3f} |")
    return lines
