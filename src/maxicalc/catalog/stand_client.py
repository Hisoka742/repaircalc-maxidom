"""Client for the organisers' stand API (`/api/catalog/*`, Bagisto-style).

Reads the category tree, walks every page of every category's products (`meta.last_page`, not the
first page only), fetches the full card (`/api/catalog/products/{id}`) for descriptions and
characteristics, de-duplicates by `id`, and writes a JSONL dump that `load_catalog` reads.

Written against the field list in the case brief; it has NOT been run against the real stand
(no URL or token was available when it was written).
"""
import hashlib
import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


class StandError(RuntimeError):
    pass


@dataclass
class FetchStats:
    categories: int = 0
    pages: int = 0
    products: int = 0
    cards: int = 0
    card_errors: int = 0
    retries: int = 0
    cache_hits: int = 0
    seconds: float = 0.0
    problems: list[str] = field(default_factory=list)


class StandClient:
    def __init__(
        self, base_url: str = "", token: str | None = None, locale: str = "ru",
        client: httpx.Client | None = None, retries: int = 3, backoff_s: float = 0.5,
        timeout: float = 30.0, cache_dir: str | Path | None = None, min_interval_s: float = 0.0,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = client or httpx.Client(base_url=base_url.rstrip("/"), headers=headers,
                                            timeout=timeout)
        self.locale = locale
        self.retries = retries
        self.backoff_s = backoff_s
        self.stats = FetchStats()
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.min_interval_s = min_interval_s
        self._last = 0.0
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_file(self, path: str, params: dict[str, Any]) -> Path | None:
        if self.cache_dir is None:
            return None
        key = json.dumps([path, sorted(params.items())], ensure_ascii=False, default=str)
        return self.cache_dir / (hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()
                                 + ".json")

    def _throttle(self) -> None:
        if self.min_interval_s > 0:
            wait = self._last + self.min_interval_s - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            self._last = time.perf_counter()

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        cached = self._cache_file(path, clean)
        if cached is not None and cached.exists():
            self.stats.cache_hits += 1
            body = json.loads(cached.read_text(encoding="utf-8"))
            if isinstance(body, dict):
                return body
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self._throttle()
                r = self._http.get(path, params=clean)
                if r.status_code in (429, 502, 503, 504):
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                r.raise_for_status()
                body = r.json()
                if not isinstance(body, dict):
                    raise StandError(f"{path}: ожидался JSON-объект")
                if cached is not None:
                    cached.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
                return body
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                last = e
                if attempt < self.retries:
                    self.stats.retries += 1
                    time.sleep(self.backoff_s * (2 ** attempt))
        raise StandError(f"{path}: {last}")

    # ---- endpoints ----
    def category_tree(self, category_id: int = 1, depth_level: int = 20) -> list[dict[str, Any]]:
        body = self._get("/api/catalog/categories/tree", category_id=category_id,
                         depth_level=depth_level, locale=self.locale)
        return list(body.get("data") or [])

    def categories(self, parent_id: int = 1, depth_level: int = 2) -> list[dict[str, Any]]:
        """Flat category details (description, status, counters) under `parent_id`."""
        body = self._get("/api/catalog/categories", parent_id=parent_id,
                         depth_level=depth_level, locale=self.locale)
        return list(body.get("data") or [])

    def regions(self) -> list[dict[str, Any]]:
        return list(self._get("/api/regions").get("data") or [])

    def default_region_id(self) -> str | None:
        """The region flagged `is_default` (the case leaves the real choice to the organisers)."""
        for r in self.regions():
            if r.get("is_default") and r.get("status", True):
                return str(r.get("id"))
        return None

    def products_page(
        self, category_id: int, page: int, per_page: int = 100
    ) -> tuple[list[dict[str, Any]], int]:
        body = self._get("/api/catalog/products", category_id=category_id,
                         include_subsections=0, include_categories_tree=1, per_page=per_page,
                         page=page, locale=self.locale)
        meta = body.get("meta") or {}
        return list(body.get("items") or []), int(meta.get("last_page") or 1)

    def card(self, product_id: int | str) -> dict[str, Any]:
        return dict(self._get(f"/api/catalog/products/{product_id}", locale=self.locale)
                    .get("data") or {})

    # ---- whole catalog ----
    @staticmethod
    def walk(tree: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for node in tree:
            yield node
            yield from StandClient.walk(node.get("children") or [])

    def fetch_all(
        self, root_category: int = 1, per_page: int = 100, with_cards: bool = True,
        max_products: int | None = None,
    ) -> list[dict[str, Any]]:
        t0 = time.perf_counter()
        tree = self.category_tree(root_category)
        out: dict[str, dict[str, Any]] = {}
        for node in self.walk(tree):
            if node.get("status") is False or not node.get("product_count"):
                continue
            self.stats.categories += 1
            page, last = 1, 1
            while page <= last:
                try:
                    items, last = self.products_page(int(node["id"]), page, per_page)
                except StandError as e:
                    self.stats.problems.append(f"категория {node.get('id')} стр. {page}: {e}")
                    break
                self.stats.pages += 1
                for it in items:
                    out[str(it.get("id"))] = it
                page += 1
            if max_products and len(out) >= max_products:
                break
        self.stats.products = len(out)
        if with_cards:
            for pid, it in list(out.items()):
                try:
                    full = self.card(pid)
                except StandError as e:
                    self.stats.card_errors += 1
                    self.stats.problems.append(f"карточка {pid}: {e}")
                    continue
                self.stats.cards += 1
                # the list item has prices/stocks/ratings; the card adds description and
                # characteristics. Keep both, the card wins on shared keys.
                out[pid] = {**it, **full}
        self.stats.seconds = round(time.perf_counter() - t0, 2)
        return list(out.values())

    @staticmethod
    def dump(items: list[dict[str, Any]], path: str | Path) -> int:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        return len(items)
