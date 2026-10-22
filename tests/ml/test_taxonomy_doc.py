"""docs/TAXONOMY.md is generated from the YAML and defines every work type."""
import importlib.util
from pathlib import Path

from maxicalc.ml.worktypes import work_type_ids

ROOT = Path(__file__).resolve().parents[2]


def test_every_work_type_has_a_definition_and_the_doc_is_current() -> None:
    spec = importlib.util.spec_from_file_location("make_taxonomy_doc",
                                                  ROOT / "scripts" / "make_taxonomy_doc.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert set(m.DEFS) == set(work_type_ids())
    assert (ROOT / "docs" / "TAXONOMY.md").read_text(encoding="utf-8") == m.build()
