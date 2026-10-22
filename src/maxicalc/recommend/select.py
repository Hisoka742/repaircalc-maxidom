"""Product selection: hard filters -> scoring -> deterministic top-k, with reasons.

Operates on precomputed catalog labels (CatalogEntry); no ML or LLM at request time.
Conservative: a property that is not an accepted label counts as absent.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from maxicalc.catalog.schema import Product
from maxicalc.ml.roles import main_calcs
from maxicalc.recommend.explain import reasons as make_reasons
from maxicalc.recommend.rules_kb import HardRule, SoftRule, merged_rules
from maxicalc.recommend.tiers import TIER_TARGET_RANK, PriceScale

ROOM_SPECIFIC_BONUS = 0.5
TIER_WEIGHT = 1.0
POPULARITY_WEIGHT = 0.3


@dataclass(frozen=True)
class Inferred:
    """An attribute read out of the card text by the LLM: never a fact until trusted."""
    value: Decimal | int | str
    confidence: str          # low | medium | high
    evidence: str            # the quote it was taken from
    source: str = "llm"


@dataclass(frozen=True)
class CatalogEntry:
    product: Product
    work: set[str]
    rooms: set[str]
    props: set[str]
    calc: str
    status: str = "auto"   # "auto" | "review" | "verified"
    attrs: dict[str, Decimal | int | str] = field(default_factory=dict)  # facts (regex/card)
    inferred: dict[str, Inferred] = field(default_factory=dict)          # LLM-read, with confidence
    role: str = "main"   # main | accessory | tool | consumable | ppe | other (ml/roles.py)


@dataclass(frozen=True)
class Constraints:
    max_price: Decimal | None = None
    min_price: Decimal | None = None
    brands: frozenset[str] | None = None
    tier: str | None = None   # economy | standard | premium
    region_id: str | None = None   # only products in stock in this region


@dataclass
class Candidate:
    entry: CatalogEntry
    score: float
    reasons: list[str]
    price_tier: str | None = None


@dataclass
class RecommendResult:
    items: list[Candidate] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)   # (sku, reason)
    warnings: list[str] = field(default_factory=list)
    companions: list[Candidate] = field(default_factory=list)   # accessories + protective gear


def completeness(e: CatalogEntry) -> float:
    """0..1: how much of what the calculator needs is on the card (60%), plus how well the card is
    described (non-empty characteristics, saturating at 8) and priced (40%)."""
    from maxicalc.service.requirements import REQUIREMENTS, missing_attrs

    if e.calc in REQUIREMENTS:
        req, any_of = REQUIREMENTS[e.calc]
        total = len(req) + (1 if any_of else 0)
        have = total - len(missing_attrs(e.calc, e.attrs))
        calc_part = have / total if total else 1.0
    else:
        calc_part = 1.0
    chars = min(len(e.product.characteristics), 8) / 8
    priced = 1.0 if e.product.price is not None else 0.0
    return 0.6 * calc_part + 0.3 * chars + 0.1 * priced


def _applies(rule: HardRule | SoftRule, e: CatalogEntry) -> bool:
    return e.calc in rule.calc or bool(set(rule.work) & e.work)


def recommend(
    catalog: list[CatalogEntry],
    room: str,
    work: str | None = None,
    calc: str | None = None,
    constraints: Constraints | None = None,
    top_k: int = 5,
    include_review: bool = False,
    overlays: tuple[str, ...] = (),
    margin_weight: float = 0.0,
    relevance: dict[str, float] | None = None,
    relevance_weight: float = 0.0,
    completeness_weight: float = 0.0,
    rating_weight: float | None = None,
) -> RecommendResult:
    """Hard room constraints first (exclusions), then a score:

        1 + soft room properties + room-specific bonus      (suitability)
          + relevance_weight x embedding relevance          (0: the ablation says it does not help)
          + completeness_weight x card completeness         (calculable, well described products)
          + tier fit when a price tier is asked for
          + rating_weight x rating, margin_weight x margin  (inactive: 0 / the data has no field)

    `rating_weight=None` keeps the legacy small popularity tie-break (POPULARITY_WEIGHT);
    the official dump has no ratings, the service passes 0 explicitly."""
    if work is None and calc is None:
        raise ValueError("Нужно указать вид работ (work) или калькулятор (calc)")
    cons = constraints or Constraints()
    kb = merged_rules(room, overlays)
    res = RecommendResult()

    # accessories, tools, consumables and protective gear are never the MAIN product of a
    # calculator; they are offered as companions (recommend/companions.py)
    typed = [e for e in catalog
             if (calc is None or e.calc == calc) and (work is None or work in e.work)
             and (e.role == "main" or e.calc not in main_calcs())]
    pool_prices = [e.product.price for e in typed if e.product.price is not None]
    scale = PriceScale(pool_prices)  # sorted once, not per candidate

    survivors: list[CatalogEntry] = []
    for e in typed:
        sku = e.product.sku
        if e.status == "review" and not include_review:
            res.excluded.append((sku, "метки не подтверждены (на проверке)"))
            continue
        p0 = e.product
        if p0.active is False or p0.in_stock is False or (
                p0.stock_qty is not None and p0.stock_qty <= 0 and p0.in_stock is not True):
            res.excluded.append((sku, "нет в наличии"))
            continue
        if cons.region_id and p0.stock_regions and (
                p0.stock_regions.get(cons.region_id, 0) <= 0):
            res.excluded.append((sku, "нет в наличии в выбранном регионе"))
            continue
        if "any" not in e.rooms and room not in e.rooms:
            res.excluded.append((sku, "предназначен для другого помещения"))
            continue
        failed = next((r for r in (kb.hard if kb else ())
                       if _applies(r, e) and not (set(r.require_any) & e.props)), None)
        if failed:
            res.excluded.append((sku, failed.reason))
            continue
        price = e.product.price
        if (cons.max_price is not None or cons.min_price is not None or cons.tier) and (
                price is None):
            res.excluded.append((sku, "нет цены"))
            continue
        if price is not None and cons.max_price is not None and price > cons.max_price:
            res.excluded.append((sku, "дороже ограничения"))
            continue
        if price is not None and cons.min_price is not None and price < cons.min_price:
            res.excluded.append((sku, "дешевле ограничения"))
            continue
        if cons.brands and (e.product.brand or "") not in cons.brands:
            res.excluded.append((sku, "другой бренд"))
            continue
        survivors.append(e)

    scored: list[Candidate] = []
    for e in survivors:
        sku = e.product.sku
        score = 1.0
        matched: list[str] = []
        if kb:
            for r in kb.hard:
                if _applies(r, e):
                    matched += sorted(set(r.require_any) & e.props)
            for s in kb.soft:
                if _applies(s, e) and s.prefer:
                    hit = sorted(set(s.prefer) & e.props)
                    score += s.weight * len(hit) / len(s.prefer)
                    matched += hit
        specific = room in e.rooms and "any" not in e.rooms
        if specific:
            score += ROOM_SPECIFIC_BONUS
        # popularity (the stand's recsys_rating, else the shop rating) breaks ties among
        # equally suitable products; deliberately small so it never outranks a hard rule
        pop = e.product.recsys_rating if e.product.recsys_rating is not None else e.product.rating
        rw = POPULARITY_WEIGHT if rating_weight is None else rating_weight
        if pop is not None and rw:
            score += rw * min(1.0, max(0.0, float(pop) / 5.0))
        if completeness_weight:
            score += completeness_weight * completeness(e)
        # margin: configurable and OFF by default (0): the stand has no margin field yet
        if margin_weight and e.product.margin is not None:
            score += margin_weight * min(1.0, max(0.0, float(e.product.margin)))
        # embedding relevance of the product to the query (0 weight = off); never overrides a
        # hard rule, those products were excluded above
        if relevance and relevance_weight:
            score += relevance_weight * min(1.0, max(0.0, relevance.get(sku, 0.0)))
        tier = None
        if e.product.price is not None and len(pool_prices) >= 2:
            tier = scale.tier(e.product.price)
        if cons.tier and e.product.price is not None:
            rank = scale.rank(e.product.price)
            score += TIER_WEIGHT * (1 - abs(rank - TIER_TARGET_RANK[cons.tier]))
        props = list(dict.fromkeys(matched))
        scored.append(Candidate(
            e, round(score, 6),
            make_reasons(room, props, specific, tier if cons.tier else None), tier))
    scored.sort(key=lambda c: (-c.score, c.entry.product.sku))
    res.items = scored[:top_k]
    if not res.items:
        why = f"для «{room}» не найдено подходящих товаров"
        if res.excluded:
            why += f" (отсеяно: {len(res.excluded)}; например: {res.excluded[0][1]})"
        res.warnings.append(why)
    return res
