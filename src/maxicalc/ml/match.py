"""Matching decision: rules + (optional) calibrated model -> labels, confidence, auto/review.

A model is any object with `score(products) -> list[ModelScores]` returning *calibrated*
per-label probabilities and per-label acceptance thresholds (None = never auto-accept).
Rules are high-precision; a model label that contradicts a rule, or a conflict between the
store category and the product name, always goes to review.
"""
from dataclasses import dataclass, field
from typing import Literal, Protocol

from maxicalc.catalog.schema import Product
from maxicalc.ml.rules import LabelHit, RuleResult, apply_rules

Head = Literal["work_categories", "room_types", "properties", "calc_template"]
MULTI_HEADS: tuple[str, ...] = ("work_categories", "room_types", "properties")
SUGGESTION_FLOOR = 0.3


@dataclass(frozen=True)
class ModelScores:
    probs: dict[str, dict[str, float]]                 # head -> label -> calibrated prob
    thresholds: dict[str, dict[str, float | None]]     # head -> label -> acceptance threshold


class Scorer(Protocol):
    def score(self, products: list[Product]) -> list[ModelScores]: ...


@dataclass(frozen=True)
class LabelDecision:
    label: str
    confidence: float
    source: Literal["rule", "model"]
    accepted: bool
    reason: str = ""


@dataclass
class MatchResult:
    sku: str
    work_categories: list[LabelDecision] = field(default_factory=list)
    room_types: list[LabelDecision] = field(default_factory=list)
    properties: list[LabelDecision] = field(default_factory=list)
    calc_template: LabelDecision | None = None
    status: Literal["auto", "review"] = "review"
    reasons: list[str] = field(default_factory=list)

    def accepted(self, head: str) -> set[str]:
        if head == "calc_template":
            c = self.calc_template
            return {c.label} if c and c.accepted else set()
        return {d.label for d in getattr(self, head) if d.accepted}

    @property
    def review_confidence(self) -> float:
        """Lower = more in need of a human (used to order the review queue)."""
        return self.calc_template.confidence if self.calc_template else 0.0


class Matcher:
    def __init__(self, scorer: Scorer | None = None) -> None:
        self.scorer = scorer

    def match(self, products: list[Product]) -> list[MatchResult]:
        scores = self.scorer.score(products) if self.scorer else [None] * len(products)
        return [self._one(p, apply_rules(p), s) for p, s in zip(products, scores, strict=True)]

    def _one(self, p: Product, rules: RuleResult, ms: ModelScores | None) -> MatchResult:
        res = MatchResult(sku=p.sku)
        trusted = not rules.conflict
        hits: dict[str, dict[str, LabelHit]] = {
            "work_categories": rules.work_categories, "room_types": rules.room_types,
            "properties": rules.properties}
        for head in MULTI_HEADS:
            decisions: dict[str, LabelDecision] = {}
            for lab, hit in hits[head].items():
                decisions[lab] = LabelDecision(lab, hit.confidence, "rule", trusted, hit.reason)
            if ms:
                for lab, prob in ms.probs.get(head, {}).items():
                    if lab in decisions or prob < SUGGESTION_FLOOR:
                        continue
                    tau = ms.thresholds.get(head, {}).get(lab)
                    decisions[lab] = LabelDecision(
                        lab, prob, "model", tau is not None and prob >= tau, "модель")
            setattr(res, head, sorted(decisions.values(), key=lambda d: -d.confidence))

        if not any(d.accepted for d in res.room_types):
            res.room_types.append(LabelDecision("any", 1.0, "rule", True, "по умолчанию"))

        res.calc_template = self._calc(rules, ms, res)
        if rules.conflict:
            res.reasons.append(f"конфликт категории и названия: {rules.calc_template.reason}"
                               if rules.calc_template else "конфликт категории и названия")
        if not res.accepted("work_categories") and not (
                res.calc_template and res.calc_template.accepted):
            res.reasons.append("нет принятых меток")
        ok = (res.calc_template is not None and res.calc_template.accepted
              and bool(res.accepted("work_categories")) and not rules.conflict
              and not any("противореч" in r for r in res.reasons))
        res.status = "auto" if ok else "review"
        if not ok and not res.reasons:
            res.reasons.append("низкая уверенность")
        return res

    def _calc(
        self, rules: RuleResult, ms: ModelScores | None, res: MatchResult
    ) -> LabelDecision | None:
        rule = rules.calc_template
        top: tuple[str, float] | None = None
        tau: float | None = None
        if ms and ms.probs.get("calc_template"):
            top = max(ms.probs["calc_template"].items(), key=lambda kv: kv[1])
            tau = ms.thresholds.get("calc_template", {}).get(top[0])
        model_ok = top is not None and tau is not None and top[1] >= tau
        if rule:
            if model_ok and top and top[0] != rule.label:
                res.reasons.append(
                    f"модель противоречит правилу: {top[0]} ({top[1]:.2f}) vs {rule.label}")
                return LabelDecision(rule.label, rule.confidence, "rule", False, rule.reason)
            return LabelDecision(rule.label, rule.confidence, "rule", not rules.conflict,
                                 rule.reason)
        if top:
            return LabelDecision(top[0], top[1], "model", bool(model_ok), "модель")
        return None
