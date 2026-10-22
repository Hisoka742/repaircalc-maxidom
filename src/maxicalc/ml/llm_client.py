"""OpenAI-compatible chat client for Ollama (also vLLM / llama.cpp) with JSON-schema output.

The LLM is only ever used to read text into structured fields, never to calculate. Output is
requested with the JSON schema, validated here (required keys and types), and retried on a parse
failure; `stats` reports how often that happened (the parse-failure rate the checklist asks for).
"""
import json
from dataclasses import dataclass
from typing import Any

import httpx


class LLMError(RuntimeError):
    pass


@dataclass
class LLMStats:
    calls: int = 0              # chat_json invocations
    attempts: int = 0           # HTTP requests sent (calls + retries)
    parse_failures: int = 0     # attempts whose content was not valid JSON for the schema
    http_failures: int = 0      # attempts that failed at the network/HTTP level
    failed_calls: int = 0       # calls that ended in LLMError

    @property
    def failure_rate(self) -> float:
        return self.failed_calls / self.calls if self.calls else 0.0

    @property
    def parse_failure_rate(self) -> float:
        return self.parse_failures / self.attempts if self.attempts else 0.0


_TYPES: dict[str, Any] = {
    "string": str, "boolean": bool, "array": list, "object": dict, "null": type(None),
    "integer": int, "number": (int, float),
}


def _type_ok(v: Any, t: str | list[str]) -> bool:
    names = t if isinstance(t, list) else [t]
    for n in names:
        py = _TYPES.get(n)
        if py is None:
            return True
        if n in ("integer", "number") and isinstance(v, bool):
            continue
        if isinstance(v, py):
            return True
    return False


def conforms(data: Any, schema: dict[str, Any]) -> bool:
    """Small structural check (type, required, properties, enum, array items). Not a full JSON
    Schema implementation: enough to reject what would break the code that reads the result."""
    t = schema.get("type")
    if t is not None and not _type_ok(data, t):
        return False
    if "enum" in schema and data not in schema["enum"]:
        return False
    if isinstance(data, dict):
        props = schema.get("properties", {})
        if any(k not in data for k in schema.get("required", [])):
            return False
        return all(conforms(v, props[k]) for k, v in data.items() if k in props)
    if isinstance(data, list) and "items" in schema:
        return all(conforms(x, schema["items"]) for x in data)
    return True


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 60.0,
        retries: int = 2,
        no_think: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.retries = retries
        self.no_think = no_think
        self.stats = LLMStats()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(timeout=timeout, headers=headers, transport=transport)

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": True},
            },
        }
        if self.no_think:
            body["reasoning_effort"] = "none"  # Ollama: no thinking phase (qwen3-style models)
        self.stats.calls += 1
        last = "нет ответа"
        for _ in range(self.retries + 1):
            self.stats.attempts += 1
            try:
                r = self._http.post(f"{self.base_url}/chat/completions", json=body)
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                self.stats.http_failures += 1
                last = f"LLM недоступен: {e}"
                continue
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                self.stats.parse_failures += 1
                last = f"LLM вернул не JSON: {e}"
                continue
            if not isinstance(data, dict) or not conforms(data, schema):
                self.stats.parse_failures += 1
                last = "LLM вернул JSON, не соответствующий схеме"
                continue
            return data
        self.stats.failed_calls += 1
        raise LLMError(last)
