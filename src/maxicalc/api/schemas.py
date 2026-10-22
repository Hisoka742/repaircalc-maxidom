"""API schemas. Decimals serialize as strings (exact money / quantities)."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maxicalc.engine.geometry import Opening, Room

RoomType = Literal["living", "bedroom", "kitchen", "bathroom", "kids", "hallway", "balcony"]
RenovationClass = Literal["cosmetic", "major", "designer"]
Tier = Literal["economy", "standard", "premium"]
PropertyType = Literal["apartment", "studio", "house"]
Humidity = Literal["normal", "high"]
Load = Literal["normal", "high"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------- requests ----------------
class RoomIn(Strict):
    room_type: RoomType = Field(description="Тип помещения")
    area_m2: Decimal = Field(gt=0, le=500, description="Площадь, м²")
    height_m: Decimal | None = Field(default=None, ge=Decimal("1.8"), le=8,
                                     description="Высота потолка, м")
    humidity: Humidity | None = Field(
        default=None, description="Влажность: high — требования для влажных зон, как в санузле")
    load: Load | None = Field(
        default=None, description="Нагрузка: high — требования к износостойкости")


class PropertyCalcRequest(Strict):
    property_type: PropertyType = Field(description="Тип объекта: квартира, студия, дом")
    total_area_m2: Decimal = Field(gt=0, le=5000, description="Общая площадь, м²")
    renovation_class: RenovationClass = Field(description="Класс ремонта")
    tier: Tier | None = Field(default=None, description="Ценовой уровень подбираемых товаров")
    ceiling_height_m: Decimal | None = Field(default=None, ge=Decimal("1.8"), le=8)
    rooms: list[RoomIn] | None = Field(
        default=None, max_length=30,
        description="Если указано — заменяет типовую раскладку комнат")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "property_type": "apartment", "total_area_m2": "60", "renovation_class": "cosmetic",
        "tier": "standard"}]})


class OpeningIn(Strict):
    kind: Literal["door", "window"] = Field(description="Дверь или окно")
    width_m: Decimal = Field(gt=0, le=5)
    height_m: Decimal = Field(gt=0, le=4)
    wall: int = Field(ge=0, le=63, description="Номер стены (от 0, по порядку вершин)")


class GeometryIn(Strict):
    length_m: Decimal | None = Field(default=None, gt=0, le=100)
    width_m: Decimal | None = Field(default=None, gt=0, le=100)
    vertices: list[tuple[Decimal, Decimal]] | None = Field(
        default=None, min_length=3, max_length=64,
        description="Контур комнаты в метрах (для Г-образных и других форм)")
    height_m: Decimal = Field(default=Decimal("2.7"), ge=Decimal("1.8"), le=8)
    openings: list[OpeningIn] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def _shape(self) -> "GeometryIn":
        rect = self.length_m is not None and self.width_m is not None
        if not rect and not self.vertices:
            raise ValueError("Укажите длину и ширину комнаты или контур (vertices)")
        if rect and self.vertices:
            raise ValueError("Укажите либо длину и ширину, либо контур, но не оба варианта")
        return self

    def to_room(self) -> Room:
        ops = [Opening(o.kind, o.width_m, o.height_m, o.wall) for o in self.openings]
        if self.vertices:
            return Room.from_vertices(self.vertices, self.height_m, ops)
        assert self.length_m is not None and self.width_m is not None
        return Room.rectangle(self.length_m, self.width_m, self.height_m, ops)


class ConditionsIn(Strict):
    """Work conditions that change quantities (each shows coefficient, reason and source)."""

    floor_layout: Literal["straight", "diagonal", "herringbone"] = "straight"
    wall_evenness: Literal["even", "uneven"] = "even"
    paint_surface: Literal["smooth", "absorbent"] = "smooth"
    paint_layers: int = Field(default=2, ge=1, le=4)
    plaster_application: Literal["manual", "machine"] = "manual"


class RoomCalcRequest(Strict):
    room: GeometryIn
    room_type: RoomType
    renovation_class: RenovationClass
    tier: Tier | None = None
    include_ceiling: bool = Field(default=True, description="Красить/грунтовать потолок")
    humidity: Humidity | None = None
    load: Load | None = None
    conditions: ConditionsIn | None = Field(
        default=None, description="Условия работ: раскладка, ровность стен, основание, слои")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "room": {"length_m": "4", "width_m": "3", "height_m": "2.5",
                 "openings": [{"kind": "door", "width_m": "0.9", "height_m": "2.05", "wall": 0}]},
        "room_type": "living", "renovation_class": "cosmetic"}]})


class ProductQuantityRequest(Strict):
    room: GeometryIn
    room_type: RoomType
    include_ceiling: bool = True
    humidity: Humidity | None = None
    load: Load | None = None

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "room": {"length_m": "3", "width_m": "3", "height_m": "2.5"}, "room_type": "kitchen"}]})


class WallIn(Strict):
    width_m: Decimal = Field(gt=0, le=100, description="Ширина стены, м")
    height_m: Decimal = Field(gt=0, le=10, description="Высота стены, м")


class FloorIn(Strict):
    length_m: Decimal = Field(gt=0, le=100)
    width_m: Decimal = Field(gt=0, le=100)


class ProductCalcRequest(Strict):
    """Калькулятор в карточке товара: покупатель вводит размеры одной поверхности или комнаты.

    Ровно один из вариантов: `wall` (стена W×H), `floor` (пол L×W) или `room` (комната)."""

    wall: WallIn | None = None
    floor: FloorIn | None = None
    room: GeometryIn | None = None
    room_type: RoomType = "living"
    humidity: Humidity | None = None
    load: Load | None = None
    include_ceiling: bool = False

    @model_validator(mode="after")
    def _one(self) -> "ProductCalcRequest":
        if sum(x is not None for x in (self.wall, self.floor, self.room)) != 1:
            raise ValueError("Укажите ровно один вариант: wall, floor или room")
        return self

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"wall": {"width_m": "4.2", "height_m": "2.6"}}]})


class RecommendRequest(Strict):
    room_type: RoomType
    humidity: Humidity | None = None
    load: Load | None = None
    region_id: str | None = Field(default=None, max_length=20,
                                  description="Регион: учитывать наличие на складах региона")
    calc: str | None = Field(default=None, max_length=40,
                             description="Тип товара (калькулятора): paint, tile, …")
    work_category: str | None = Field(default=None, max_length=40)
    tier: Tier | None = None
    max_price: Decimal | None = Field(default=None, gt=0)
    min_price: Decimal | None = Field(default=None, ge=0)
    brands: list[str] | None = Field(default=None, max_length=20)
    top_k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _need_type(self) -> "RecommendRequest":
        if not self.calc and not self.work_category:
            raise ValueError("Укажите calc (тип товара) или work_category (вид работ)")
        return self

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "room_type": "bathroom", "calc": "paint", "tier": "standard", "top_k": 3}]})


class ProductIn(Strict):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=500)
    category_path: list[str] = Field(default_factory=list, max_length=10)
    brand: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    description: str = Field(default="", max_length=5000)
    characteristics: dict[str, str] = Field(default_factory=dict)


class MatchRequest(Strict):
    products: list[ProductIn] = Field(min_length=1, max_length=50000)


class ReviewIn(Strict):
    work_categories: list[str] = Field(max_length=14)
    room_types: list[str] = Field(default_factory=lambda: ["any"], max_length=8)
    properties: list[str] = Field(default_factory=list, max_length=12)
    calc_template: str
    reviewer: str = Field(min_length=1, max_length=64)


class ParseRequest(Strict):
    text: str = Field(min_length=3, max_length=1000,
                      description="Запрос своими словами: «квартира, капитальный, санузел 6 м²»")


# ---------------- responses ----------------
class ParsedRoomOut(BaseModel):
    room_type: str
    area_m2: Decimal | None
    humidity: str | None = None
    load: str | None = None


class ParseOut(BaseModel):
    property_type: str | None
    renovation_class: str | None
    tier: str | None
    total_area_m2: Decimal | None
    rooms: list[ParsedRoomOut]
    missing: list[str] = Field(description="Чего не хватило в тексте: это нужно уточнить")
    method: Literal["rules", "llm", "none"]
    notes: list[str]
    ready: bool = Field(description="Можно ли сразу считать (хватает типа, класса и площади)")


class FactOut(BaseModel):
    id: str
    text: str
    source: str


class ExplainOut(BaseModel):
    text: str
    method: Literal["llm", "template"] = Field(description="Чем получено объяснение")
    facts: list[FactOut]
    note: str = ""

class AlternativeOut(BaseModel):
    sku: str
    name: str
    price: str | None


class OptimizedPackOut(BaseModel):
    sku: str
    name: str
    count: int
    size: Decimal
    price: Decimal


class CheapestSingleOut(BaseModel):
    sku: str
    count: int
    total: Decimal


class OptimizedOut(BaseModel):
    """A cheaper mix of pack sizes for the same quantity (the basket itself stays single-SKU)."""

    packs: list[OptimizedPackOut]
    total: Decimal
    saving: Decimal
    overbuy: Decimal
    cheapest_single_sku: CheapestSingleOut


class GroupOut(BaseModel):
    key: str
    title: str
    total: Decimal
    skus: list[str]


class BasketLineOut(BaseModel):
    sku: str
    product_id: str | None = None
    url: str | None = None
    name: str
    qty_packs: int = Field(description="Сколько упаковок купить (округлено вверх в самом конце)")
    unit: str
    unit_price: Decimal | None
    line_total: Decimal
    reason: str = Field(description="Почему товар подходит")
    group: str = "other"
    optimized: OptimizedOut | None = None
    explain: list[str] = Field(description="Ход расчёта количества")
    alternatives: list[AlternativeOut]


class BasketOut(BaseModel):
    lines: list[BasketLineOut]
    materials_total: Decimal
    optimized_total: Decimal
    groups: list[GroupOut] = Field(default_factory=list)


class RoomOut(BaseModel):
    room_type: str
    area_m2: Decimal
    height_m: Decimal
    humidity: str | None = None
    load: str | None = None


class ElectricalOut(BaseModel):
    room: str
    sockets: int
    switches: int
    light_points: int
    junction_boxes: int
    cable_m: Decimal
    breakers: int
    note: str = "Оценка по типовым нормам, не проект электрики"


class LaborItemOut(BaseModel):
    work: str
    title: str
    quantity: Decimal
    unit: str
    rate: Decimal
    expected: Decimal


class LaborOut(BaseModel):
    """Labor cost range; absent (null) until every needed rate is sourced."""

    low: Decimal
    expected: Decimal
    high: Decimal
    items: list[LaborItemOut]
    explain: list[str]


class EstimateOut(BaseModel):
    estimate_id: str
    kind: Literal["property", "room", "product"]
    catalog_version: str
    rooms: list[RoomOut]
    basket: BasketOut
    labor: LaborOut | None = Field(
        default=None, description="Стоимость работ: диапазон; null, если не хватает ставок")
    labor_note: str = Field(default="", description="Почему стоимость работ не рассчитана")
    warnings: list[str]
    assumptions: list[str]
    electrical: list[ElectricalOut]
    cached: bool = False


class CandidateOut(BaseModel):
    sku: str
    product_id: str | None = None
    rating: Decimal | None = None
    in_stock: bool | None = None
    name: str
    price: Decimal | None
    calc: str
    score: float
    price_tier: str | None
    reasons: list[str]


class RecommendOut(BaseModel):
    items: list[CandidateOut]
    excluded: list[dict[str, str]] = Field(description="Отсеянные товары и причины (до 50)")
    excluded_total: int
    warnings: list[str]
    companions: list[CandidateOut] = Field(
        default_factory=list,
        description="Сопутствующие товары: аксессуары выбранного калькулятора и СИЗ")


class LabelOut(BaseModel):
    label: str
    confidence: float
    source: Literal["rule", "model"]
    accepted: bool
    reason: str = ""


class MatchItemOut(BaseModel):
    sku: str
    status: Literal["auto", "review"]
    calc_template: LabelOut | None
    work_categories: list[LabelOut]
    room_types: list[LabelOut]
    properties: list[LabelOut]
    attributes: dict[str, str]
    reasons: list[str]


class MatchOut(BaseModel):
    status: Literal["done", "accepted"]
    results: list[MatchItemOut] | None = None
    job_id: str | None = None


class JobOut(BaseModel):
    job_id: str
    status: Literal["running", "done", "failed"]
    total: int
    done: int
    results: list[MatchItemOut] | None = None
    error: str | None = None


class CatalogItemOut(BaseModel):
    sku: str
    product_id: str | None
    name: str
    category_path: list[str]
    price: Decimal | None
    brand: str | None
    calc: str
    work_categories: list[str]
    room_types: list[str]
    properties: list[str]
    status: Literal["auto", "review", "verified"]
    attributes: dict[str, str]


class CatalogPage(BaseModel):
    total: int
    items: list[CatalogItemOut]


class ReviewItemOut(BaseModel):
    sku: str
    name: str
    suggestion: LabelOut | None
    confidence: float
    reasons: list[str]
