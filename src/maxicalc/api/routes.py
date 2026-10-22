"""/v1 endpoints. Calc endpoints are `async def`: they compute in a few milliseconds from
precomputed labels, so running them on the event loop beats a thread-pool hop."""
import hashlib
import json
from collections.abc import Callable
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from maxicalc import __version__
from maxicalc.api import mappers
from maxicalc.api import schemas as s
from maxicalc.api.export import PdfUnavailable, build_pdf, build_xlsx
from maxicalc.api.middleware import CATALOG_SIZE, ESTIMATE_CACHE, REVIEW_PENDING
from maxicalc.api.state import AppState
from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Room, WallSurface
from maxicalc.ml.parse_request import parse_request
from maxicalc.ml.synth import Labels
from maxicalc.ml.taxonomy import load_taxonomy
from maxicalc.recommend import rag
from maxicalc.recommend.index import CatalogIndex
from maxicalc.recommend.select import Constraints
from maxicalc.service.property_calc import (
    PropertyEstimate,
    PropertyInput,
    RoomInput,
    calc_product,
    calc_property,
    calc_room,
    overlays_for,
)
from maxicalc.service.room_calc import ROOM_RU, Conditions

router = APIRouter(prefix="/v1")
# the path the case brief names for the product-card calculator
api_v1 = APIRouter(prefix="/api/v1")
ops = APIRouter()


def state_of(request: Request) -> AppState:
    st: AppState = request.app.state.maxi
    return st


_CACHED_FALSE = '"cached":false}'
_CACHED_TRUE = '"cached":true}'


def _json(body: str) -> Response:
    return Response(body, media_type="application/json")


def _estimate(
    st: AppState, kind: Literal["property", "room", "product"], key: str, payload: dict,  # type: ignore[type-arg]
    compute: Callable[[CatalogIndex], PropertyEstimate],
) -> Response:
    """Idempotent: same request + same catalog version -> same estimate_id and result.

    Returns pre-serialised JSON (skips FastAPI's response re-validation); a cache hit is a
    string operation only. The stored JSON always ends with '"cached":false}'.
    """
    material = json.dumps({"k": key, "r": payload, "v": st.version}, sort_keys=True,
                          ensure_ascii=False)
    eid = hashlib.sha256(material.encode()).hexdigest()[:16]
    hit = st.cache.get("est:" + eid)
    if hit is not None and hit.endswith(_CACHED_FALSE):
        ESTIMATE_CACHE.labels("hit").inc()
        return _json(hit[: -len(_CACHED_FALSE)] + _CACHED_TRUE)
    ESTIMATE_CACHE.labels("miss").inc()
    out = mappers.estimate_out(compute(st.index), eid, kind, st.version)
    body = out.model_dump_json()
    assert body.endswith(_CACHED_FALSE)
    st.cache.set("est:" + eid, body)
    return _json(body)


# ------------------------------------------------------------------ calculators
@router.post("/calc/property", response_model=s.EstimateOut, tags=["calc"],
             summary="Расчёт ремонта объекта целиком")
async def calc_property_ep(req: s.PropertyCalcRequest, request: Request) -> Response:
    st = state_of(request)
    inp = PropertyInput(
        req.property_type, req.total_area_m2, req.renovation_class,
        None if req.rooms is None else [RoomInput(r.room_type, r.area_m2, r.height_m,
                                                  r.humidity, r.load) for r in req.rooms],
        req.tier, req.ceiling_height_m)
    return _estimate(st, "property", "property", req.model_dump(mode="json"),
                     lambda idx: calc_property(inp, idx))


@router.post("/calc/room", response_model=s.EstimateOut, tags=["calc"],
             summary="Расчёт материалов для одной комнаты (с проёмами и сложной формой)")
async def calc_room_ep(req: s.RoomCalcRequest, request: Request) -> Response:
    st = state_of(request)
    room = req.room.to_room()
    return _estimate(
        st, "room", "room", req.model_dump(mode="json"),
        lambda idx: calc_room(room, req.room_type, req.renovation_class, idx, req.tier,
                              req.include_ceiling, req.humidity, req.load,
                              conditions=None if req.conditions is None
                              else Conditions(**req.conditions.model_dump())))


@router.post("/products/{sku}/quantity", response_model=s.EstimateOut, tags=["calc"],
             summary="Калькулятор в карточке товара: сколько упаковок + сопутствующие товары")
