from pathlib import Path

import pytest

from maxicalc.golden import load_cases, run_all

EXTRA = """
cases:
  - id: org-001
    calc: paint_liters
    kind: continuous
    inputs: {area: 30, spread: 10, layers: 2}
    expected: 6
    source: organiser reference sheet (test)
    verified: true
  - id: org-002
    calc: paint_liters
    kind: continuous
    inputs: {area: 30, spread: 10, layers: 2}
    expected: 7.5            # deliberately different from the engine -> must show as a deviation
    source: organiser reference sheet (test)
    verified: true
"""


def test_extra_cases_are_merged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "organizer_golden.yaml"
    f.write_text(EXTRA, encoding="utf-8")
    monkeypatch.setenv("GOLDEN_EXTRA", str(f))
    ids = {c["id"] for c in load_cases()}
    assert {"org-001", "org-002", "wp-001"} <= ids


def test_deviation_from_reference_value_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "organizer_golden.yaml"
    f.write_text(EXTRA, encoding="utf-8")
    monkeypatch.setenv("GOLDEN_EXTRA", str(f))
    by_id = {r.id: r for r in run_all()}
    assert by_id["org-001"].passed
    bad = by_id["org-002"]
    assert not bad.passed and bad.expected == 7.5 and bad.actual == 6


def test_duplicate_ids_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "dup.yaml"
    f.write_text(EXTRA.replace("org-002", "wp-001"), encoding="utf-8")
    monkeypatch.setenv("GOLDEN_EXTRA", str(f))
    with pytest.raises(ValueError, match="wp-001"):
        load_cases()


def test_missing_extra_file_is_an_error_not_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOLDEN_EXTRA", str(tmp_path / "nope.yaml"))
    with pytest.raises(FileNotFoundError):
        load_cases()


def test_no_extra_means_only_builtin_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOLDEN_EXTRA", raising=False)
    assert all(not c["id"].startswith("org-") for c in load_cases())
