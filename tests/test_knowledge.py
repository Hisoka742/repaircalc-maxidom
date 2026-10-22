from maxicalc.engine import electrical, labor
from maxicalc.knowledge.loader import load_electrical_norms, load_labor_params, load_work_rates

ROOMS = {"living", "bedroom", "kids", "kitchen", "bathroom", "hallway", "balcony"}


def test_electrical_norms_cover_all_room_types() -> None:
    norms = load_electrical_norms()
    assert set(norms) >= ROOMS
    assert all(isinstance(n, electrical.RoomNorms) for n in norms.values())
    # every room yields a usable estimate
    for room in ROOMS:
        assert electrical.estimate(room, 10, norms).points > 0


def test_work_rates_never_unsourced() -> None:
    """A price may only be filled in if it has a real source (no invented rates)."""
    rates = load_work_rates()
    assert rates, "work_rates.yaml is empty"
    for r in rates.values():
        assert isinstance(r, labor.WorkRate)
        if r.rub_per_unit is not None:
            assert r.source and "TODO" not in r.source and "unsourced" not in r.source.lower(), r


def test_labor_params_load() -> None:
    p = load_labor_params()
    assert set(p.class_tier) == set(p.scope) == {"cosmetic", "major", "designer"}
    assert p.class_tier == {"cosmetic": "p25", "major": "median", "designer": "p75"}
    assert p.scope["cosmetic"] < p.scope["major"]            # major adds works, not a multiplier
    assert p.region_coeff["spb"] == 1


def test_knowledge_files_are_parsed_once_not_per_request() -> None:
    """Re-parsing norms.yaml per room was ~90% of estimate latency (found by profiling)."""
    assert load_electrical_norms() is load_electrical_norms()
