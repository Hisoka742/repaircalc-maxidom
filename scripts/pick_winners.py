"""Read the outputs of embed_bench.py / llm_bench.py, pick the winners, write them down.

    uv run python scripts/pick_winners.py --embed out/embed.txt --llm out/llm.txt \
        [--env .env] [--llm-doc docs/LLM.md] [--report eval/REPORT.md] [--dry-run]

* embedder: highest macro-F1 (ties -> fewer seconds); written to `.env` as EMBEDDER=;
* LLM: most parsed requests, then the explanation check, then lower latency; written as
  LLM_MODEL=;
* the two tables are appended to docs/LLM.md and eval/REPORT.md under a dated heading.
Nothing is invented: a model the benchmark skipped never wins; with no scored row the
corresponding setting is left as it is.
"""
import argparse
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class EmbedRow:
    spec: str
    macro_f1: float
    accuracy: float
    seconds: float


@dataclass(frozen=True)
class LlmRow:
    model: str
    parsed: int
    total: int
    seconds_per_request: float
    explained: int
    seconds_explain: float


_EMBED = re.compile(r"^(\S+)\s+([01]\.\d+)\s+([01]\.\d+)\s+(\d+(?:\.\d+)?)\s*$")
_LLM = re.compile(r"^(\S+)\s+(\d+)/\s*(\d+)\s+(\d+(?:\.\d+)?)\s+(\d+)/1\s+(\d+(?:\.\d+)?)\s*$")


def parse_embed(text: str) -> list[EmbedRow]:
    rows = []
    for line in text.splitlines():
        m = _EMBED.match(line.strip())
        if m:
            rows.append(EmbedRow(m[1], float(m[2]), float(m[3]), float(m[4])))
    return rows


def parse_llm(text: str) -> list[LlmRow]:
    rows = []
    for line in text.splitlines():
        m = _LLM.match(line.strip())
        if m:
            rows.append(LlmRow(m[1], int(m[2]), int(m[3]), float(m[4]), int(m[5]), float(m[6])))
    return rows


def best_embedder(rows: list[EmbedRow]) -> EmbedRow | None:
    return min(rows, key=lambda r: (-r.macro_f1, r.seconds)) if rows else None


def best_llm(rows: list[LlmRow]) -> LlmRow | None:
    return min(rows, key=lambda r: (-r.parsed, -r.explained, r.seconds_per_request)) \
        if rows else None


def set_env(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], False
    for ln in lines:
        if re.match(rf"^\s*{re.escape(key)}=", ln):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def tables(embed: list[EmbedRow], llm: list[LlmRow]) -> list[str]:
    out = ["", "| embedder | macro-F1 | accuracy | seconds |", "|---|---|---|---|"]
    out += [f"| {r.spec} | {r.macro_f1:.3f} | {r.accuracy:.3f} | {r.seconds:.1f} |"
            for r in sorted(embed, key=lambda r: -r.macro_f1)]
    out += ["", "| LLM | parsed requests | s/request | explanation ok | s |",
            "|---|---|---|---|---|"]
    out += [f"| {r.model} | {r.parsed}/{r.total} | {r.seconds_per_request:.2f} | "
            f"{r.explained}/1 | {r.seconds_explain:.2f} |"
            for r in sorted(llm, key=lambda r: (-r.parsed, r.seconds_per_request))]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--embed")
    ap.add_argument("--llm")
    ap.add_argument("--env", default=".env")
    ap.add_argument("--llm-doc", default="docs/LLM.md")
    ap.add_argument("--report", default="eval/REPORT.md")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    embed = parse_embed(Path(a.embed).read_text(encoding="utf-8")) if a.embed else []
    llm = parse_llm(Path(a.llm).read_text(encoding="utf-8")) if a.llm else []
    e, m = best_embedder(embed), best_llm(llm)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    block = [f"## Benchmark run {stamp}", *tables(embed, llm), ""]
    block.append(f"- Winner embedder: {e.spec if e else 'not measured'}")
    block.append(f"- Winner LLM: {m.model if m else 'not measured'}")
    print("\n".join(block))
    if a.dry_run:
        return 0
    env = Path(a.env)
    if e:
        set_env(env, "EMBEDDER", e.spec)
    if m:
        set_env(env, "LLM_MODEL", m.model)
    for target in (Path(a.llm_doc), Path(a.report)):
        if target.exists():
            target.write_text(target.read_text(encoding="utf-8").rstrip() + "\n\n"
                              + "\n".join(block) + "\n", encoding="utf-8")
    return 0 if (e or m) else 2


if __name__ == "__main__":
    sys.exit(main())
