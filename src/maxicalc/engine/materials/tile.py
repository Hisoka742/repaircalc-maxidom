"""Tile, adhesive, grout.

Grout: q = (A + B) / (A x B) x C x D x rho  [kg/m2], A,B tile sides mm, C tile thickness mm,
D joint width mm, rho kg/dm3 -- the standard formula used by Ceresit / Litokol calculators.
Adhesive fallback table is a typical-range placeholder (kg/m2 by largest tile side);
a value from the product card always takes precedence.
"""
from decimal import Decimal

from maxicalc.engine.materials import waste
from maxicalc.engine.result import Calc
from maxicalc.engine.units import Number, ceil_int, d

# Ceresit CM 11 technical description (01.2020), "Ориентировочный расход":
# (max tile side mm inclusive, kg/m2). Last row is "от 5,5" for up to 50 cm tiles
# (combined application); larger formats are outside the sheet and use the same floor value.
ADHESIVE_FALLBACK = [(50, Decimal("1.7")), (100, Decimal("2.0")), (150, Decimal("2.7")),
                     (250, Decimal("3.6")), (300, Decimal("4.2")), (100_000, Decimal("5.5"))]

# Ceresit CM 11 PLUS technical description, "ориентировочный расход клея CM 11 в зависимости от
# размера плитки" (datasheets.tdx.henkel.com/CERESIT-CM-11-ru_KZ.pdf): side of the tile, cm ->
# trowel tooth, mm -> kg/m2: <=5: 3 -> ~2.0; <=10: 4 -> ~2.5; <=15: 6 -> ~3.0; <=25: 8 -> ~3.7;
# <=30: 10 -> ~4.2; <=40: 12 -> ~5.2. The edition above (01.2020, "CM 11") differs on five rows
# (1.7 / 2.0 / 2.7 / 3.6 / 5.5): both are the manufacturer's figures for different editions, so the
# table is selectable and the service picks the PLUS one for a product that says "CM 11 PLUS".
ADHESIVE_TABLES: dict[str, list[tuple[int, Decimal]]] = {
    "cm11": ADHESIVE_FALLBACK,
    # ОСНОВИТ ГРАНИПЛИКС АС14 F (техкарта от 17.10.2025, osnovit.ru, раздел «РАСХОД»):
    # «до 15 см — зуб 4 мм — слой 2 мм — 2,6 кг/м²; до 30 см — 6 / 3 / 3,9; до 60 см — 8 / 4 /
    # 5,2; до 100 см — 10 / 5 / 6,5». Used for ОСНОВИТ tile adhesives (the brand is in the catalog).
    "osnovit_ac14": [(150, Decimal("2.6")), (300, Decimal("3.9")), (600, Decimal("5.2")),
                     (1000, Decimal("6.5")), (100_000, Decimal("6.5"))],
    "cm11_plus": [(50, Decimal("2.0")), (100, Decimal("2.5")), (150, Decimal("3.0")),
                  (250, Decimal("3.7")), (300, Decimal("4.2")), (100_000, Decimal("5.2"))],
}

# Ceresit CE 40 Aquastatic, "ориентировочный расход сухой смеси в зависимости от ширины шва и
# размера плитки" (datasheets.tdx.henkel.com/CERESIT-CE-40-ru_KZ.pdf), kg per m2 of cladding:
# (tile sides in cm, sorted; joint in mm) -> kg/m2. Tile thickness is not stated by the sheet.
GROUT_TABLES: dict[str, dict[tuple[int, int, int], Decimal]] = {
    "ce40": {(5, 5, 2): Decimal("0.6"), (5, 5, 3): Decimal("0.7"), (10, 10, 2): Decimal("0.4"),
             (10, 20, 3): Decimal("0.4"), (15, 15, 3): Decimal("0.4"), (20, 20, 5): Decimal("0.5")},
}


def area_with_waste(
    area_m2: Number, layout: str, tile_w_mm: Number, tile_h_mm: Number,
    table: waste.WasteTable | None = None,
) -> Calc:
    a = d(area_m2)
    if a < 0:
        raise ValueError("Площадь не может быть отрицательной")
    t = table or waste.DEFAULT_TABLE
    w = waste.layout_waste(layout, t)
    ex = [f"Запас по раскладке [{layout}]: {w} ({t.source})"]
    if a < t.small_room_area_m2:
        w += t.small_room_extra
        ex.append(f"Малая площадь (<{t.small_room_area_m2} м²): +{t.small_room_extra}")
    if max(d(tile_w_mm), d(tile_h_mm)) >= t.large_format_side_mm:
        w += t.large_format_extra
        ex.append(f"Крупный формат: +{t.large_format_extra}")
    v = a * (1 + w)
    ex.append(f"{a} м² × (1 + {w}) = {v} м²")
    return Calc(v, "м²", tuple(ex))


