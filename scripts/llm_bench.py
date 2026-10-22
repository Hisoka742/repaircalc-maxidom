"""Compare local LLMs (served by Ollama) on the two jobs the product gives them.

    uv run python scripts/llm_bench.py qwen3:14b gigachat3.1 [--base-url http://localhost:11434/v1]

Jobs:
  1. free-text request -> structured calculator input (checked against the expected fields);
  2. "why these materials" explanation (checked: cites only known facts, no invented numbers).
Reports, per model: pass rate, mean latency, and the failure reasons. The product never asks an
LLM to calculate, so there is no arithmetic benchmark. Needs a reachable Ollama; without one it
exits with code 2 and says so.

Candidates for the RTX 3090 (24 GB) server: qwen3:14b, qwen3:32b (Q4), the GigaChat 3.1 GGUF
imported with `ollama pull hf.co/ai-sage/GigaChat3.1-10B-A1.8B-GGUF:Q8_0`.
"""
import argparse
import sys
import time
from decimal import Decimal as D

import httpx

from maxicalc.ml.llm_client import LLMClient, LLMError
from maxicalc.ml.parse_request import parse_llm
from maxicalc.recommend import rag

PARSE_SET: list[tuple[str, dict[str, object]]] = [
    ("Квартира, капитальный ремонт, санузел 6 м², высокая влажность",
     {"renovation_class": "major", "rooms": {("bathroom", D(6))}}),
    ("Хочу косметический ремонт кухни 9 квадратов и спальни 14 метров",
     {"renovation_class": "cosmetic", "rooms": {("kitchen", D(9)), ("bedroom", D(14))}}),
    ("Дом 120 м2, дизайнерский ремонт, детская 12 м2",
     {"renovation_class": "designer", "rooms": {("kids", D(12))}, "property_type": "house"}),
    ("Нужно обновить ванную 4,5 м2 в студии, влажность высокая",
     {"rooms": {("bathroom", D("4.5"))}, "property_type": "studio"}),
]


def bench_parse(llm: LLMClient) -> tuple[int, list[str], float]:
    ok, why, t0 = 0, [], time.perf_counter()
    for text, want in PARSE_SET:
        try:
            p = parse_llm(text, llm)
        except LLMError as e:
            why.append(f"«{text[:30]}…»: {e}")
            continue
        got = {(r.room_type, r.area_m2) for r in p.rooms}
        good = want["rooms"] <= got  # type: ignore[operator]
        for k in ("renovation_class", "property_type"):
            if k in want and getattr(p, k) != want[k]:
                good = False
        if good:
            ok += 1
        else:
            why.append(f"«{text[:30]}…»: получено {sorted(map(str, got))}, "
                       f"{p.renovation_class}/{p.property_type}")
    return ok, why, (time.perf_counter() - t0) / len(PARSE_SET)


def bench_explain(llm: LLMClient) -> tuple[int, list[str], float]:
    ctx = rag.Context(
        rooms=[("bathroom", "6")],
        lines=[rag.LineCtx("D1", "Гипсокартон влагостойкий", "drywall", 10, "лист", "5160",
                           "подходит для ванной"),
               rag.LineCtx("T1", "Плитка напольная противоскользящая", "tile", 5, "уп", "2860",
                           "подходит для ванной")],
        total="8020", warnings=[], overlays={"wet_zone"}, room_names_ru={"bathroom": "Ванная"})
    t0 = time.perf_counter()
    out = rag.explain(ctx, llm)
    dt = time.perf_counter() - t0
    return (1, [], dt) if out.method == "llm" else (0, [out.note or "шаблон"], dt)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--base-url", default="http://localhost:11434/v1")
    a = ap.parse_args()
    try:
        httpx.get(a.base_url.rstrip("/") + "/models", timeout=5).raise_for_status()
    except httpx.HTTPError as e:
        print(f"ОШИБКА: Ollama недоступна по {a.base_url}: {e}")
        return 2
    print(f"{'модель':28} {'разбор текста':>14} {'с на запрос':>12} {'объяснение':>11} {'с':>6}")
    for m in a.models:
        llm = LLMClient(a.base_url, m, retries=0, timeout=120)
        po, pw, pt = bench_parse(llm)
        eo, ew, et = bench_explain(llm)
        print(f"{m:28} {po}/{len(PARSE_SET):>12} {pt:12.2f} {eo}/1{'':>9} {et:6.2f}")
        for w in [*pw, *ew][:6]:
            print(f"   ! {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
