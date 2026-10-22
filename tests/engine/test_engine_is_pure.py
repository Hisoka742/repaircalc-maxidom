"""Engine rule 1: engine/ is pure — no I/O, network, DB or ML imports."""
import ast
from pathlib import Path

FORBIDDEN = {"requests", "httpx", "redis", "sqlalchemy", "psycopg", "fastapi", "torch",
             "transformers", "sklearn", "socket", "urllib", "openai", "maxicalc.ml",
             "maxicalc.api", "maxicalc.catalog"}
ENGINE = Path(__file__).resolve().parents[2] / "src" / "maxicalc" / "engine"


def test_engine_has_no_forbidden_imports() -> None:
    bad: list[str] = []
    for f in ENGINE.rglob("*.py"):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            bad += [f"{f.name}: {n}" for n in names
                    if any(n == x or n.startswith(x + ".") for x in FORBIDDEN)]
    assert not bad, bad