async def product_quantity_ep(
    sku: str, req: s.ProductQuantityRequest, request: Request
) -> Response:
    st = state_of(request)
    entry = st.index.get(sku)
    if entry is None:
        raise HTTPException(404, f"Товар {sku} не найден в каталоге")
    room = req.room.to_room()
    return _estimate(
        st, "product", f"product:{sku}", req.model_dump(mode="json"),
        lambda idx: calc_product(room, req.room_type, entry, idx, req.include_ceiling,
                                 req.humidity, req.load))


WALL_CALCS = frozenset({"paint", "primer", "putty", "wallpaper"})
FLOOR_CALCS = frozenset({"laminate", "underlay", "skirting", "self_leveling", "waterproofing"})


def _product_card_calc(st: AppState, product_id: str, req: s.ProductCalcRequest) -> Response:
    """Shared by POST and GET /api/v1/product/{id}/calc: the customer's own dimensions."""
    entry = st.index.get(product_id)
    if entry is None:
        raise HTTPException(404, f"Товар {product_id} не найден в каталоге")
    calc = entry.calc
    if req.wall is not None:
        if calc in FLOOR_CALCS:
            raise ValueError("Для этого товара укажите размеры пола (floor) или комнаты (room)")
        room = WallSurface.of(req.wall.width_m, req.wall.height_m, as_floor=calc == "tile")
        ceiling = False
    elif req.floor is not None:
        if calc in WALL_CALCS:
            raise ValueError("Для этого товара укажите размеры стены (wall) или комнаты (room)")
        room = Room.rectangle(req.floor.length_m, req.floor.width_m, Decimal("2.7"))
        ceiling = False
    else:
        assert req.room is not None
        room = req.room.to_room()
        ceiling = req.include_ceiling
    return _estimate(
        st, "product", f"product:{product_id}", req.model_dump(mode="json"),
        lambda idx: calc_product(room, req.room_type, entry, idx, ceiling, req.humidity,
                                 req.load))


@api_v1.post("/product/{product_id}/calc", response_model=s.EstimateOut, tags=["calc"],
             summary="Калькулятор на карточке товара: сколько упаковок под ваши размеры")
async def product_calc_ep(product_id: str, req: s.ProductCalcRequest, request: Request) -> Response:
    return _product_card_calc(state_of(request), product_id, req)


@api_v1.get("/product/{product_id}/calc", response_model=s.EstimateOut, tags=["calc"],
            summary="То же по GET, для встраивания без JS-клиента")
async def product_calc_get_ep(
    product_id: str, request: Request,
    wall_width_m: Annotated[Decimal | None, Query(gt=0, le=100)] = None,
    wall_height_m: Annotated[Decimal | None, Query(gt=0, le=10)] = None,
    floor_length_m: Annotated[Decimal | None, Query(gt=0, le=100)] = None,
    floor_width_m: Annotated[Decimal | None, Query(gt=0, le=100)] = None,
    room_type: s.RoomType = "living",
    humidity: s.Humidity | None = None,
) -> Response:
    wall = (s.WallIn(width_m=wall_width_m, height_m=wall_height_m)
            if wall_width_m is not None and wall_height_m is not None else None)
    floor = (s.FloorIn(length_m=floor_length_m, width_m=floor_width_m)
             if floor_length_m is not None and floor_width_m is not None else None)
    req = s.ProductCalcRequest(wall=wall, floor=floor, room_type=room_type, humidity=humidity)
    return _product_card_calc(state_of(request), product_id, req)


# ------------------------------------------------------------------ recommendation
@router.post("/recommend", response_model=s.RecommendOut, tags=["recommend"],
             summary="Подбор товаров под тип помещения с объяснением")
async def recommend_ep(req: s.RecommendRequest, request: Request) -> s.RecommendOut:
    st = state_of(request)
    cons = Constraints(req.max_price, req.min_price,
                       frozenset(req.brands) if req.brands else None, req.tier, req.region_id)
    res = st.index.query(req.room_type, req.work_category, req.calc, cons, req.top_k,
                         overlays_for(req.humidity, req.load))
    return s.RecommendOut(
        items=[mappers.candidate_out(c) for c in res.items],
        excluded=[{"sku": k, "reason": v} for k, v in res.excluded[: mappers.EXCLUDED_LIMIT]],
        excluded_total=len(res.excluded), warnings=res.warnings,
        companions=[mappers.candidate_out(c) for c in res.companions])


# ------------------------------------------------------------------ catalog / matching
def _products(req: s.MatchRequest) -> list[Product]:
    return [Product(**p.model_dump()) for p in req.products]


