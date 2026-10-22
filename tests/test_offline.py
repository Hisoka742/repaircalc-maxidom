"""Offline rehearsal ("Wi-Fi off"): the whole system must work with no outside network.

Any attempt to resolve a non-local host or connect to a non-local address fails the test, so a
hidden dependency on the internet (an LLM endpoint, a model download, telemetry) cannot slip in.
"""
import csv
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maxicalc.api.main import create_app
from maxicalc.api.state import AppState
from maxicalc.config import Settings
from maxicalc.dayof import run_dayof
from maxicalc.ml.classify import MatchModel, weak_labels
from maxicalc.ml.synth import generate, split_by_group

LOCAL = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


class NetworkAttempt(AssertionError):
    pass


@pytest.fixture()
def no_internet(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo

    def guarded_connect(self: socket.socket, address: object) -> None:
        host = address[0] if isinstance(address, tuple) else address
        if self.family != getattr(socket, "AF_UNIX", -1) and str(host) not in LOCAL:
            attempts.append(f"connect {host}")
            raise NetworkAttempt(f"outside network access: connect to {host}")
        real_connect(self, address)  # type: ignore[arg-type]

    def guarded_getaddrinfo(host, *a, **kw):  # type: ignore[no-untyped-def]
        if host is not None and str(host) not in LOCAL:
            attempts.append(f"dns {host}")
            raise NetworkAttempt(f"outside network access: DNS lookup of {host}")
        return real_getaddrinfo(host, *a, **kw)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    return attempts


def test_the_guard_itself_works(no_internet: list[str]) -> None:
    with pytest.raises(NetworkAttempt):
        socket.getaddrinfo("example.com", 80)
    with pytest.raises(NetworkAttempt):
        socket.create_connection(("93.184.216.34", 80), timeout=1)
    # create_connection resolves first, so the second attempt is blocked at the lookup step
    assert len(no_internet) == 2 and no_internet[0] == "dns example.com"
    assert "93.184.216.34" in no_internet[1]


def write_catalog(path: Path) -> list:  # type: ignore[type-arg]
    items = generate(600, seed=9)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["sku", "name", "category", "brand", "price", "description"])
        for it in items:
            p = it.product
            desc = "Расход 10 м2/л" if it.gold.calc == "paint" else ""
            w.writerow([p.sku, p.name, " > ".join(p.category_path), p.brand or "", 700, desc])
    return items


def test_whole_system_works_offline(tmp_path: Path, no_internet: list[str]) -> None:
    cat = tmp_path / "catalog.csv"
    items = write_catalog(cat)
    train, dev, _ = split_by_group(items, seed=9)
    prods, labels = weak_labels([i.product for i in train])
    model = MatchModel().fit(prods, labels, [i.product for i in dev], [i.gold for i in dev])
    model_path = tmp_path / "model.joblib"
    model.save(model_path)

    settings = Settings(catalog_path=str(cat), model_path=str(model_path), redis_url=None,
                        rate_limit_per_min=0, log_json=True)
    client = TestClient(create_app(AppState.from_settings(settings), settings))

    assert client.get("/health").json()["catalog_size"] == 600
    room = {"room": {"length_m": "4", "width_m": "3"}, "room_type": "living",
            "renovation_class": "cosmetic"}
    est = client.post("/v1/calc/room", json=room)
    assert est.status_code == 200
    assert client.post("/v1/calc/property", json={
        "property_type": "apartment", "total_area_m2": "60",
        "renovation_class": "major"}).status_code == 200
    assert client.post("/v1/recommend", json={"room_type": "kitchen", "calc": "paint"}
                       ).status_code == 200
    assert client.post("/v1/catalog/match", json={"products": [
        {"sku": "z", "name": "Обои флизелиновые 1,06х10,05 м", "category_path": ["Обои"]}]}
    ).json()["status"] == "done"
    assert client.post(f"/v1/estimate/{est.json()['estimate_id']}/export?format=xlsx"
                       ).status_code == 200
    assert client.get("/metrics").status_code == 200

    res = run_dayof(cat, tmp_path / "dayof", sample_size=20)       # the day-of pipeline too
    assert res.loaded == 600
    assert no_internet == [], f"unexpected network access: {no_internet}"
