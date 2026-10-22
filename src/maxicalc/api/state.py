"""Application state: the precomputed catalog view, caches, review queue and background jobs.

Matching is done off the request path (at load / re-match), so calc endpoints only read
precomputed labels. The catalog is swapped atomically (new CatalogIndex object).
"""
import hashlib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

import structlog

from maxicalc.api.cache import Cache, make_cache
from maxicalc.api.schemas import MatchItemOut
from maxicalc.api.worktype_service import WorkTypeService
from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.schema import Product
from maxicalc.config import Settings, llm_url_is_private
from maxicalc.ml.classify import MatchModel
from maxicalc.ml.llm_client import LLMClient
from maxicalc.ml.match import Matcher, MatchResult
from maxicalc.ml.review import ReviewQueue
from maxicalc.ml.synth import Labels
from maxicalc.recommend.build import to_entries
from maxicalc.recommend.index import CatalogIndex
from maxicalc.recommend.select import CatalogEntry

log = structlog.get_logger()
MATCH_CHUNK = 500


def catalog_version(entries: list[CatalogEntry]) -> str:
    h = hashlib.sha1(usedforsecurity=False)
    for e in sorted(entries, key=lambda x: x.product.sku):
        h.update(repr((e.product.sku, str(e.product.price), e.calc, e.status,
                       sorted(e.props), sorted(e.rooms), sorted(e.work),
                       sorted((k, str(v)) for k, v in e.attrs.items()))).encode())
    return h.hexdigest()[:12]


@dataclass
class JobState:
    total: int
    done: int = 0
    status: str = "running"
    results: list[MatchItemOut] | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)


class AppState:
    def __init__(
        self, entries: list[CatalogEntry], settings: Settings, cache: Cache | None = None,
        matcher: Matcher | None = None, results: list[MatchResult] | None = None,
    ) -> None:
        self.settings = settings
        self.cache = cache or make_cache(settings.redis_url, settings.cache_max_items,
                                         settings.cache_ttl_s)
        self.matcher = matcher or Matcher()
        self.model_loaded = bool(matcher and matcher.scorer)
        self.review = ReviewQueue(
            Path(settings.overrides_path) if settings.overrides_path else None)
        self._llm: LLMClient | None = None
        self.worktypes = WorkTypeService(settings.worktype_model_path,
                                         settings.worktype_overrides_path)
        self.jobs: dict[str, JobState] = {}
        self._lock = RLock()
        self._pool = ThreadPoolExecutor(max_workers=2)
        entries = self._with_overrides(entries)
        self._entries = entries
        self.index = CatalogIndex(entries, settings.margin_weight, settings.completeness_weight,
                                 settings.rating_weight)
        self.version = catalog_version(entries)
        if results:
            self.review.add(results)

    @classmethod
    def from_settings(cls, settings: Settings) -> "AppState":
        if not settings.catalog_path:
            return cls([], settings)
        t0 = time.perf_counter()
        products, report = load_catalog(settings.catalog_path)
        scorer = MatchModel.load(Path(settings.model_path)) if settings.model_path else None
        matcher = Matcher(scorer)
        results = matcher.match(products)
        entries = to_entries(products, results)
        log.info("catalog_loaded", products=len(products), skipped=report.skipped,
                 review=sum(r.status == "review" for r in results),
                 seconds=round(time.perf_counter() - t0, 2), model=bool(scorer))
        return cls(entries, settings, matcher=matcher, results=results)

    @property
    def llm(self) -> LLMClient | None:
        """Local model (Ollama) or None when disabled. Created lazily: no network at startup."""
        if not self.settings.llm_enabled:
            return None
        if not self.settings.llm_allow_remote and not llm_url_is_private(
                self.settings.llm_base_url):
            log.error("llm_url_refused", url=self.settings.llm_base_url)
            return None   # closed contour: never call a public endpoint
        if self._llm is None:
            self._llm = LLMClient(self.settings.llm_base_url, self.settings.llm_model,
                                  self.settings.llm_api_key, timeout=self.settings.llm_timeout_s,
                                  retries=1)
        return self._llm

    # ---- human bindings: always win over ML ----
    def _with_overrides(self, entries: list[CatalogEntry]) -> list[CatalogEntry]:
        fb = self.review.feedback()
        if not fb:
            return entries
        out: list[CatalogEntry] = []
        for e in entries:
            lab = fb.get(e.product.sku)
            out.append(e if lab is None else CatalogEntry(
                e.product, set(lab.work), set(lab.rooms), set(lab.props), lab.calc, "verified",
                e.attrs))
        return out

    def rematch(self) -> int:
        """Run the matcher over the catalog file again and swap the index. Human bindings are
        applied last, so a re-match never undoes a manual decision."""
        path = self.settings.catalog_path
        if not path:
            raise ValueError("Каталог не задан (CATALOG_PATH): нечего пересчитывать")
        products, _ = load_catalog(path)
        results = self.matcher.match(products)
        with self._lock:
            fresh = self._with_overrides(to_entries(products, results))
            self.review = ReviewQueue(self.review._path)  # reload feedback, drop stale queue
            self.review.add(results)
            self._entries = fresh
            self.index = CatalogIndex(fresh, self.settings.margin_weight,
                                      self.settings.completeness_weight,
                                      self.settings.rating_weight)
            self.version = catalog_version(fresh)
        return len(fresh)

    # ---- review feedback -> live catalog ----
    def apply_review(self, sku: str, labels: Labels, reviewer: str) -> None:
        with self._lock:
            old = self.index.get(sku)
            if old is None:
                raise KeyError(sku)
            self.review.override(sku, labels, reviewer)
            new = CatalogEntry(old.product, set(labels.work), set(labels.rooms),
                               set(labels.props), labels.calc, "verified", old.attrs)
            self._entries = [new if e.product.sku == sku else e for e in self._entries]
            self.index = CatalogIndex(self._entries, self.settings.margin_weight,
                                      self.settings.completeness_weight,
                                      self.settings.rating_weight)
            self.version = catalog_version(self._entries)

    # ---- background matching jobs ----
    def start_match_job(self, products: list[Product], fn) -> str:  # type: ignore[no-untyped-def]
        job_id = uuid.uuid4().hex[:12]
        self.jobs[job_id] = JobState(total=len(products))
        self._prune_jobs()
        self._pool.submit(self._run_job, job_id, products, fn)
        return job_id

    def _run_job(self, job_id: str, products: list[Product], fn) -> None:  # type: ignore[no-untyped-def]
        job = self.jobs[job_id]
        out: list[MatchItemOut] = []
        try:
            for i in range(0, len(products), MATCH_CHUNK):
                out.extend(fn(self, products[i:i + MATCH_CHUNK]))
                job.done = min(i + MATCH_CHUNK, len(products))
            job.results, job.status = out, "done"
        except Exception as e:
            log.error("match_job_failed", job_id=job_id, error=repr(e))
            job.status, job.error = "failed", "Не удалось обработать пакет товаров"

    def _prune_jobs(self, keep: int = 50) -> None:
        if len(self.jobs) > keep:
            for k in sorted(self.jobs, key=lambda j: self.jobs[j].created)[:-keep]:
                del self.jobs[k]

