from decimal import Decimal

from pydantic import BaseModel, Field


class Product(BaseModel):
    """Normalized catalog item, independent of the source format."""

    sku: str
    name: str
    category_path: list[str] = Field(default_factory=list)
    brand: str | None = None
    price: Decimal | None = None
    description: str = ""
    characteristics: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    image_url: str | None = None
    unit: str | None = None
    # --- fields of the organisers' stand API (/api/catalog/products); all optional ---
    product_id: str | None = None         # Bagisto `id`: the key of /api/v1/product/{id}/calc
    cod_good: str | None = None           # source-system code, kept as a string
    list_price: Decimal | None = None     # `price`; `price` above is what we sell at (result_price)
    special_price: Decimal | None = None  # only if active and in its period; never the price shown
    quantity_in_package: Decimal | None = None
    package_area_m2: Decimal | None = None
    price_per_m2: Decimal | None = None
    in_stock: bool | None = None
    stock_qty: Decimal | None = None
    stock_regions: dict[str, Decimal] = Field(default_factory=dict)  # region_id -> qty
    rating: Decimal | None = None         # ratings.rating
    recsys_rating: Decimal | None = None  # popularity score used for ranking
    active: bool | None = None            # `status`
    margin: Decimal | None = None         # 0..1; not in the stand's API (see OPEN_QUESTIONS)


MAX_ISSUES = 200


class IngestReport(BaseModel):
    read: int = 0
    loaded: int = 0
    skipped: int = 0
    issues_total: int = 0
    issues: list[str] = Field(default_factory=list)  # first MAX_ISSUES only

    def add_issue(self, msg: str) -> None:
        self.issues_total += 1
        if len(self.issues) < MAX_ISSUES:
            self.issues.append(msg)
