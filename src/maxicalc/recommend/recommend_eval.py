"""Recommendation evaluation on the SYNTHETIC catalog: hard-rule violations and nDCG@5.

Truth for both metrics is the GOLD label set. nDCG relevance uses an independent rubric
(not the selector's scoring), but it reads the same room-rule knowledge base, so it checks
how label errors propagate into rankings, not whether the rules themselves are right.
"""
from dataclasses import dataclass

from maxicalc.ml.classify import MatchModel, weak_labels
from maxicalc.ml.embed import HashingEmbedder
from maxicalc.ml.match import Matcher, MatchResult
from maxicalc.ml.metrics import ndcg_at_k
from maxicalc.ml.synth import Labels, SynthItem, generate, split_by_group
from maxicalc.recommend.relevance import RelevanceScorer
from maxicalc.recommend.rules_kb import load_room_rules
from maxicalc.recommend.select import Candidate, CatalogEntry, recommend

ROOMS = ("bathroom", "kitchen", "kids", "balcony", "hallway", "living", "bedroom")
QUERY_CALCS = ("paint", "wallpaper", "tile", "laminate", "drywall", "electrical",
               "tile_adhesive", "grout", "primer", "putty")


def entries_from_gold(items: list[SynthItem]) -> list[CatalogEntry]:
    return [CatalogEntry(i.product, set(i.gold.work), set(i.gold.rooms), set(i.gold.props),
                         i.gold.calc, "verified") for i in items]


def entries_from_predictions(
    items: list[SynthItem], results: list[MatchResult]
) -> list[CatalogEntry]:
    out: list[CatalogEntry] = []
    for it, r in zip(items, results, strict=True):
        calc = r.calc_template
        out.append(CatalogEntry(
            it.product, r.accepted("work_categories"), r.accepted("room_types") or {"any"},
            r.accepted("properties"), calc.label if calc and calc.accepted else "none",
            r.status))
    return out


def _applies(rule_calc: tuple[str, ...], rule_work: tuple[str, ...], g: Labels) -> bool:
    return g.calc in rule_calc or bool(set(rule_work) & g.work)


def count_violations(
    room: str, cands: list[Candidate], gold: dict[str, Labels]
) -> tuple[int, list[str]]:
    """(# recommended, SKUs that break a hard rule or the room restriction per GOLD labels)."""
    kb = load_room_rules().rooms.get(room)
    bad: list[str] = []
    for c in cands:
        sku = c.entry.product.sku
        g = gold[sku]
        if "any" not in g.rooms and room not in g.rooms:
            bad.append(sku)
            continue
        if kb and any(_applies(r.calc, r.work, g) and not (set(r.require_any) & g.props)
                      for r in kb.hard):
            bad.append(sku)
    return len(cands), bad


def rubric_relevance(room: str, calc: str, g: Labels) -> int:
    """0 = wrong type / wrong room / breaks a hard rule; 1 = acceptable; up to 3 = better fit."""
    if g.calc != calc or ("any" not in g.rooms and room not in g.rooms):
        return 0
    kb = load_room_rules().rooms.get(room)
    if kb and any(_applies(r.calc, r.work, g) and not (set(r.require_any) & g.props)
                  for r in kb.hard):
        return 0
    rel = 1
    if room in g.rooms and "any" not in g.rooms:
        rel += 1
    if kb and any(_applies(s.calc, s.work, g) and set(s.prefer) & g.props for s in kb.soft):
        rel += 1
    return rel


@dataclass
class RecommendEval:
    queries: int
    mean_ndcg5: float
    returned: int
    violations: int
    empty_queries: int


