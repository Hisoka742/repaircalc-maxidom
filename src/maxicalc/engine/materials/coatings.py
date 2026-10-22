"""Paint, primer, putty/plaster/screed: quantity = area x rate; packs last."""
from decimal import Decimal

from maxicalc.engine.result import Calc
from maxicalc.engine.units import Number, ceil_int, d

POROUS_EXTRA = Decimal("0.10")


def liters_by_spread(
    area_m2: Number, spread_m2_per_l: Number, layers: int = 2, porous: bool = False
) -> Calc:
    """Paint: V = A x layers / spread (m2/l per layer); porous base +10%."""
    a, s = d(area_m2), d(spread_m2_per_l)
    if a < 0 or s <= 0 or layers < 1:
        raise ValueError("Некорректные параметры краски")
    v = a * layers / s
    ex = [f"{a} м² × {layers} сл. / {s} м²/л = {v} л"]
    if porous:
        v = v * (1 + POROUS_EXTRA)
        ex.append(f"Пористое основание +10%: {v} л")
    return Calc(v, "л", tuple(ex))


def liters_by_consumption(area_m2: Number, l_per_m2: Number, layers: int = 1) -> Calc:
    a, c = d(area_m2), d(l_per_m2)
    if a < 0 or c <= 0 or layers < 1:
        raise ValueError("Некорректные параметры грунта")
    v = a * c * layers
    return Calc(v, "л", (f"{a} м² × {c} л/м² × {layers} сл. = {v} л",))


def kg_by_thickness(area_m2: Number, thickness_mm: Number, kg_per_m2_per_mm: Number) -> Calc:
    a, t, k = d(area_m2), d(thickness_mm), d(kg_per_m2_per_mm)
    if a < 0 or t <= 0 or k <= 0:
        raise ValueError("Некорректные параметры смеси")
    m = a * t * k
    return Calc(m, "кг", (f"{a} м² × {t} мм × {k} кг/м²/мм = {m} кг",))


def packs(quantity: Number, pack_size: Number) -> Calc:
    q, p = d(quantity), d(pack_size)
    if p <= 0:
        raise ValueError("Некорректная фасовка")
    n = ceil_int(q / p)
    return Calc(Decimal(n), "уп", (f"ceil({q} / {p}) = {n} уп",))
