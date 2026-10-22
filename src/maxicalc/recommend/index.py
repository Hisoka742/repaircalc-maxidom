"""Read-only catalog index: entries by calc template and memoised recommendations.

The catalog is static between re-matches, so recommend() results per (room, calc, tier) can be
cached for the lifetime of the index. This keeps estimate latency independent of catalog size.
"""
from collections import defaultdict

from maxicalc.recommend.companions import pick_companions
from maxicalc.recommend.select import CatalogEntry, Constraints, RecommendResult, recommend

TOP_K = 10
MAX_QUERY_MEMO = 4096


class CatalogIndex:
    def __init__(self, entries: list[CatalogEntry], margin_weight: float = 0.0,
                 completeness_weight: float = 0.0, rating_weight: float | None = None) -> None:
        self.entries = entries
        self.margin_weight = margin_weight
        self.completeness_weight = completeness_weight
        self.rating_weight = rating_weight
        self._by_calc: dict[str, list[CatalogEntry]] = defaultdict(list)
        self._by_sku: dict[str, CatalogEntry] = {}
        self._by_id: dict[str, CatalogEntry] = {}
        for e in entries:
            self._by_calc[e.calc].append(e)
            self._by_sku[e.product.sku] = e
            if e.product.product_id:
                self._by_id[e.product.product_id] = e
        self._ppe = [e for e in entries if e.role == "ppe"]
        self._accessories: dict[str, list[CatalogEntry]] = defaultdict(list)
        for e in entries:
            if e.role == "accessory":
                self._accessories[e.calc].append(e)
        self._memo: dict[tuple[str, str, str | None, tuple[str, ...]], RecommendResult] = {}
        self._query_memo: dict[tuple[object, ...], RecommendResult] = {}

    def __len__(self) -> int:
        return len(self.entries)

    def of_calc(self, calc: str) -> list[CatalogEntry]:
        return self._by_calc.get(calc, [])

    def get(self, key: str) -> CatalogEntry | None:
        """By article (`sku`), falling back to the stand's product `id`."""
        return self._by_sku.get(key) or self._by_id.get(key)

    def recommend(
        self, room: str, calc: str, tier: str | None, overlays: tuple[str, ...] = ()
    ) -> RecommendResult:
        key = (room, calc, tier, overlays)
        hit = self._memo.get(key)
        if hit is None:
            hit = recommend(self.of_calc(calc), room, calc=calc,
                            constraints=Constraints(tier=tier), top_k=TOP_K, overlays=overlays,
                            margin_weight=self.margin_weight,
                            completeness_weight=self.completeness_weight,
                            rating_weight=self.rating_weight)
            hit.companions = pick_companions(self._accessories.get(calc, []), self._ppe)
            self._memo[key] = hit
        return hit

    def query(
        self, room: str, work: str | None, calc: str | None,
        constraints: Constraints, top_k: int, overlays: tuple[str, ...] = (),
    ) -> RecommendResult:
        """Memoised general query (the catalog is static until the next re-match)."""
        key = (room, work, calc, constraints, top_k, overlays)
        hit = self._query_memo.get(key)
        if hit is None:
            pool = self.of_calc(calc) if calc else self.entries
            hit = recommend(pool, room, work=work, calc=calc, constraints=constraints,
                            top_k=top_k, overlays=overlays, margin_weight=self.margin_weight,
                            completeness_weight=self.completeness_weight,
                            rating_weight=self.rating_weight)
            if calc:
                hit.companions = pick_companions(self._accessories.get(calc, []), self._ppe)
            if len(self._query_memo) >= MAX_QUERY_MEMO:
                self._query_memo.clear()
            self._query_memo[key] = hit
        return hit
