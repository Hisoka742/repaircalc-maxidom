"""Checklist H1: knowledge-base documents are chunked and carry their source."""
from pathlib import Path

from maxicalc.recommend import rag


def test_shipped_documents_are_chunked_with_their_source() -> None:
    chunks = rag.load_doc_chunks()
    ids = {c.id for c in chunks}
    assert {"ceresit_cr65#1", "ceresit_cr65#2", "ceresit_cm11#1"} <= ids
    cr = next(c for c in chunks if c.id == "ceresit_cr65#1")
    assert "Ceresit CR 65" in cr.source and "3,5" in cr.text
    assert cr.calc == ("waterproofing",) and "bathroom" in cr.room


def test_retrieval_returns_the_document_chunk_with_its_source() -> None:
    facts = rag.retrieve({"waterproofing"}, {"bathroom"}, {"wet_zone"})
    cr = [f for f in facts if f.id.startswith("ceresit_cr65")]
    assert cr and all("Ceresit CR 65" in f.source for f in cr)
    # an unrelated product type does not pull the waterproofing document
    other = rag.retrieve({"laminate"}, {"living"}, set())
    assert not [f for f in other if f.id.startswith("ceresit_cr65")]


def test_a_document_without_a_source_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text("calc: paint\n\nУтверждение без источника.\n", encoding="utf-8")
    (tmp_path / "y.md").write_text("source: тест\ncalc: paint\n\nПервый.\n\nВторой.\n",
                                   encoding="utf-8")
    got = rag.load_doc_chunks(tmp_path)
    assert [c.id for c in got] == ["y#1", "y#2"]
