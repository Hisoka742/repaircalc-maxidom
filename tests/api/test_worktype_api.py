"""Full cycle: upload a feed -> job -> work types with confidence -> review -> human override."""
import gzip
import time
from pathlib import Path

from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.config import Settings

FEED = Path(__file__).resolve().parents[1] / "fixtures" / "maxidom_feed_sample.xml"


def make(tmp_path: Path) -> TestClient:
    settings = Settings(catalog_path=None, model_path=None, redis_url=None, rate_limit_per_min=0,
                        worktype_model_path=None,
                        worktype_overrides_path=str(tmp_path / "wt_overrides.json"))
    return TestClient(create_app(AppState([], settings), settings))


def wait(client: TestClient, job: str) -> dict:  # type: ignore[type-arg]
    for _ in range(100):
        body = client.get(f"/api/v1/catalog/upload/{job}").json()
        if body["stage"] in ("done", "failed"):
            return body  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_upload_yml_job_returns_work_types_with_confidence(tmp_path: Path) -> None:
    c = make(tmp_path)
    r = c.post("/api/v1/catalog/upload",
               files={"file": ("feed.xml.gz", gzip.compress(FEED.read_bytes()))})
    assert r.status_code == 202
    body = wait(c, r.json()["job_id"])
    assert body["stage"] == "done" and body["total"] == 3
    assert body["summary"]["products"] == 3 and body["summary"]["no_work_type"] >= 2
    paint = next(i for i in body["results"] if i["sku"] == "100")
    works = {w["work"]: w for w in paint["work_types"]}
    assert works["wall_painting"]["role"] == "material"
    assert works["wall_painting"]["source"] == "rule"
    assert 0 < works["wall_painting"]["confidence"] <= 1
    assert body["seconds"]["match"] >= 0 and body["ms_per_1k_products"] is not None


def test_upload_rejects_unknown_format_and_reports_a_broken_file(tmp_path: Path) -> None:
    c = make(tmp_path)
    assert c.post("/api/v1/catalog/upload", files={"file": ("x.exe", b"MZ")}).status_code == 415
    r = c.post("/api/v1/catalog/upload", files={"file": ("bad.json", b"{not json")})
    assert wait(c, r.json()["job_id"])["stage"] == "failed"
    assert c.get("/api/v1/catalog/upload/nope").status_code == 404


def test_new_product_is_classified_in_milliseconds(tmp_path: Path) -> None:
    c = make(tmp_path)
    r = c.post("/api/v1/catalog/work-types/classify", json={
        "name": "грунтовка глубокого проникновения 5л",
        "category": "Краска и малярный инструмент > Грунты, пропитки, олифы > Грунтовка"})
    assert r.status_code == 200
    works = {w["work"]: w["role"] for w in r.json()["item"]["work_types"]}
    assert works["priming"] == "material" and works["tile_laying"] == "consumable"
    assert r.json()["milliseconds"] < 200


def test_human_override_wins_and_is_persisted(tmp_path: Path) -> None:
    c = make(tmp_path)
    j = c.post("/api/v1/catalog/upload",
               files={"file": ("feed.xml", FEED.read_bytes())}).json()["job_id"]
    wait(c, j)
    r = c.post("/api/v1/catalog/work-review/100",
               json={"work_types": ["wall_painting"], "reviewer": "ivan"})
    assert r.status_code == 200
    item = next(i for i in c.get(f"/api/v1/catalog/upload/{j}").json()["results"]
                if i["sku"] == "100")
    assert [w["work"] for w in item["work_types"]] == ["wall_painting"]
    assert item["verified"] and item["work_types"][0]["source"] == "human"
    assert (tmp_path / "wt_overrides.json").exists()
    bad = c.post("/api/v1/catalog/work-review/100", json={"work_types": ["nope"], "reviewer": "x"})
    assert bad.status_code == 422
    assert len(c.get("/api/v1/catalog/work-types").json()) == 42
