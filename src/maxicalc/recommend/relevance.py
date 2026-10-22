"""Embedding relevance of a product to a recommendation query (room + need), 0..1.

The score is the cosine between the embedded query text and the product text (name, category,
characteristics), clamped at 0. It is one more term in `recommend` next to the room rules, tier,
popularity and margin, with its own weight (0 = off). Hard rules are untouched: a product that
breaks one is excluded before scoring, whatever its relevance.
"""
import numpy as np

from maxicalc.ml.embed import Embedder, product_text
from maxicalc.recommend.select import CatalogEntry

CALC_RU = {
    "paint": "краска для стен", "wallpaper": "обои", "tile": "плитка керамическая",
    "laminate": "ламинат", "drywall": "гипсокартон", "electrical": "розетки выключатели",
    "tile_adhesive": "клей для плитки", "grout": "затирка для швов", "primer": "грунтовка",
    "putty": "шпатлёвка", "waterproofing": "гидроизоляция", "skirting": "плинтус",
}
ROOM_RU = {
    "bathroom": "ванная комната влажное помещение", "kitchen": "кухня", "kids": "детская",
    "balcony": "балкон лоджия", "hallway": "прихожая коридор", "living": "гостиная",
    "bedroom": "спальня", "toilet": "санузел",
}


def query_text(room: str, calc: str) -> str:
    return f"{CALC_RU.get(calc, calc)} для {ROOM_RU.get(room, room)}"


class RelevanceScorer:
    """Encodes each product once, then scores any (room, calc) query against it."""

    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self._vec: dict[str, np.ndarray] = {}

    def _ensure(self, entries: list[CatalogEntry]) -> None:
        todo = [e for e in entries if e.product.sku not in self._vec]
        if todo:
            m = self.embedder.encode([product_text(e.product) for e in todo])
            for e, v in zip(todo, m, strict=True):
                self._vec[e.product.sku] = v

    def scores(self, entries: list[CatalogEntry], room: str, calc: str) -> dict[str, float]:
        self._ensure(entries)
        q = self.embedder.encode([query_text(room, calc)])[0]
        return {e.product.sku: max(0.0, float(self._vec[e.product.sku] @ q)) for e in entries}
