"""Basket: quantities are summed per SKU in BASE units and rounded to whole packs LAST."""
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from maxicalc.engine.packaging import Pack, cheapest_cover, single_sku_options
from maxicalc.engine.units import ceil_int
from maxicalc.recommend.select import CatalogEntry

if TYPE_CHECKING:
    from maxicalc.service.room_calc import RoomPlan


_LONG_DECIMAL = re.compile(r"\d+\.\d{5,}")


def humanize(line: str) -> str:
    """Display-only: shorten long decimals in a trace to 3 places. Never used for calculation."""
    def short(m: re.Match[str]) -> str:
        out = f"{Decimal(m.group(0)):.3f}".rstrip("0").rstrip(".")
        return out or "0"

    return _LONG_DECIMAL.sub(short, line)


@dataclass
class Need:
    """Requirement for one product in one room, in the product's base unit (л, кг, м², шт)."""

    entry: CatalogEntry
    base_qty: Decimal
    base_unit: str
    pack_size: Decimal          # base units per purchasable pack
    pack_unit: str              # "уп", "шт", "рулон"
    explain: list[str]
    alternatives: list[CatalogEntry] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


# work package of a product type: what the case calls пол / стены / обои / электрика
GROUP_OF = {
    "laminate": "floor", "underlay": "floor", "skirting": "floor", "self_leveling": "floor",
    "tile": "floor", "tile_adhesive": "floor", "grout": "floor", "tile_spacers": "floor",
    "waterproofing": "floor",
    "paint": "walls", "primer": "walls", "putty": "walls", "drywall": "walls",
    "wallpaper": "wallpaper", "wallpaper_glue": "wallpaper",
    "electrical": "electrical",
}
GROUP_TITLE = {"floor": "Пол", "walls": "Стены", "wallpaper": "Обои",
               "electrical": "Электрика", "other": "Прочее"}
GROUP_ORDER = ["floor", "walls", "wallpaper", "electrical", "other"]

# attribute holding one pack's size, by the base unit a need is expressed in
PACK_ATTR = {"л": "pack_volume_l", "кг": "pack_mass_kg", "м²": "m2_per_pack"}


@dataclass(frozen=True)
class GroupTotal:
    key: str
    title: str
    total: Decimal
    skus: list[str]


@dataclass(frozen=True)
class BasketLine:
    sku: str
    name: str
    qty_packs: int
    unit: str
    unit_price: Decimal | None
    line_total: Decimal
    reason: str
    explain: list[str]
    alternatives: list[dict[str, object]]
    product_id: str | None = None
    url: str | None = None
    group: str = "other"
    optimized: dict[str, Any] | None = None


@dataclass
class Basket:
    lines: list[BasketLine] = field(default_factory=list)
    materials_total: Decimal = Decimal(0)
    warnings: list[str] = field(default_factory=list)
    groups: list[GroupTotal] = field(default_factory=list)
    optimized_total: Decimal = Decimal(0)


def _pack_size(entry: CatalogEntry, base_unit: str) -> Decimal | None:
    attr = PACK_ATTR.get(base_unit)
    if attr is None:
        return Decimal(1)   # a roll, a sheet, a piece: the pack is one unit
    v = entry.attrs.get(attr)
    return Decimal(str(v)) if v is not None else None


def _optimized(first: Need, total: Decimal, line_total: Decimal) -> dict[str, Any] | None:
    """Cheapest mix of the chosen product's pack size and its alternatives' pack sizes.

    The basket keeps the single-SKU purchase (predictable, what the explain trace describes);
    this is the offered saving, and it is only offered when it is really cheaper."""
    packs: list[Pack] = []
    names: dict[str, str] = {}
    for e in [first.entry, *first.alternatives]:
        size = first.pack_size if e is first.entry else _pack_size(e, first.base_unit)
        price = e.product.price
        if size is None or size <= 0 or price is None:
            continue
        packs.append(Pack(e.product.sku, size, price))
        names[e.product.sku] = e.product.name
    if len(packs) < 2 or total <= 0:
        return None
    plan = cheapest_cover(total, packs)
    if plan.total_cost >= line_total:
        return None
    best_single = single_sku_options(total, packs)[0]
    return {
        "packs": [{"sku": ln.pack.sku, "name": names[ln.pack.sku], "count": ln.count,
                   "size": ln.pack.size, "price": ln.pack.price} for ln in plan.lines],
        "total": plan.total_cost, "saving": line_total - plan.total_cost,
        "overbuy": plan.overbuy,
        "cheapest_single_sku": {"sku": best_single.lines[0].pack.sku,
                                "count": best_single.lines[0].count,
                                "total": best_single.total_cost},
    }


def build_basket(plans: "list[RoomPlan]") -> Basket:
    order: list[str] = []
    needs: dict[str, list[Need]] = {}
    for plan in plans:
        for n in plan.needs:
            sku = n.entry.product.sku
            if sku not in needs:
                order.append(sku)
                needs[sku] = []
            needs[sku].append(n)

    basket = Basket()
    for sku in order:
        group = needs[sku]
        first = group[0]
        total = sum((n.base_qty for n in group), Decimal(0))
        packs = ceil_int(total / first.pack_size)
        price = first.entry.product.price
        if price is None:
            basket.warnings.append(f"У товара {sku} нет цены — стоимость позиции не учтена")
        line_total = (price or Decimal(0)) * packs
        explain = [humanize(line) for n in group for line in n.explain]
        explain.append(
            f"Итого по всем помещениям: {total} {first.base_unit}; "
            f"ceil({total} / {first.pack_size}) = {packs} {first.pack_unit}")
        explain[-1] = humanize(explain[-1])
        reason = next((r for n in group for r in n.reasons), "рассчитано по характеристикам товара")
        alts = [
            {"sku": a.product.sku, "name": a.product.name,
             "price": None if a.product.price is None else str(a.product.price)}
            for a in first.alternatives
        ]
        basket.lines.append(BasketLine(
            sku, first.entry.product.name, packs, first.pack_unit, price, line_total, reason,
            explain, alts, first.entry.product.product_id, first.entry.product.url,
            GROUP_OF.get(first.entry.calc, "other"),
            _optimized(first, total, line_total) if price is not None else None))
        basket.materials_total += line_total
    totals: dict[str, Decimal] = {}
    members: dict[str, list[str]] = {}
    for ln in basket.lines:
        totals[ln.group] = totals.get(ln.group, Decimal(0)) + ln.line_total
        members.setdefault(ln.group, []).append(ln.sku)
    basket.groups = [GroupTotal(k, GROUP_TITLE[k], totals[k], members[k])
                     for k in GROUP_ORDER if k in totals]
    basket.optimized_total = sum(
        (ln.optimized["total"] if ln.optimized else ln.line_total for ln in basket.lines),
        Decimal(0))
    return basket
