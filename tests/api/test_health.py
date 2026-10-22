from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.config import Settings


def make() -> TestClient:
    # isolated from .env / environment: an empty catalog, in-memory cache
    settings = Settings(catalog_path=None, model_path=None, redis_url=None, rate_limit_per_min=0)
    return TestClient(create_app(AppState([], settings), settings))


def test_health_ok() -> None:
    body = make().get("/health").json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["catalog_size"] == 0


def test_openapi_is_versioned_and_served() -> None:
    r = make().get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["openapi"].startswith("3.1")


def test_importing_main_has_no_side_effects(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The module-level `app` must not read a catalog at import time."""
    import importlib

    import maxicalc.api.main as main

    monkeypatch.setenv("CATALOG_PATH", "does/not/exist.csv")
    importlib.reload(main)           # would raise FileNotFoundError if it loaded eagerly
    assert main.app._app is None
