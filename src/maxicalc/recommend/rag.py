"""RAG for the "why these materials" explanation.

Retrieval is deterministic (tags: product type, room type, overlay). The local LLM may only
rephrase the retrieved facts and the estimate's own numbers; it never calculates. Anything it
returns is checked: it may cite only retrieved fact ids, and every number in its text must
already appear in the context. If the model is unavailable or fails a check, the explanation is
built from templates. The caller is told which path produced the text.
"""
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml

from maxicalc.ml.llm_client import LLMClient, LLMError

GUIDES = Path(__file__).resolve().parents[1] / "knowledge" / "guides.yaml"
MAX_FACTS = 8
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass(frozen=True)
class Fact:
    id: str
    text: str
    source: str
    calc: tuple[str, ...] = ()
    room: tuple[str, ...] = ()
    overlay: tuple[str, ...] = ()


DOCS = Path(__file__).resolve().parents[1] / "knowledge" / "docs"


def _csv(v: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in v.split(",") if x.strip())


def load_doc_chunks(folder: Path = DOCS) -> list[Fact]:
    """Paragraphs of the markdown documents in knowledge/docs, each with its source.

    A document is `key: value` header lines (source, calc, room, overlay), a blank line, then
    paragraphs. No `source` header = the file is ignored (an unsourced fact is not a fact)."""
    out: list[Fact] = []
    for f in sorted(folder.glob("*.md")) if folder.exists() else []:
        head, _, body = f.read_text(encoding="utf-8").partition("\n\n")
        meta = {}
        for line in head.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        if "source" not in meta:
            continue
        for n, para in enumerate(p.strip() for p in body.split("\n\n")):
            if para:
                out.append(Fact(
                    f"{f.stem}#{n + 1}", para, meta["source"], _csv(meta.get("calc", "")),
                    _csv(meta.get("room", "")), _csv(meta.get("overlay", ""))))
    return out


@cache
def load_facts(path: Path = GUIDES) -> tuple[Fact, ...]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    curated = [Fact(f["id"], f["text"], f["source"], tuple(f.get("calc") or ()),
                    tuple(f.get("room") or ()), tuple(f.get("overlay") or ()))
               for f in raw["facts"]]
    return tuple(curated + load_doc_chunks())


def retrieve(calcs: set[str], rooms: set[str], overlays: set[str],
             k: int = MAX_FACTS) -> list[Fact]:
    """Facts that match the basket's product types and the rooms/overlays involved.

    Score: +2 for a product-type match, +1 for a room match, +1 for an overlay match; facts with
    tags that do not match anything are dropped; generic facts (no tags) rank last but are kept."""
    scored: list[tuple[int, int, Fact]] = []
    for i, f in enumerate(load_facts()):
        if not (f.calc or f.room or f.overlay):
            scored.append((0, i, f))
            continue
        c = 2 if set(f.calc) & calcs else 0
        r = 1 if set(f.room) & rooms else 0
        o = 1 if set(f.overlay) & overlays else 0
        if f.calc and not c:
            continue
        if (f.room or f.overlay) and not (r or o):
            continue
        scored.append((c + r + o, i, f))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [f for _, _, f in scored[:k]]


@dataclass
class LineCtx:
    sku: str
    name: str
    calc: str
    qty_packs: int
    unit: str
    line_total: str
    reason: str


@dataclass
class Context:
    rooms: list[tuple[str, str]]          # (room type, area as string)
    lines: list[LineCtx]
    total: str
    warnings: list[str]
    overlays: set[str] = field(default_factory=set)
    room_names_ru: dict[str, str] = field(default_factory=dict)


@dataclass
class Explanation:
    text: str
    method: Literal["llm", "template"]
    facts: list[Fact]
    note: str = ""


def _template(ctx: Context, facts: list[Fact]) -> str:
    rooms = ", ".join(f"{ctx.room_names_ru.get(r, r).lower()} {a} м²" for r, a in ctx.rooms)
    parts = [f"Смета рассчитана для: {rooms}." if rooms else "Смета рассчитана по вашим данным."]
    for ln in ctx.lines[:6]:
        parts.append(f"{ln.name}: {ln.qty_packs} {ln.unit} — {ln.reason}.")
    for f in facts[:4]:
        parts.append(f.text)
    parts.append(f"Итого материалов: {ctx.total} ₽.")
    return " ".join(parts)


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"explanation": {"type": "string"},
                   "used_fact_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["explanation", "used_fact_ids"],
    "additionalProperties": False,
}
SYSTEM = (
    "Ты помощник строительного магазина. Объясни покупателю по-русски, в 3–5 коротких "
    "предложениях, почему подобраны эти материалы. Используй ТОЛЬКО блок ФАКТЫ и данные сметы. "
    "Не вычисляй, не округляй и не придумывай числа: называй только числа, которые есть в "
    "данных. В used_fact_ids перечисли id фактов, на которые опираешься."
)


def _numbers(s: str) -> set[str]:
    return {n.replace(",", ".") for n in _NUM.findall(s)}


def _prompt(ctx: Context, facts: list[Fact]) -> str:
    rooms = "; ".join(f"{ctx.room_names_ru.get(r, r)} {a} м²" for r, a in ctx.rooms)
    lines = "\n".join(f"- {ln.name}: {ln.qty_packs} {ln.unit}, {ln.line_total} ₽ ({ln.reason})"
                      for ln in ctx.lines)
    fl = "\n".join(f"[{f.id}] {f.text}" for f in facts)
    return f"ПОМЕЩЕНИЯ: {rooms}\nСМЕТА:\n{lines}\nИтого: {ctx.total} ₽\nФАКТЫ:\n{fl}"


def explain(ctx: Context, llm: LLMClient | None) -> Explanation:
    calcs = {ln.calc for ln in ctx.lines}
    facts = retrieve(calcs, {r for r, _ in ctx.rooms}, ctx.overlays)
    base = Explanation(_template(ctx, facts), "template", facts)
    if llm is None:
        return base
    prompt = _prompt(ctx, facts)
    try:
        out = llm.chat_json(SYSTEM, prompt, SCHEMA)
    except LLMError as e:
        base.note = f"LLM недоступен, использован шаблон: {e}"
        return base
    text = str(out.get("explanation", "")).strip()
    used = out.get("used_fact_ids") or []
    ids = {f.id for f in facts}
    if not text:
        base.note = "LLM вернул пустой ответ, использован шаблон"
        return base
    if not isinstance(used, list) or not set(map(str, used)) <= ids:
        base.note = "LLM сослался на неизвестные факты, использован шаблон"
        return base
    extra = _numbers(text) - _numbers(prompt)
    if extra:
        base.note = ("LLM назвал числа, которых нет в данных "
                     f"({', '.join(sorted(extra))}), использован шаблон")
        return base
    cited = [f for f in facts if f.id in set(map(str, used))] or facts[:3]
    return Explanation(text, "llm", cited)
