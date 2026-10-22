"""pick_winners reads the real bench output formats and never lets a skipped model win."""
import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "pick_winners", Path(__file__).resolve().parents[2] / "scripts" / "pick_winners.py")
assert SPEC and SPEC.loader
pw = importlib.util.module_from_spec(SPEC)
sys.modules["pick_winners"] = pw
SPEC.loader.exec_module(pw)

EMBED = """train 2000, test 1000 (SYNTHETIC; unseen product groups in test)
модель                                           macro-F1  accuracy       с
hashing                                             0.812     0.850     1.2
st:ai-forever/FRIDA                                 0.903     0.921    40.5
st:intfloat/multilingual-e5-base                    0.903     0.920    22.0
ollama:bge-m3                                    пропущена: connection refused
"""
LLM = """модель                         разбор текста  с на запрос  объяснение      с
qwen3:14b                              9/10         2.10 1/1           3.50
qwen3:8b                               8/10         1.00 1/1           1.50
"""


def test_parse_and_pick_embedder_prefers_f1_then_speed() -> None:
    rows = pw.parse_embed(EMBED)
    assert [r.spec for r in rows] == ["hashing", "st:ai-forever/FRIDA",
                                      "st:intfloat/multilingual-e5-base"]
    assert pw.best_embedder(rows).spec == "st:intfloat/multilingual-e5-base"   # tie, faster


def test_pick_llm_by_parsed_requests() -> None:
    rows = pw.parse_llm(LLM)
    assert len(rows) == 2 and pw.best_llm(rows).model == "qwen3:14b"


def test_set_env_replaces_or_appends(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text("A=1\nEMBEDDER=hashing\n", encoding="utf-8")
    pw.set_env(f, "EMBEDDER", "st:x")
    pw.set_env(f, "LLM_MODEL", "qwen3:14b")
    assert f.read_text(encoding="utf-8").splitlines() == ["A=1", "EMBEDDER=st:x",
                                                          "LLM_MODEL=qwen3:14b"]


def test_nothing_measured_picks_nothing() -> None:
    assert pw.best_embedder([]) is None and pw.best_llm([]) is None
