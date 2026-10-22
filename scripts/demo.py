"""End-to-end demo on the official dataset: start the service, run the scenario, stop the service.

    make demo          (needs data/raw/products_final.json; a few minutes: loads 88 790 products)

Steps: uvicorn with CATALOG_PATH -> wait for /ready -> scripts/e2e_dump.py (smoke checks,
room estimate, upload job, new product) -> stop. Output: out/e2e_dump.json.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/raw/products_final.json"
PORT = int(os.environ.get("DEMO_PORT", "8765"))


def main() -> int:
    if not DATA.exists():
        print(f"Нет набора данных: положите файл организаторов в {DATA.relative_to(ROOT)}")
        print("Without the dataset the demo cannot run; see README (Data).")
        return 2
    env = {**os.environ, "CATALOG_PATH": str(DATA), "PYTHONIOENCODING": "utf-8"}
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "maxicalc.api.main:app",
                               "--port", str(PORT)], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        t0 = time.time()
        while time.time() - t0 < 900:
            try:
                r = httpx.get(f"http://127.0.0.1:{PORT}/ready", timeout=2, trust_env=False)
                if r.json().get("catalog_size"):
                    break
            except Exception:
                pass
            if server.poll() is not None:
                print("сервис завершился при старте")
                return 1
            time.sleep(3)
        print(f"сервис готов за {time.time() - t0:.0f} с")
        return subprocess.call([sys.executable, "scripts/e2e_dump.py", "--base",
                                f"http://127.0.0.1:{PORT}"], cwd=ROOT, env=env)
    finally:
        server.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
