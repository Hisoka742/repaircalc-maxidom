"""LLM judge for the uncertain zone (checklist G3, step 4).

Only products the rules and the model could not decide reach it, and it may only choose among
the candidates it is offered. Its answer is a SUGGESTION for the review queue: it is never
auto-accepted on its own, and any failure returns None (the product just stays in the queue).
"""
from dataclasses import dataclass

from maxicalc.catalog.schema import Product
from maxicalc.ml.embed import product_text
from maxicalc.ml.llm_client import LLMClient, LLMError

SYSTEM = (
    "Ты помогаешь разметить товар строительного магазина. Выбери ОДИН тип из списка кандидатов, "
    "который лучше всего описывает товар по названию, категории и характеристикам. Если "
    "ничего не подходит, выбери none. Ничего не вычисляй."
)


@dataclass(frozen=True)
class Judged:
    calc: str
    reason: str


def judge_uncertain(p: Product, candidates: list[str], llm: LLMClient) -> Judged | None:
    options = list(dict.fromkeys([*candidates, "none"]))
    schema = {
        "type": "object",
        "properties": {"calc": {"type": "string", "enum": options},
                       "reason": {"type": "string"}},
        "required": ["calc", "reason"], "additionalProperties": False,
    }
    prompt = f"ТОВАР: {product_text(p)}\nОписание: {p.description[:600]}\nКАНДИДАТЫ: " + \
        ", ".join(options)
    try:
        out = llm.chat_json(SYSTEM, prompt, schema)
    except LLMError:
        return None
    calc = out.get("calc")
    if calc not in options:
        return None
    return Judged(str(calc), str(out.get("reason", ""))[:300])
