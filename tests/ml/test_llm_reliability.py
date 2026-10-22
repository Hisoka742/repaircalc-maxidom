"""Checklist I2: structured output is validated, retried, and the failure rate is reported."""
import json

import httpx
import pytest

from maxicalc.ml.llm_client import LLMClient, LLMError

SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}


def client(replies: list[str], retries: int = 2) -> tuple[LLMClient, list[dict]]:  # type: ignore[type-arg]
    sent: list[dict] = []  # type: ignore[type-arg]
    it = iter(replies)

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": next(it)}}]})

    return LLMClient("http://ollama/v1", "m", retries=retries,
                     transport=httpx.MockTransport(handler)), sent


def test_broken_json_is_retried_then_succeeds_and_is_counted() -> None:
    c, sent = client(["not json", '{"a": 1}'])
    assert c.chat_json("s", "u", SCHEMA) == {"a": 1}
    assert len(sent) == 2
    assert c.stats.calls == 1 and c.stats.parse_failures == 1 and c.stats.failed_calls == 0


def test_a_schema_violation_counts_as_a_parse_failure() -> None:
    c, _ = client(['{"b": 2}', '{"a": 3}'])
    assert c.chat_json("s", "u", SCHEMA)["a"] == 3
    assert c.stats.parse_failures == 1


def test_gives_up_after_the_retries_and_reports_the_rate() -> None:
    c, sent = client(["x", "y", "z"], retries=2)
    with pytest.raises(LLMError):
        c.chat_json("s", "u", SCHEMA)
    assert len(sent) == 3
    assert c.stats.failed_calls == 1 and c.stats.failure_rate == 1.0


def test_thinking_is_switched_off_and_schema_is_sent_to_ollama() -> None:
    c, sent = client(['{"a": 1}'])
    c.chat_json("s", "u", SCHEMA)
    body = sent[0]
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["reasoning_effort"] == "none" and body["temperature"] == 0
