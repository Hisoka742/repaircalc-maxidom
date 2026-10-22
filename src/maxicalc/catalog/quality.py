"""Data-quality report for a loaded catalog: how much of it the calculators can actually use.

Field coverage (share of products that have the field) and the unit/pack parse rates. Read this
before trusting any calculation on a new catalog: a product without pack data produces a warning,
not a quantity.
"""
from dataclasses import dataclass, field

from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract

_PACK_ATTRS = ("m2_per_pack", "pcs_per_pack", "pack_mass_kg", "pack_volume_l", "roll_length_m")


@dataclass
class Quality:
    total: int = 0
    coverage: dict[str, float] = field(default_factory=dict)
    unit_parse_rate: float = 0.0   # share with a sale unit we can read (упак., шт., м, л, кг…)
    pack_info_rate: float = 0.0    # share with a usable pack size (card, API fields or text)

    def to_markdown(self) -> str:
        names = {"price": "цена", "description": "описание", "characteristics": "характеристики",
                 "category": "категория", "brand": "бренд", "unit": "единица продажи",
                 "stock": "наличие", "rating": "рейтинг"}
        rows = [f"| {names.get(k, k)} | {v * 100:.1f}% |" for k, v in self.coverage.items()]
        return "\n".join([
            "# Качество данных каталога", "", f"Товаров: **{self.total}**", "",
            "| поле | покрытие |", "|---|---|", *rows, "",
            f"- Единица продажи распознана: **{self.unit_parse_rate * 100:.1f}%**",
            f"- Известна фасовка (площадь/масса/объём/штук): **{self.pack_info_rate * 100:.1f}%**",
            "", "Товары без фасовки попадут в смету только с предупреждением, без количества.",
        ])


_UNITS = ("упак", "шт", "м2", "м²", "кв", "м.п", "пог", "рул", "кг", "л", "компл", "м")


def _unit_ok(unit: str | None) -> bool:
    if not unit:
        return False
    u = unit.lower().replace(".", "").strip()
    return any(u.startswith(x.replace(".", "")) for x in _UNITS)


def quality_report(products: list[Product]) -> Quality:
    n = len(products)
    if n == 0:
        return Quality()

    def share(pred) -> float:  # type: ignore[no-untyped-def]
        return sum(1 for p in products if pred(p)) / n

    units = share(lambda p: _unit_ok(p.unit))
    packs = 0
    for p in products:
        if p.package_area_m2 or p.quantity_in_package or any(
                a in extract(p).attrs for a in _PACK_ATTRS):
            packs += 1
    cov = {
        "price": share(lambda p: p.price is not None),
        "description": share(lambda p: bool(p.description.strip())),
        "characteristics": share(lambda p: bool(p.characteristics)),
        "category": share(lambda p: bool(p.category_path)),
        "brand": share(lambda p: bool(p.brand)),
        "unit": share(lambda p: bool(p.unit)),
        "stock": share(lambda p: p.in_stock is not None or p.stock_qty is not None),
        "rating": share(lambda p: p.rating is not None or p.recsys_rating is not None),
    }
    return Quality(n, cov, units, packs / n)
