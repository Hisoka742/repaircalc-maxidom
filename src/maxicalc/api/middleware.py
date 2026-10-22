"""Pure-ASGI middleware: rate limit, request id, structured access log, Prometheus metrics.

Pure ASGI (not BaseHTTPMiddleware) to keep per-request overhead in microseconds.
"""
import json
import time
import uuid
from typing import Any

import structlog
from prometheus_client import Counter, Gauge, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = structlog.get_logger()

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["route"],
    buckets=(0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
RATE_LIMITED = Counter("rate_limited_total", "Requests rejected by the rate limiter")
ESTIMATE_CACHE = Counter("estimate_cache_total", "Estimate cache lookups", ["result"])
CATALOG_SIZE = Gauge("catalog_products", "Products in the loaded catalog")
REVIEW_PENDING = Gauge("review_queue_pending", "Items waiting for human review")

UNMETERED = ("/health", "/metrics")


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp, log_requests: bool = True) -> None:
        self.app = app
        self.log_requests = log_requests

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        rid = next((v.decode() for k, v in scope["headers"] if k == b"x-request-id"), None)
        rid = (rid or uuid.uuid4().hex[:16])[:64]
        scope.setdefault("state", {})["request_id"] = rid
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            dur = time.perf_counter() - start
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            REQUESTS.labels(scope["method"], route, str(status)).inc()
            LATENCY.labels(route).observe(dur)
            path = scope["path"]
            if self.log_requests and path not in UNMETERED:
                log.info("request", request_id=rid, method=scope["method"], path=path,
                         status=status, ms=round(dur * 1000, 2))


class RateLimitMiddleware:
    """Token bucket per client IP. /health and /metrics are exempt."""

    def __init__(self, app: ASGIApp, per_min: int, burst: int) -> None:
        self.app = app
        self.rate = per_min / 60.0
        self.burst = float(max(burst, 1))
        self.buckets: dict[str, tuple[float, float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.rate <= 0 or scope["path"] in UNMETERED:
            await self.app(scope, receive, send)
            return
        ip = scope["client"][0] if scope.get("client") else "unknown"
        now = time.monotonic()
        tokens, last = self.buckets.get(ip, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        if tokens < 1:
            RATE_LIMITED.inc()
            retry = max(1, int((1 - tokens) / self.rate) + 1)
            self.buckets[ip] = (tokens, now)
            await _json(send, 429, {"error": {
                "code": "rate_limited", "details": [],
                "message": f"Слишком много запросов. Повторите через {retry} с."}},
                [(b"retry-after", str(retry).encode())])
            return
        self.buckets[ip] = (tokens - 1, now)
        if len(self.buckets) > 20000:  # drop idle clients
            cutoff = now - 3600
            self.buckets = {k: v for k, v in self.buckets.items() if v[1] > cutoff}
        await self.app(scope, receive, send)


async def _json(send: Send, status: int, body: dict[str, Any],
                extra: list[tuple[bytes, bytes]]) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(raw)).encode()), *extra]})
    await send({"type": "http.response.body", "body": raw})


def configure_logging(json_logs: bool) -> None:
    import logging

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    processors.append(structlog.processors.JSONRenderer(ensure_ascii=False) if json_logs
                      else structlog.dev.ConsoleRenderer())
    structlog.configure(processors=processors,
                        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))
