"""Open-loop HTTP load test (fixed arrival rate, so slow responses cannot hide as lower load).

    uv run python scripts/load_test.py --rps 200 --seconds 30 --scenario cold
    scenarios: cold  = unique room dimensions every request (every request is a cache miss)
               mixed = realistic mix: repeated popular estimates (cache hits), unique estimates,
                       recommendations and product-card calculations
Prints p50/p95/p99 latency, achieved RPS and error counts; exit code 1 on any 5xx / failure.
"""
import argparse
import asyncio
import json
import multiprocessing
import random
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOM_TYPES = ["living", "bedroom", "kitchen", "bathroom", "kids", "hallway"]
CLASSES = ["cosmetic", "major", "designer"]


def room_body(rnd: random.Random, unique: bool) -> dict:  # type: ignore[type-arg]
    if unique:
        length, width = round(rnd.uniform(2, 9), 3), round(rnd.uniform(2, 7), 3)
    else:
        length, width = rnd.choice([3, 4, 5, 6]), rnd.choice([3, 4])
    return {"room": {"length_m": str(length), "width_m": str(width), "height_m": "2.7"},
            "room_type": rnd.choice(ROOM_TYPES), "renovation_class": rnd.choice(CLASSES)}


async def fetch_skus(client: httpx.AsyncClient) -> list[str]:
    skus: list[str] = []
    for calc in ("paint", "laminate", "tile", "wallpaper", "putty"):
        r = await client.post("/v1/recommend", json={"room_type": "living", "calc": calc,
                                                      "top_k": 5})
        skus += [i["sku"] for i in r.json().get("items", [])]
    return skus


def make_request(rnd: random.Random, scenario: str, skus: list[str]) -> tuple[str, str, dict]:  # type: ignore[type-arg]
    if scenario == "cold":
        return "POST", "/v1/calc/room", room_body(rnd, unique=True)
    x = rnd.random()
    if x < 0.45:
        return "POST", "/v1/calc/room", room_body(rnd, unique=False)         # popular -> hits
    if x < 0.65:
        return "POST", "/v1/calc/room", room_body(rnd, unique=True)          # unique -> misses
    if x < 0.80:
        return "POST", "/v1/calc/property", {
            "property_type": rnd.choice(["apartment", "studio", "house"]),
            "total_area_m2": str(rnd.choice([35, 45, 60, 75, 90, 120])),
            "renovation_class": rnd.choice(CLASSES)}
    if x < 0.92:
        return "POST", "/v1/recommend", {"room_type": rnd.choice(ROOM_TYPES),
                                         "calc": rnd.choice(["paint", "tile", "laminate",
                                                             "wallpaper", "drywall"]),
                                         "top_k": 5}
    sku = rnd.choice(skus) if skus else "x"
    return "POST", f"/v1/products/{sku}/quantity", {
        "room": {"length_m": str(round(rnd.uniform(2, 7), 2)),
                 "width_m": str(round(rnd.uniform(2, 6), 2)), "height_m": "2.7"},
        "room_type": rnd.choice(ROOM_TYPES)}


async def _worker(base: str, rps: int, seconds: int, scenario: str, seed: int):  # type: ignore[no-untyped-def]
    rnd = random.Random(seed)
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=200)
    lat: list[float] = []
    codes: Counter[int | str] = Counter()
    async with httpx.AsyncClient(base_url=base, timeout=15, limits=limits) as client:
        skus = await fetch_skus(client)
        await client.get("/health")

        async def one(method: str, path: str, body: dict) -> None:  # type: ignore[type-arg]
            t = time.perf_counter()
            try:
                r = await client.request(method, path, json=body)
                codes[r.status_code] += 1
            except Exception as e:
                codes[type(e).__name__] += 1
            lat.append((time.perf_counter() - t) * 1000)

        tasks: list[asyncio.Task[None]] = []
        start = time.perf_counter()
        for i in range(rps * seconds):
            method, path, body = make_request(rnd, scenario, skus)
            tasks.append(asyncio.create_task(one(method, path, body)))
            delay = start + (i + 1) / rps - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
        await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start
    return lat, dict(codes), elapsed


def worker_entry(args: tuple[str, int, int, str, int]):  # type: ignore[no-untyped-def]
    return asyncio.run(_worker(*args))


def run(base: str, rps: int, seconds: int, scenario: str, seed: int, procs: int,
        out: str | None = None, label: str | None = None) -> int:
    """`procs` client processes, each generating rps/procs: one Python process cannot drive
    200 req/s of httpx without becoming the bottleneck itself."""
    per = max(1, rps // procs)
    jobs = [(base, per, seconds, scenario, seed + i) for i in range(procs)]
    with multiprocessing.Pool(procs) as pool:
        results = pool.map(worker_entry, jobs)
    lat = sorted(x for r in results for x in r[0])
    codes: Counter[int | str] = Counter()
    for r in results:
        codes.update(r[1])
    elapsed = max(r[2] for r in results)
    pct = lambda p: lat[min(len(lat) - 1, int(len(lat) * p))]  # noqa: E731
    bad = sum(v for k, v in codes.items() if not (isinstance(k, int) and k < 500 and k != 429))
    print(f"scenario={scenario} target={per * procs} rps x {seconds}s ({procs} client procs) -> "
          f"{len(lat)} requests, achieved {len(lat) / elapsed:.0f} rps")
    print(f"latency ms: p50={pct(0.50):.1f} p95={pct(0.95):.1f} p99={pct(0.99):.1f} "
          f"max={lat[-1]:.1f}")
    print(f"status codes: {dict(codes)}")
    if out:
        ok = sum(v for k, v in codes.items() if isinstance(k, int) and 200 <= k < 300)
        server_errors = sum(v for k, v in codes.items() if isinstance(k, int) and k >= 500)
        result = {
            "label": label or f"{scenario} {per * procs} rps", "scenario": scenario,
            "rps": per * procs, "seconds": seconds, "requests": len(lat), "ok": ok,
            "errors_5xx": server_errors, "other_failures": len(lat) - ok - server_errors,
            "p50": round(pct(0.50), 1), "p95": round(pct(0.95), 1), "p99": round(pct(0.99), 1),
            "max": round(lat[-1], 1),
        }
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--rps", type=int, default=200)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--scenario", choices=["cold", "mixed"], default="mixed")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--procs", type=int, default=4, help="client processes")
    ap.add_argument("--out", help="write the result as JSON (for scripts/pitch_metrics.py)")
    ap.add_argument("--label", help="name of this run in the pitch table")
    a = ap.parse_args()
    raise SystemExit(run(a.base, a.rps, a.seconds, a.scenario, a.seed, a.procs, a.out, a.label))
