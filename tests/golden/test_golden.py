import pytest

from maxicalc.golden import load_cases, run_case


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_golden(case: dict) -> None:  # type: ignore[type-arg]
    r = run_case(case)
    assert r.passed, f"{r.id}: expected {r.expected}, got {r.actual} {r.error or ''}"
