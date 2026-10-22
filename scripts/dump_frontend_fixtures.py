"""Record real API responses as frontend demo fixtures (offline rehearsal, API stopped).

    uv run python scripts/dump_frontend_fixtures.py [--catalog data/demo_catalog.csv]
Writes frontend/src/data/fixtures.json. Every value is genuine engine output on the SYNTHETIC
demo catalog; nothing is hand-written.
"""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.config import Settings

PROPERTIES = [("studio", 30), ("apartment", 60), ("house", 120)]
CLASSES = ["cosmetic", "major", "designer"]
ROOMS = ["living", "bedroom", "kitchen", "bathroom", "kids", "hallway", "balcony"]
CALCS = ["paint", "primer", "putty", "wallpaper", "laminate", "tile", "tile_adhesive", "grout",
         "drywall", "electrical", "waterproofing", "self_leveling", "underlay", "skirting"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="data/demo_catalog.csv")
    ap.add_argument("--model", default="data/demo_model.joblib")
    ap.add_argument("--out", default="frontend/src/data/fixtures.json")
    a = ap.parse_args()

    settings = Settings(catalog_path=a.catalog, model_path=a.model, rate_limit_per_min=0,
                        log_json=False)
    state = AppState.from_settings(settings)
    client = TestClient(create_app(state, settings))
    health = client.get("/health").json()

    prop: dict[str, object] = {}
    for ptype, area in PROPERTIES:
        for klass in CLASSES:
            r = client.post("/v1/calc/property", json={
                "property_type": ptype, "total_area_m2": str(area), "renovation_class": klass})
            r.raise_for_status()
            prop[f"{ptype}|{area}|{klass}"] = r.json()

    rec: dict[str, object] = {}
    for room in ROOMS:
        for calc in CALCS:
            r = client.post("/v1/recommend", json={"room_type": room, "calc": calc, "top_k": 5})
            r.raise_for_status()
            body = r.json()
            body["excluded"] = body["excluded"][:12]   # keep the file small; total is kept
            rec[f"{room}|{calc}"] = body

    out = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "catalog": f"синтетический демо-каталог, {health['catalog_size']} товаров",
        "catalog_version": health["catalog_version"],
        "presets": [{"property_type": p, "area": s} for p, s in PROPERTIES],
        "property": prop,
        "recommend": rec,
    }
    path = Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {path} ({path.stat().st_size // 1024} KB): {len(prop)} property estimates, "
          f"{len(rec)} recommendation sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