def packs(
    area_with_waste_m2: Number,
    m2_per_pack: Number | None = None,
    pcs_per_pack: int | None = None,
    tile_w_mm: Number | None = None,
    tile_h_mm: Number | None = None,
) -> Calc:
    a = d(area_with_waste_m2)
    if pcs_per_pack is not None and tile_w_mm is not None and tile_h_mm is not None:
        if pcs_per_pack < 1:
            raise ValueError("Некорректная фасовка")
        piece = d(tile_w_mm) * d(tile_h_mm) / 1_000_000
        pcs = ceil_int(a / piece)
        n = -(-pcs // pcs_per_pack)
        return Calc(Decimal(n), "уп",
                    (f"{a} м² / {piece} м² = {pcs} шт; ceil({pcs}/{pcs_per_pack}) = {n} уп",))
    if m2_per_pack is None or d(m2_per_pack) <= 0:
        raise ValueError("Нужна площадь упаковки или штук в упаковке с размером плитки")
    p = d(m2_per_pack)
    n = ceil_int(a / p)
    return Calc(Decimal(n), "уп", (f"ceil({a} / {p}) = {n} уп",))


def grout_kg_per_m2(
    tile_w_mm: Number, tile_h_mm: Number, tile_thickness_mm: Number,
    joint_mm: Number, density_kg_per_dm3: Number = "1.6",
) -> Calc:
    a, b, c = d(tile_w_mm), d(tile_h_mm), d(tile_thickness_mm)
    j, rho = d(joint_mm), d(density_kg_per_dm3)
    if min(a, b, c, j, rho) <= 0:
        raise ValueError("Некорректные параметры затирки")
    q = (a + b) * c * j * rho / (a * b)  # multiply first: exact for typical inputs
    return Calc(q, "кг/м²", (f"({a}+{b})/({a}×{b}) × {c} × {j} × {rho} = {q} кг/м²",))


def grout_kg(
    area_m2: Number, tile_w_mm: Number, tile_h_mm: Number, tile_thickness_mm: Number,
    joint_mm: Number, density_kg_per_dm3: Number = "1.6",
) -> Calc:
    q = grout_kg_per_m2(tile_w_mm, tile_h_mm, tile_thickness_mm, joint_mm, density_kg_per_dm3)
    a = d(area_m2)
    m = a * q.value
    return Calc(m, "кг", (*q.explain, f"{a} м² × {q.value} = {m} кг"))


# joints (nodes) per laid tile by layout: a 4-way node is shared by 4 tiles (1 per tile); in a
# running-bond / herringbone layout the nodes are T-shaped, shared by 3 tiles, 6 per tile (2).
SPACER_NODES_PER_TILE = {"straight": Decimal(1), "diagonal": Decimal(1),
                         "offset": Decimal(2), "herringbone": Decimal(2)}


def spacers(
    area_m2: Number, tile_w_mm: Number, tile_h_mm: Number, joint_mm: Number,
    layout: str = "straight",
) -> Calc:
    """Spacers (крестики / СВП clips) from the layout geometry, pieces.

    Tiles laid n = A / ((w + j)(h + j)) (the pitch includes the joint). One spacer per joint node:
    interior nodes = n x nodes_per_tile (1 straight / diagonal, 2 offset / herringbone), plus the
    perimeter nodes of a roughly square field, 2 x sqrt(n) x nodes_per_tile (each takes one
    spacer: a T-spacer or a cut cross). Rounded up to a piece; packs are rounded by the caller.
    Estimate: spacers are lost and re-used, so a pack of the next size is normal.
    """
    a, w, h, j = d(area_m2), d(tile_w_mm), d(tile_h_mm), d(joint_mm)
    if a < 0 or min(w, h) <= 0 or j <= 0:
        raise ValueError("Некорректные параметры раскладки")
    k = SPACER_NODES_PER_TILE.get(layout, Decimal(1))
    n = a * 1_000_000 / ((w + j) * (h + j))
    interior = n * k
    edge = 2 * n.sqrt() * k
    total = (interior + edge).to_integral_value(rounding="ROUND_CEILING")
    return Calc(total, "шт", (
        f"Плиток в раскладке: {a} м² / (({w}+{j})×({h}+{j})) мм = {n:.1f}",
        f"Узлов: {n:.1f} × {k} (раскладка {layout}) + периметр 2×√{n:.1f}×{k} = "
        f"{interior + edge:.1f} → {total} шт (по одному на узел)"))


def grout_table_kg(
    area_m2: Number, tile_w_mm: Number, tile_h_mm: Number, joint_mm: Number, table: str = "ce40"
) -> Calc | None:
    """Grout by the manufacturer's own table when the tile and joint are one of its rows
    (sides in cm, joint in mm, compared exactly); None otherwise (use the formula)."""
    w, h, j = d(tile_w_mm) / 10, d(tile_h_mm) / 10, d(joint_mm)
    if w != int(w) or h != int(h) or j != int(j):
        return None
    key = (int(min(w, h)), int(max(w, h)), int(j))
    rate = GROUT_TABLES[table].get(key)
    if rate is None:
        return None
    a = d(area_m2)
    if a < 0:
        raise ValueError("Площадь не может быть отрицательной")
    m = a * rate
    return Calc(m, "кг", (f"{a} м² × {rate} кг/м² (таблица производителя: плитка "
                          f"{key[0]}×{key[1]} см, шов {key[2]} мм) = {m} кг",))


def adhesive_kg(
    area_m2: Number, tile_w_mm: Number, tile_h_mm: Number, kg_per_m2: Number | None = None,
    table: str = "cm11",
) -> Calc:
    a = d(area_m2)
    if kg_per_m2 is not None:
        r = d(kg_per_m2)
        src = "из карточки товара"
    else:
        side = max(d(tile_w_mm), d(tile_h_mm))
        r = next(rate for lim, rate in ADHESIVE_TABLES[table] if side <= lim)
        src = f"по таблице производителя [{table}] для плитки {side} мм (оценка)"
    if r <= 0 or a < 0:
        raise ValueError("Некорректные параметры клея")
    m = a * r
    return Calc(m, "кг", (f"{a} м² × {r} кг/м² ({src}) = {m} кг",))