def evaluate(
    entries: list[CatalogEntry], items: list[SynthItem], k: int = 5,
    scorer: RelevanceScorer | None = None, relevance_weight: float = 0.0,
) -> RecommendEval:
    gold = {i.product.sku: i.gold for i in items}
    ndcgs: list[float] = []
    returned = violations = empty = 0
    for room in ROOMS:
        for calc in QUERY_CALCS:
            ideal = [rubric_relevance(room, calc, i.gold) for i in items if i.gold.calc == calc]
            if not any(ideal):
                continue  # nothing relevant exists for this (room, need): not a valid query
            rel = None
            if scorer and relevance_weight:
                rel = scorer.scores([e for e in entries if e.calc == calc], room, calc)
            res = recommend(entries, room, calc=calc, top_k=k, relevance=rel,
                            relevance_weight=relevance_weight)
            n, bad = count_violations(room, res.items, gold)
            returned += n
            violations += len(bad)
            empty += not res.items
            ranked = [rubric_relevance(room, calc, gold[c.entry.product.sku]) for c in res.items]
            ndcgs.append(ndcg_at_k(ranked, ideal, k))
    return RecommendEval(len(ndcgs), sum(ndcgs) / len(ndcgs) if ndcgs else 0.0, returned,
                         violations, empty)


def run(n: int = 3000, seed: int = 0) -> tuple[RecommendEval, RecommendEval]:
    """(gold-label catalog, pipeline-predicted catalog) on the unseen-model test split."""
    train, dev, test = split_by_group(generate(n, seed=seed), seed=seed)
    prods, labels = weak_labels([i.product for i in train])
    model = MatchModel().fit(prods, labels, [i.product for i in dev], [i.gold for i in dev])
    results = Matcher(model).match([i.product for i in test])
    return (evaluate(entries_from_gold(test), test),
            evaluate(entries_from_predictions(test, results), test))


def to_markdown(gold_ev: RecommendEval, pred_ev: RecommendEval) -> list[str]:
    def row(name: str, e: RecommendEval) -> str:
        return (f"| {name} | {e.queries} | {e.mean_ndcg5:.3f} | {e.returned} | {e.violations} | "
                f"{e.empty_queries} |")

    return ["", "## Recommendation (SYNTHETIC catalog)", "",
            "- Truth = gold labels; relevance = independent rubric over the same room-rule KB "
            "(measures label-error propagation, not rule correctness)",
            "", "| catalog labels | queries | nDCG@5 | recommended | hard-rule violations | "
            "empty results |", "|---|---|---|---|---|---|",
            row("gold", gold_ev), row("pipeline (rules+model)", pred_ev)]


ABLATION_WEIGHTS = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5)


def run_ablation(n: int = 3000, seed: int = 0) -> list[tuple[float, RecommendEval, RecommendEval]]:
    """nDCG@5 / hard-rule violations vs the embedding-relevance weight (hashing embedder, so it
    runs offline; the server run swaps in a real embedder). Same split as `run`."""
    train, dev, test = split_by_group(generate(n, seed=seed), seed=seed)
    prods, labels = weak_labels([i.product for i in train])
    model = MatchModel().fit(prods, labels, [i.product for i in dev], [i.gold for i in dev])
    results = Matcher(model).match([i.product for i in test])
    gold_e = entries_from_gold(test)
    pred_e = entries_from_predictions(test, results)
    scorer = RelevanceScorer(HashingEmbedder())
    return [(w, evaluate(gold_e, test, scorer=scorer, relevance_weight=w),
             evaluate(pred_e, test, scorer=scorer, relevance_weight=w))
            for w in ABLATION_WEIGHTS]


def ablation_markdown(rows: list[tuple[float, RecommendEval, RecommendEval]]) -> list[str]:
    base = rows[0]
    out = ["", "## Recommendation: embedding-relevance ablation (SYNTHETIC catalog)", "",
           "- Weight of the query-product embedding similarity in the ranking score; 0 = off. "
           "Embedder: hashing (offline). nDCG@5 against the rubric; delta vs weight 0.",
           "", "| weight | nDCG@5 gold | Δ | nDCG@5 pipeline | Δ | violations (pipeline) |",
           "|---|---|---|---|---|---|"]
    for w, g, p in rows:
        out.append(f"| {w} | {g.mean_ndcg5:.3f} | {g.mean_ndcg5 - base[1].mean_ndcg5:+.3f} | "
                   f"{p.mean_ndcg5:.3f} | {p.mean_ndcg5 - base[2].mean_ndcg5:+.3f} | "
                   f"{p.violations} |")
    return out
