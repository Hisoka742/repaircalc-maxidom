from decimal import Decimal as D

from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.catalog.schema import Product
from maxicalc.config import Settings
from maxicalc.recommend.select import CatalogEntry
from maxicalc.smoke import run_smoke


def entry(sku: str, calc: str, attrs: dict[str, object], props: set[str] | None = None):  # type: ignore[no-untyped-def]
    return CatalogEntry(
        Product(sku=sku, name=f"Товар {sku}", price=D("100"), category_path=["Краски"]),
        work=set(), rooms={"any"}, props=props or set(), calc=calc, status="verified",
        attrs={k: (v if isinstance(v, int) else D(str(v))) for k, v in attrs.items()})


def client(entries: list[CatalogEntry]) -> TestClient:
    settings = Settings(rate_limit_per_min=0)
    return TestClient(create_app(AppState(entries, settings), settings))


def test_smoke_passes_on_a_working_service() -> None:
    entries = [entry("P1", "paint", {"spread_m2_per_l": 10, "pack_volume_l": "2.5"}, {"washable"}),
               entry("W1", "wallpaper", {"roll_width_m": "1.06", "roll_length_m": "10.05"})]
    results = run_smoke(client(entries))
    names = {r.name for r in results}
    assert {"health", "recommend", "calc/room", "calc/property", "product quantity",
            "catalog/match", "review-queue", "export xlsx", "metrics"} <= names
    failed = [r for r in results if not r.ok]
    assert not failed, [(r.name, r.detail) for r in failed]


def test_smoke_reports_each_failure_instead_of_crashing() -> None:
    # an empty catalog is the classic day-of failure (wrong CATALOG_PATH): say so, and still
    # run every check so the operator sees the whole picture in one pass
    results = run_smoke(client([]))
    by = {r.name: r for r in results}
    assert not by["health"].ok and "каталог пуст" in by["health"].detail
    assert not by["recommend"].ok and "не найден" in by["recommend"].detail
    assert by["metrics"].ok and by["catalog/match"].ok       # independent checks still pass
    assert len(results) == 9
