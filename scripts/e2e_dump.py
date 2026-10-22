"""End-to-end demo against a RUNNING service that serves the official dump.

    CATALOG_PATH=data/raw/products_final.json uvicorn maxicalc.api.main:app --port 8000
    python scripts/e2e_dump.py [--base http://127.0.0.1:8000] [--sample 300]

Steps (each timed, results printed and written to out/e2e_dump.json):
  1. smoke checks of every endpoint (maxicalc.smoke)
  2. room estimate -> basket with sources in `explain`
  3. full cycle: POST /api/v1/catalog/upload (a sample cut from the dump, JSON) -> async job ->
     work types with confidence -> review queue
  4. new product: POST /api/v1/catalog/work-types/classify (name + category, milliseconds)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx
import ijson

from maxicalc.smoke import run_smoke

ROOT = Path(__file__).resolve().parents[1]


def sample_dump(n: int, step: int = 290) -> bytes:
    """Every `step`-th product of the dump, same JSON layout ({"products": [...]})."""
    items = []
    with (ROOT / "data/raw/products_final.json").open("rb") as f:
        for i, it in enumerate(ijson.items(f, "products.item", use_float=True)):
            if i % step == 0:
                items.append(it)
            if len(items) >= n:
                break
    return json.dumps({"products": items}, ensure_ascii=False, default=float).encode("utf-8")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--sample", type=int, default=300)
    a = ap.parse_args()
    out: dict[str, object] = {}
    with httpx.Client(base_url=a.base, timeout=120) as c:
        t = time.perf_counter()
        smoke = run_smoke(c)
        out["smoke"] = {"passed": sum(r.ok for r in smoke), "total": len(smoke),
                        "failed": [f"{r.name}: {r.detail}" for r in smoke if not r.ok],
                        "seconds": round(time.perf_counter() - t, 2)}
        print(f"1. smoke: {out['smoke']}")

        room = {"room": {"length_m": "4", "width_m": "3", "height_m": "2.7"},
                "room_type": "living", "renovation_class": "cosmetic"}
        t = time.perf_counter()
        r = c.post("/api/v1/calc/room", json=room).json()
        ms = (time.perf_counter() - t) * 1000
        lines = r["basket"]["lines"]
        out["room"] = {"lines": len(lines), "total_rub": r["basket"]["materials_total"],
                       "warnings": len(r["warnings"]), "ms": round(ms),
                       "first": [(ln["name"][:60], ln["qty_packs"], ln["unit"])
                                 for ln in lines[:4]]}
        print(f"2. room estimate: {out['room']}")

        body = sample_dump(a.sample)
        t = time.perf_counter()
        job = c.post("/api/v1/catalog/upload",
                     files={"file": ("sample.json", body)}).json()["job_id"]
        while True:
            st = c.get(f"/api/v1/catalog/upload/{job}").json()
            if st["stage"] in ("done", "failed"):
                break
            time.sleep(0.2)
        review = c.get(f"/api/v1/catalog/upload/{job}/review").json()
        res = st.get("results", [])
        out["upload"] = {
            "stage": st["stage"], "products": st.get("total"), "seconds": round(
                time.perf_counter() - t, 2), "ms_per_1k_products": st.get("ms_per_1k_products"),
            "summary": st.get("summary"),
            "review_queue": len(review if isinstance(review, list) else review.get("items", [])),
            "example": next(({"name": i["name"][:60],
                              "works": [(w["work"], w["role"], w["confidence"])
                                        for w in i["work_types"]][:4]}
                             for i in res if i["work_types"]), None)}
        print(f"3. upload job: {json.dumps(out['upload'], ensure_ascii=False)}")

        new = {"name": "саморез по гипсокартону 3,5x35 мм фосфатированный 200 шт",
               "category": "Строительные материалы > Метизы, крепежные изделия > Саморезы, шурупы"}
        cl = c.post("/api/v1/catalog/work-types/classify", json=new).json()
        out["new_product"] = {"ms": cl["milliseconds"],
                              "works": [(w["work"], w["role"], w["confidence"], w["source"])
                                        for w in cl["item"]["work_types"]]}
        print(f"4. new product: {out['new_product']}")
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out/e2e_dump.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    return 0 if out["smoke"]["failed"] == [] else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
