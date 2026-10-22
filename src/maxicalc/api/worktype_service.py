"""Work-type matching service: upload jobs, one-product classification, human overrides.

Kept apart from AppState: it owns the matcher (rules + optional model), an upload job table and
the persistent human work-type overrides (they always win over the machine).
"""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

import joblib
import structlog

from maxicalc.catalog.adapters import load_catalog
from maxicalc.catalog.schema import Product
from maxicalc.ml.worktypes import (
    ROLES,
    WorkHit,
    WorkMatcher,
    WorkPrediction,
    work_type_ids,
    work_type_names,
)

log = structlog.get_logger()
CHUNK = 2000
MAX_JOBS = 20


@dataclass
class WorkItem:
    sku: str
    name: str
    category: str
    hits: list[WorkHit]
    review: bool
    review_reason: str
    verified: bool = False


@dataclass
class UploadJob:
    filename: str
    stage: str = "queued"           # queued | parsing | matching | done | failed
    total: int = 0
    done: int = 0
    error: str | None = None
    items: list[WorkItem] = field(default_factory=list)
    seconds: dict[str, float] = field(default_factory=dict)
    created: float = field(default_factory=time.time)
    skipped: int = 0


class WorkTypeService:
    def __init__(self, model_path: str | None, overrides_path: str | None = None) -> None:
        model = None
        if model_path and Path(model_path).exists():
            model = joblib.load(model_path)
        self.model_loaded = model is not None
        self.matcher = WorkMatcher(model)
        self.jobs: dict[str, UploadJob] = {}
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._lock = RLock()
        self._path = Path(overrides_path) if overrides_path else None
        self.overrides: dict[str, dict[str, Any]] = {}
        if self._path and self._path.exists():
            self.overrides = json.loads(self._path.read_text(encoding="utf-8"))

    # -- matching -------------------------------------------------------------------------
    def _apply_overrides(self, p: Product, pred: WorkPrediction) -> WorkItem:
        ov = self.overrides.get(p.sku)
        hits = sorted(pred.hits.values(), key=lambda h: (-h.confidence, h.work))
        if ov is not None:
            hits = [WorkHit(w, "material", 1.0, "human", f"проверил {ov['reviewer']}")
                    for w in ov["work_types"]]
            return WorkItem(p.sku, p.name, " > ".join(p.category_path), hits, False, "", True)
        return WorkItem(p.sku, p.name, " > ".join(p.category_path), hits, pred.review,
                        pred.review_reason)

    def classify(self, products: list[Product]) -> list[WorkItem]:
        preds = self.matcher.predict(products)
        return [self._apply_overrides(p, pr) for p, pr in zip(products, preds, strict=True)]

    # -- upload job -----------------------------------------------------------------------
    def start_upload(self, path: Path, filename: str) -> str:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self.jobs[job_id] = UploadJob(filename)
            for k in sorted(self.jobs, key=lambda j: self.jobs[j].created)[:-MAX_JOBS]:
                del self.jobs[k]
        self._pool.submit(self._run, job_id, path)
        return job_id

    def _run(self, job_id: str, path: Path) -> None:
        job = self.jobs[job_id]
        try:
            job.stage = "parsing"
            t0 = time.perf_counter()
            products, report = load_catalog(path)   # format = the file's own suffix
            job.seconds["parse"] = time.perf_counter() - t0
            job.total, job.skipped = len(products), report.skipped
            job.stage = "matching"
            t1 = time.perf_counter()
            for i in range(0, len(products), CHUNK):
                job.items.extend(self.classify(products[i:i + CHUNK]))
                job.done = min(i + CHUNK, len(products))
            job.seconds["match"] = time.perf_counter() - t1
            job.stage = "done"
        except Exception as e:
            log.error("upload_job_failed", job_id=job_id, error=repr(e))
            job.stage, job.error = "failed", f"Не удалось обработать файл: {type(e).__name__}"
        finally:
            path.unlink(missing_ok=True)

    # -- human review ---------------------------------------------------------------------
    def override(self, sku: str, work_types: list[str], reviewer: str) -> None:
        bad = set(work_types) - set(work_type_ids())
        if bad:
            raise ValueError(f"Неизвестные виды работ: {sorted(bad)}")
        with self._lock:
            self.overrides[sku] = {"work_types": sorted(set(work_types)), "reviewer": reviewer,
                                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if self._path:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._path.write_text(json.dumps(self.overrides, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
            for job in self.jobs.values():
                for it in job.items:
                    if it.sku == sku:
                        it.hits = [WorkHit(w, "material", 1.0, "human", f"проверил {reviewer}")
                                   for w in sorted(set(work_types))]
                        it.review, it.review_reason, it.verified = False, "", True


def role_ru(role: str) -> str:
    return {"material": "материал", "tool": "инструмент", "consumable": "расходник"}.get(role, role)


__all__ = ["ROLES", "UploadJob", "WorkItem", "WorkTypeService", "work_type_names"]
