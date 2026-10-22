"""/api/v1/catalog/upload and friends: the full cycle for a new catalog or a single new product.

    POST /catalog/upload                multipart file (YML, CSV, XLSX, JSON, .gz) -> job
    GET  /catalog/upload/{job}          progress, timings, summary, one page of results
    GET  /catalog/upload/{job}/review   products the system is unsure about (review queue)
    POST /catalog/work-types/classify   one new product (name + description) -> work types, fast
    GET  /catalog/work-types            the taxonomy
    POST /catalog/work-review/{sku}     a human fixes the work types (always wins)
"""
import shutil
import tempfile
import time
from pathlib import Path
from typing import Annotated, Literal

import yaml
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from maxicalc.api.state import AppState
from maxicalc.api.worktype_service import UploadJob, WorkItem, WorkTypeService, role_ru
from maxicalc.catalog.schema import Product
from maxicalc.ml.worktypes import KNOW, work_type_names

wt_router = APIRouter(prefix="/v1", tags=["work-types"])
MAX_UPLOAD_MB = 250
ALLOWED = (".xml", ".yml", ".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".json", ".jsonl", ".gz")


class WorkHitOut(BaseModel):
    work: str
    name: str
    role: Literal["material", "tool", "consumable"]
    role_ru: str
    confidence: float
    source: Literal["rule", "model", "human"]
    evidence: str


class WorkItemOut(BaseModel):
    sku: str
    name: str
    category: str
    work_types: list[WorkHitOut]
    review: bool
    review_reason: str = ""
    verified: bool = False


class UploadAccepted(BaseModel):
    job_id: str
    status: Literal["accepted"] = "accepted"
    filename: str


class UploadStatus(BaseModel):
    job_id: str
    stage: Literal["queued", "parsing", "matching", "done", "failed"]
    filename: str
    total: int
    done: int
    skipped: int
    seconds: dict[str, float]
    ms_per_1k_products: float | None = None
    summary: dict[str, int] | None = None
    results: list[WorkItemOut] | None = None
    error: str | None = None


class ClassifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=500)
    description: str = Field(default="", max_length=5000)
    category: str = Field(default="", max_length=500, description="путь через « > »")
    brand: str | None = None
    params: dict[str, str] = Field(default_factory=dict)


class ClassifyOut(BaseModel):
    item: WorkItemOut
    milliseconds: float


class WorkReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_types: list[str] = Field(max_length=45)
    reviewer: str = Field(min_length=1, max_length=64)


def svc(request: Request) -> WorkTypeService:
    st: AppState = request.app.state.maxi
    return st.worktypes


def _item_out(it: WorkItem) -> WorkItemOut:
    names = work_type_names()
    hits = [WorkHitOut(work=h.work, name=names[h.work], role=h.role,  # type: ignore[arg-type]
                       role_ru=role_ru(h.role), confidence=round(h.confidence, 3),
                       source=h.source,  # type: ignore[arg-type]
                       evidence=h.evidence) for h in it.hits]
    return WorkItemOut(sku=it.sku, name=it.name, category=it.category, work_types=hits,
                       review=it.review, review_reason=it.review_reason, verified=it.verified)


def _summary(job: UploadJob) -> dict[str, int]:
    return {"products": len(job.items),
            "with_work_types": sum(1 for i in job.items if i.hits),
            "no_work_type": sum(1 for i in job.items if not i.hits),
            "review": sum(1 for i in job.items if i.review),
            "verified": sum(1 for i in job.items if i.verified)}


@wt_router.post("/catalog/upload", response_model=UploadAccepted, status_code=202,
                summary="Загрузить каталог (YML/CSV/XLSX/JSON) -> фоновая разметка по видам работ")
async def upload_ep(file: UploadFile, request: Request) -> UploadAccepted:
    name = Path(file.filename or "catalog").name
    if not name.lower().endswith(ALLOWED):
        raise HTTPException(415, f"Формат не поддерживается: {name}. Допустимо: {ALLOWED}")
    tmp = Path(tempfile.mkdtemp(prefix="maxi_upload_")) / name
    size = 0
    with tmp.open("wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_MB << 20:
                f.close()
                shutil.rmtree(tmp.parent, ignore_errors=True)
                raise HTTPException(413, f"Файл больше {MAX_UPLOAD_MB} МБ")
            f.write(chunk)
    job_id = svc(request).start_upload(tmp, name)
    return UploadAccepted(job_id=job_id, filename=name)


@wt_router.get("/catalog/upload/{job_id}", response_model=UploadStatus,
               summary="Ход разметки, время и страница результатов")
async def upload_status_ep(
    job_id: str, request: Request, limit: Annotated[int, Query(ge=0, le=500)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UploadStatus:
    job = svc(request).jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Задание не найдено")
    done = job.stage == "done"
    per_1k = (job.seconds["match"] / job.total * 1000
              if done and job.total and "match" in job.seconds else None)
    return UploadStatus(
        job_id=job_id, stage=job.stage,  # type: ignore[arg-type]
        filename=job.filename, total=job.total, done=job.done, skipped=job.skipped,
        seconds={k: round(v, 3) for k, v in job.seconds.items()},
        ms_per_1k_products=None if per_1k is None else round(per_1k * 1000, 1),
        summary=_summary(job) if done else None,
        results=[_item_out(i) for i in job.items[offset: offset + limit]] if done else None,
        error=job.error)


@wt_router.get("/catalog/upload/{job_id}/review", response_model=list[WorkItemOut],
               summary="Очередь на проверку: товары, где система не уверена")
async def upload_review_ep(
    job_id: str, request: Request, limit: Annotated[int, Query(ge=1, le=500)] = 50
) -> list[WorkItemOut]:
    job = svc(request).jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Задание не найдено")
    pending = [i for i in job.items if i.review]
    pending.sort(key=lambda i: (max((h.confidence for h in i.hits), default=0.0), i.sku))
    return [_item_out(i) for i in pending[:limit]]


@wt_router.post("/catalog/work-types/classify", response_model=ClassifyOut,
                summary="Новый товар: название + описание -> виды работ за миллисекунды")
async def classify_ep(body: ClassifyIn, request: Request) -> ClassifyOut:
    p = Product(sku="new", name=body.name, description=body.description, brand=body.brand,
                category_path=[c.strip() for c in body.category.split(">") if c.strip()],
                characteristics=body.params)
    t0 = time.perf_counter()
    item = svc(request).classify([p])[0]
    ms = round((time.perf_counter() - t0) * 1000, 2)
    return ClassifyOut(item=_item_out(item), milliseconds=ms)


@wt_router.get("/catalog/work-types", summary="Справочник видов работ")
async def work_types_ep() -> list[dict[str, str]]:
    tax = yaml.safe_load((KNOW / "taxonomy.yaml").read_text(encoding="utf-8"))
    return [{"id": k, "name": v["ru"], "stage": tax["stages"][v["stage"]]}
            for k, v in tax["work_types"].items()]


@wt_router.post("/catalog/work-review/{sku}", summary="Человек исправляет виды работ (приоритет)")
async def work_review_ep(sku: str, body: WorkReviewIn, request: Request) -> dict[str, str]:
    try:
        svc(request).override(sku, body.work_types, body.reviewer)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return {"status": "ok", "sku": sku}
