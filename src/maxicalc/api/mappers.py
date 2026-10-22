"""Domain objects -> API schemas."""
from maxicalc.api import schemas as s
from maxicalc.api.state import AppState
from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract
from maxicalc.ml.match import LabelDecision, MatchResult
from maxicalc.recommend.select import Candidate
from maxicalc.service.property_calc import PropertyEstimate

EXCLUDED_LIMIT = 50


def estimate_out(est: PropertyEstimate, estimate_id: str, kind: str, version: str) -> s.EstimateOut:
    return s.EstimateOut(
        estimate_id=estimate_id, kind=kind,  # type: ignore[arg-type]
        catalog_version=version,
        rooms=[s.RoomOut(room_type=r.room_type, area_m2=r.area_m2, height_m=r.height_m,
                         humidity=r.humidity, load=r.load) for r in est.rooms],
        basket=s.BasketOut(
            lines=[s.BasketLineOut(
                sku=ln.sku, product_id=ln.product_id, url=ln.url, name=ln.name,
                qty_packs=ln.qty_packs, unit=ln.unit,
                unit_price=ln.unit_price, line_total=ln.line_total, reason=ln.reason,
                group=ln.group, optimized=ln.optimized,
                explain=ln.explain,
                alternatives=[s.AlternativeOut(**a) for a in ln.alternatives])  # type: ignore[arg-type]
                for ln in est.basket.lines],
            materials_total=est.basket.materials_total,
            optimized_total=est.basket.optimized_total,
            groups=[s.GroupOut(key=g.key, title=g.title, total=g.total, skus=g.skus)
                    for g in est.basket.groups]),
        warnings=est.warnings, assumptions=est.assumptions,
        labor=None if est.labor is None else s.LaborOut(
            low=est.labor.low, expected=est.labor.expected, high=est.labor.high,
            items=[s.LaborItemOut(work=i.work, title=i.title, quantity=i.quantity, unit=i.unit,
                                  rate=i.rate, expected=i.expected) for i in est.labor.items],
            explain=est.labor.explain),
        labor_note=est.labor_note,
        electrical=[s.ElectricalOut(
            room=room, sockets=e.sockets, switches=e.switches, light_points=e.light_points,
            junction_boxes=e.junction_boxes, cable_m=e.cable_m, breakers=e.breakers)
            for room, e in est.electrical],
    )


def candidate_out(c: Candidate) -> s.CandidateOut:
    p = c.entry.product
    return s.CandidateOut(sku=p.sku, product_id=p.product_id, rating=p.rating, in_stock=p.in_stock,
                          name=p.name, price=p.price, calc=c.entry.calc,
                          score=c.score, price_tier=c.price_tier, reasons=c.reasons)


def label_out(d: LabelDecision) -> s.LabelOut:
    return s.LabelOut(label=d.label, confidence=round(d.confidence, 4), source=d.source,
                      accepted=d.accepted, reason=d.reason)


def match_item(p: Product, r: MatchResult) -> s.MatchItemOut:
    attrs = {k: str(a.value) for k, a in extract(p).attrs.items()}
    return s.MatchItemOut(
        sku=r.sku, status=r.status,
        calc_template=label_out(r.calc_template) if r.calc_template else None,
        work_categories=[label_out(d) for d in r.work_categories],
        room_types=[label_out(d) for d in r.room_types],
        properties=[label_out(d) for d in r.properties],
        attributes=attrs, reasons=r.reasons)


def match_products(state: AppState, products: list[Product]) -> list[s.MatchItemOut]:
    results = state.matcher.match(products)
    return [match_item(p, r) for p, r in zip(products, results, strict=True)]
