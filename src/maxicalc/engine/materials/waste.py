"""Waste (запас) factors by layout, as DATA: a `WasteTable` the caller can replace.

The defaults are conservative upper-range values of the typical 5-7% (straight) and 10-15%
(diagonal / herringbone) ranges. A table can be fitted from real orders (ml/waste_fit.py,
scripts/fit_waste.py); every calculation names the table it used in its `explain`.
The engine stays pure: it never reads the table from disk, the service layer passes it in.
"""
from dataclasses import dataclass
from decimal import Decimal

Layout = str  # "straight" | "diagonal" | "herringbone"


@dataclass(frozen=True)
class WasteTable:
    layouts: dict[str, Decimal]
    small_room_extra: Decimal
    large_format_extra: Decimal
    source: str
    small_room_area_m2: Decimal = Decimal("4")
    large_format_side_mm: int = 600


DEFAULT_TABLE = WasteTable(
    layouts={"straight": Decimal("0.07"), "diagonal": Decimal("0.12"),
             "herringbone": Decimal("0.15")},
    small_room_extra=Decimal("0.03"), large_format_extra=Decimal("0.03"),
    source="нормативные значения по умолчанию",
)

# kept for importers of the old constants
LAYOUT_WASTE: dict[str, Decimal] = dict(DEFAULT_TABLE.layouts)
SMALL_ROOM_AREA_M2 = DEFAULT_TABLE.small_room_area_m2
SMALL_ROOM_EXTRA = DEFAULT_TABLE.small_room_extra
LARGE_FORMAT_SIDE_MM = DEFAULT_TABLE.large_format_side_mm
LARGE_FORMAT_EXTRA = DEFAULT_TABLE.large_format_extra


def layout_waste(layout: str, table: WasteTable | None = None) -> Decimal:
    t = table or DEFAULT_TABLE
    try:
        return t.layouts[layout]
    except KeyError:
        raise ValueError(f"Неизвестная раскладка: {layout}") from None
