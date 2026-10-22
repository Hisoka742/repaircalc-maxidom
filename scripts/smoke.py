"""Smoke-test a running API: every endpoint, one pass, with reasons for any failure.

    uv run python scripts/smoke.py [--base http://127.0.0.1:8000]
Exit code 0 only if every check passed.
"""
import argparse
import sys

import httpx

from maxicalc.smoke import run_smoke


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    try:
        with httpx.Client(base_url=a.base, timeout=30) as c:
            results = run_smoke(c)
    except httpx.ConnectError:
        print(f"ОШИБКА: сервис не отвечает на {a.base}. Запущен ли uvicorn?")
        return 2
    for r in results:
        print(f"{'OK  ' if r.ok else 'FAIL'} {r.name:18s} {r.detail}")
    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} проверок пройдено")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