@router.post("/catalog/match", response_model=s.MatchOut, tags=["catalog"],
             summary="Разметка товаров: метки, уверенность, авто/на проверку")
def match_ep(req: s.MatchRequest, request: Request, response: Response) -> s.MatchOut:
    st = state_of(request)
    products = _products(req)
    if len(products) <= st.settings.sync_match_limit:
        return s.MatchOut(status="done", results=mappers.match_products(st, products))
    job_id = st.start_match_job(products, mappers.match_products)
    response.status_code = 202
    return s.MatchOut(status="accepted", job_id=job_id)


@router.get("/catalog/jobs/{job_id}", response_model=s.JobOut, tags=["catalog"])
async def job_ep(job_id: str, request: Request) -> s.JobOut:
    job = state_of(request).jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Задание не найдено")
    return s.JobOut(job_id=job_id, status=job.status,  # type: ignore[arg-type]
                    total=job.total, done=job.done, results=job.results, error=job.error)


@router.get("/catalog/products", response_model=s.CatalogPage, tags=["catalog"],
            summary="Каталог с метками (для админки привязки товаров)")
async def catalog_products_ep(
    request: Request,
    q: Annotated[str | None, Query(max_length=100)] = None,
    sku: Annotated[str | None, Query(max_length=64, description="точный артикул")] = None,
    status: Literal["auto", "review", "verified"] | None = None,
    calc: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> s.CatalogPage:
    st = state_of(request)
    needle = q.lower() if q else None
    rows = [e for e in st.index.entries
            if (sku is None or e.product.sku == sku)
            and (status is None or e.status == status) and (calc is None or e.calc == calc)
            and (needle is None or needle in e.product.name.lower()
                 or needle in e.product.sku.lower()
                 or needle == (e.product.product_id or ""))]
    page = rows[offset: offset + limit]
    return s.CatalogPage(total=len(rows), items=[
        s.CatalogItemOut(
            sku=e.product.sku, product_id=e.product.product_id, name=e.product.name,
            category_path=e.product.category_path, price=e.product.price, brand=e.product.brand,
            calc=e.calc, work_categories=sorted(e.work), room_types=sorted(e.rooms),
            properties=sorted(e.props), status=e.status,  # type: ignore[arg-type]
            attributes={k: str(v) for k, v in e.attrs.items()}) for e in page])


@router.get("/catalog/review-queue", response_model=list[s.ReviewItemOut], tags=["catalog"],
            summary="Товары с низкой уверенностью — на ручную проверку")
async def review_queue_ep(
    request: Request, limit: int = Query(50, ge=1, le=500)
) -> list[s.ReviewItemOut]:
    st = state_of(request)
    out: list[s.ReviewItemOut] = []
    for r in st.review.pending(limit):
        e = st.index.get(r.sku)
        out.append(s.ReviewItemOut(
            sku=r.sku, name=e.product.name if e else r.sku,
            suggestion=mappers.label_out(r.calc_template) if r.calc_template else None,
            confidence=round(r.review_confidence, 4), reasons=r.reasons))
    return out


@router.post("/catalog/rematch", tags=["catalog"],
             summary="Пересчитать разметку каталога (ручные привязки сохраняются)")
def rematch_ep(request: Request) -> dict[str, str | int]:
    st = state_of(request)
    n = st.rematch()
    return {"status": "ok", "products": n, "catalog_version": st.version,
            "review_pending": len(st.review.pending())}


@router.post("/catalog/review/{sku}", tags=["catalog"],
             summary="Подтвердить или исправить разметку товара")
async def review_ep(sku: str, body: s.ReviewIn, request: Request) -> dict[str, str]:
    st = state_of(request)
    tax = load_taxonomy()
    for label, valid, what in (
        *((w, tax.work_categories, "вид работ") for w in body.work_categories),
        *((r, tax.room_types, "тип помещения") for r in body.room_types),
        *((p, tax.properties, "свойство") for p in body.properties),
        (body.calc_template, tax.calc_templates, "тип калькулятора"),
    ):
        if label not in valid:
            raise ValueError(f"Неизвестный {what}: {label}")
    labels = Labels(set(body.work_categories), set(body.room_types) or {"any"},
                    set(body.properties), body.calc_template)
    try:
        st.apply_review(sku, labels, body.reviewer)
    except KeyError:
        raise HTTPException(404, f"Товар {sku} не найден в каталоге") from None
    return {"status": "ok", "catalog_version": st.version}


# ------------------------------------------------------------------ language
@router.post("/parse", response_model=s.ParseOut, tags=["calc"],
             summary="Запрос своими словами -> параметры калькулятора")
def parse_ep(req: s.ParseRequest, request: Request) -> s.ParseOut:
    st = state_of(request)
    p = parse_request(req.text, st.llm)
    ready = bool(p.property_type and p.renovation_class
                 and (p.total_area_m2 or any(r.area_m2 for r in p.rooms)))
    return s.ParseOut(
        property_type=p.property_type, renovation_class=p.renovation_class, tier=p.tier,
        total_area_m2=p.total_area_m2,
        rooms=[s.ParsedRoomOut(room_type=r.room_type, area_m2=r.area_m2, humidity=r.humidity,
                               load=r.load) for r in p.rooms],
        missing=p.missing, method=p.method, notes=p.notes, ready=ready)


@router.post("/estimate/{estimate_id}/explain", response_model=s.ExplainOut, tags=["estimate"],
             summary="Почему эти материалы: объяснение по базе знаний (RAG, локальная LLM)")
def explain_ep(estimate_id: str, request: Request) -> s.ExplainOut:
    st = state_of(request)
    raw = st.cache.get("est:" + estimate_id)
    if raw is None:
        raise HTTPException(404, "Смета не найдена или устарела — повторите расчёт")
    est = s.EstimateOut.model_validate_json(raw)
    lines = []
    for ln in est.basket.lines:
        e = st.index.get(ln.sku)
        lines.append(rag.LineCtx(ln.sku, ln.name, e.calc if e else "none", ln.qty_packs, ln.unit,
                                 str(ln.line_total), ln.reason))
    overlays = {o for r in est.rooms
                for o, v in (("wet_zone", r.humidity), ("heavy_traffic", r.load)) if v == "high"}
    ctx = rag.Context([(r.room_type, str(r.area_m2)) for r in est.rooms], lines,
                      str(est.basket.materials_total), est.warnings, overlays, ROOM_RU)
    out = rag.explain(ctx, st.llm)
    return s.ExplainOut(
        text=out.text, method=out.method, note=out.note,
        facts=[s.FactOut(id=f.id, text=f.text, source=f.source) for f in out.facts])


# ------------------------------------------------------------------ export
@router.post("/estimate/{estimate_id}/export", tags=["estimate"],
             summary="Смета для B2B: XLSX или PDF",
             response_class=Response,
             responses={200: {"content": {
                 "application/pdf": {}, "application/vnd.openxmlformats-officedocument."
                 "spreadsheetml.sheet": {}}}})
async def export_ep(
    estimate_id: str, request: Request,
    format: Literal["xlsx", "pdf"] = Query("xlsx"),
) -> Response:
    st = state_of(request)
    raw = st.cache.get("est:" + estimate_id)
    if raw is None:
        raise HTTPException(404, "Смета не найдена или устарела — повторите расчёт")
    est = s.EstimateOut.model_validate_json(raw)
    if format == "xlsx":
        body = build_xlsx(est)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        try:
            body = build_pdf(est, st.settings.pdf_font_path)
        except PdfUnavailable as e:
            raise HTTPException(501, str(e)) from None
        media = "application/pdf"
    return Response(body, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="smeta-{estimate_id}.{format}"'})


# ------------------------------------------------------------------ ops
@ops.get("/health", tags=["ops"])
async def health(request: Request) -> dict[str, str | int | bool]:
    st = state_of(request)
    return {"status": "ok", "version": __version__, "catalog_size": len(st.index),
            "catalog_version": st.version, "cache": st.cache.name,
            "model_loaded": st.model_loaded,
            "llm": (f"{st.settings.llm_model}" if st.settings.llm_enabled else "off")}


@ops.get("/ready", tags=["ops"], summary="Готовность: каталог загружен")
async def ready(request: Request, response: Response) -> dict[str, str | int | bool]:
    """Readiness for an orchestrator: 503 until a catalog is loaded. The LLM is reported but
    never required: calculations work without it."""
    st = state_of(request)
    ok = len(st.index) > 0
    if not ok:
        response.status_code = 503
    return {"ready": ok, "catalog_size": len(st.index), "catalog_version": st.version,
            "llm": st.settings.llm_model if st.llm is not None else "off"}


@ops.get("/metrics", tags=["ops"], include_in_schema=False)
async def metrics(request: Request) -> Response:
    st = state_of(request)
    CATALOG_SIZE.set(len(st.index))
    REVIEW_PENDING.set(len(st.review.pending()))
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
