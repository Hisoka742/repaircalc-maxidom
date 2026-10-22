"""Checklist C7: labor range from a rate table, class multiplier, work quantities from geometry."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Room
from maxicalc.engine.labor import Spread, WorkRate
from maxicalc.knowledge.loader import LaborParams
from maxicalc.recommend.select import CatalogEntry
from maxicalc.service.property_calc import calc_room


def ent(sku: str, calc: str, attrs: dict[str, str]) -> CatalogEntry:
    return CatalogEntry(Product(sku=sku, name=sku, price=D(100)), work=set(), rooms={"any"},
                        props=set(), calc=calc, status="verified",
                        attrs={k: D(v) for k, v in attrs.items()})


CATALOG = [
    ent("P", "paint", {"spread_m2_per_l": "10", "pack_volume_l": "2.5"}),
    ent("R", "primer", {"consumption_l_per_m2": "0.15", "pack_volume_l": "5"}),
    ent("L", "laminate", {"m2_per_pack": "2.131"}),
    ent("U", "underlay", {"m2_per_pack": "10"}),
    ent("S", "skirting", {"piece_len_m": "2.5"}),
]
# floor 12 m2, walls 35 m2, ceiling 12 m2, perimeter 14 m
ROOM = Room.rectangle(4, 3, "2.5")

RATES = {
    "painting_walls": WorkRate("painting_walls", "м²", D(300), "тестовый прайс", D(250), D(400)),
    "priming": WorkRate("priming", "м²", D(80), "тестовый прайс", D(60), D(100)),
    "laminate": WorkRate("laminate", "м²", D(500), "тестовый прайс", D(400), D(600)),
    "skirting": WorkRate("skirting", "м", D(150), "тестовый прайс", D(120), D(200)),
    "electrical_point": WorkRate("electrical_point", "шт", D(900), "тестовый прайс",
                                 D(700), D(1100)),
}
BASIC = ["painting_walls", "priming", "laminate", "skirting"]
PARAMS = LaborParams(
    {"spb": D(1)}, {"cosmetic": "p25", "major": "median", "designer": "p75"},
    {"cosmetic": frozenset(BASIC), "major": frozenset([*BASIC, "electrical_point"]),
     "designer": frozenset([*BASIC, "electrical_point"])}, Spread(D("0.8"), D("1.25")))


def test_labor_is_summed_from_geometry_at_the_class_price_tier_with_range() -> None:
    est = calc_room(ROOM, "living", "cosmetic", CATALOG, labor_rates=RATES,
                    labor_params=PARAMS)
    assert est.labor is not None
    by = {i.work: i for i in est.labor.items}
    assert by["painting_walls"].quantity == D(47)          # walls 35 + ceiling 12
    assert by["laminate"].quantity == D(12)
    assert by["skirting"].quantity == D(14)
    # cosmetic = p25: 47 x 250 + 47 x 60 + 12 x 400 + 14 x 120 = 11750 + 2820 + 4800 + 1680
    assert est.labor.expected == D("21050")
    assert est.labor.low == est.labor.expected * D("0.8")
    assert est.labor.high == est.labor.expected * D("1.25")
    assert any("p25" in e for e in est.labor.explain)


def test_major_uses_the_median_tier_and_adds_wiring_to_the_scope() -> None:
    cosmetic = calc_room(ROOM, "living", "cosmetic", CATALOG, labor_rates=RATES,
                         labor_params=PARAMS).labor
    major = calc_room(ROOM, "living", "major", CATALOG, labor_rates=RATES,
                      labor_params=PARAMS).labor
    assert cosmetic and major
    assert {i.work: i.rate for i in major.items}["laminate"] == D(500)      # median
    assert {i.work: i.rate for i in cosmetic.items}["laminate"] == D(400)   # p25
    narrow = LaborParams(PARAMS.region_coeff, PARAMS.class_tier,
                         {**PARAMS.scope, "cosmetic": frozenset(BASIC) - {"skirting"}},
                         PARAMS.spread)
    cut = calc_room(ROOM, "living", "cosmetic", CATALOG, labor_rates=RATES,
                    labor_params=narrow).labor
    assert cut and "skirting" not in {i.work for i in cut.items}
    assert any("Не входят" in e and "плинтус" in e for e in cut.explain)


def test_a_missing_rate_gives_no_labor_and_names_what_is_missing() -> None:
    thin = {k: v for k, v in RATES.items() if k != "laminate"}
    est = calc_room(ROOM, "living", "cosmetic", CATALOG, labor_rates=thin, labor_params=PARAMS)
    assert est.labor is None
    assert "laminate" in est.labor_note and "Ставки" in est.labor_note


def test_an_unknown_class_gives_no_labor() -> None:
    from maxicalc.service.labor_calc import compute_labor

    res, note = compute_labor([], "luxury", RATES, PARAMS.class_tier, PARAMS.scope,
                              PARAMS.region_coeff, PARAMS.spread)
    assert res is None and "объём работ" in note


def test_shipped_rates_are_sourced_market_benchmarks_and_a_range() -> None:
    est = calc_room(ROOM, "living", "cosmetic", CATALOG)
    assert est.labor is not None and est.labor.low < est.labor.expected < est.labor.high


def test_shipped_classes_differ_by_scope_and_tier_not_by_a_multiplier() -> None:
    cosmetic = calc_room(ROOM, "living", "cosmetic", CATALOG).labor
    major = calc_room(ROOM, "living", "major", CATALOG).labor
    assert cosmetic and major and major.expected > cosmetic.expected
    assert not any("множител" in e.lower() for e in cosmetic.explain)