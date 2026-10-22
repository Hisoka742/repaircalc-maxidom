"""Generate tests/golden/golden_generated.yaml: a few hundred reference cases.

    uv run python scripts/make_golden.py

Every expected value is computed HERE with plain Decimal arithmetic written from the textbook
formulas, importing nothing from `maxicalc.engine`. A deviation therefore shows that the engine
and an independent re-derivation disagree. These cases are NOT manufacturer or organiser
references (`verified: false`); they widen coverage of the formulas and boundaries (rounding,
rapport, doors, small rooms, large formats). Replace/extend with real references via
GOLDEN_EXTRA once the organisers provide them.
"""
import random
from decimal import Decimal as D
from math import ceil, floor
from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parents[1] / "tests" / "golden" / "golden_generated.yaml"
rnd = random.Random(20261014)
cases: list[dict[str, object]] = []


def add(cid: str, calc: str, kind: str, inputs: dict[str, object], expected: object,
        source: str) -> None:
    cases.append({"id": cid, "calc": calc, "kind": kind, "inputs": inputs,
                  "expected": expected if isinstance(expected, int) else str(expected),
                  "source": source, "verified": False})


def ceil_d(x: D) -> int:
    return ceil(x)   # note: Decimal `//` truncates toward zero, it is not a floor


def num(lo: float, hi: float, step: float = 0.1) -> D:
    n = round((hi - lo) / step)
    return D(str(round(lo + rnd.randint(0, n) * step, 3)))


# ---- paint: V = A x layers / spread (+10% porous) ----------------------------------------
SRC_PAINT = "независимый пересчёт: V = S × слоёв / расход (м²/л на слой), пористое +10%"
for i in range(28):
    area, spread = num(5, 120, 0.5), num(6, 14, 0.5)
    layers, porous = rnd.choice([1, 2, 2, 3]), rnd.random() < 0.3
    v = area * layers / spread * (D("1.1") if porous else 1)
    add(f"gen-paint-{i:03d}", "paint_liters", "continuous",
        {"area": str(area), "spread": str(spread), "layers": layers, "porous": porous}, v,
        SRC_PAINT)

# ---- mixes by thickness: m = A x t x rate -----------------------------------------------------
for i in range(16):
    area, t, rate = num(4, 80, 0.5), D(rnd.choice([1, 2, 3, 5, 10, 20])), num(0.8, 2.0, 0.1)
    add(f"gen-layer-{i:03d}", "layer_kg", "continuous",
        {"area": str(area), "thickness_mm": str(t), "rate": str(rate)}, area * t * rate,
        "независимый пересчёт: m = S × толщина, мм × расход, кг/м²/мм")

for i in range(16):
    area, t, rate = num(4, 80, 0.5), D(rnd.choice([1, 2, 3])), num(0.9, 1.5, 0.1)
    bag = D(rnd.choice([5, 20, 25, 30]))
    add(f"gen-putty-{i:03d}", "putty_bags", "pack",
        {"area": str(area), "thickness_mm": str(t), "rate": str(rate), "bag_kg": str(bag)},
        ceil_d(area * t * rate / bag),
        "независимый пересчёт: ceil(S × t × расход / фасовка)")

# ---- laminate: ceil(A x (1 + waste) / pack) ----------------------------------------------
WASTE = {"straight": D("0.07"), "diagonal": D("0.12"), "herringbone": D("0.15")}
for i in range(20):
    area, pack = num(5, 90, 0.5), num(1.5, 3.0, 0.001)
    layout = rnd.choice(list(WASTE))
    add(f"gen-lam-{i:03d}", "laminate_packs", "pack",
        {"area": str(area), "m2_per_pack": str(pack), "layout": layout},
        ceil_d(area * (1 + WASTE[layout]) / pack),
        "независимый пересчёт: ceil(S × (1 + запас раскладки) / м² в упаковке)")

# ---- tile packs: waste by layout + small room + large format -----------------------------------
for i in range(24):
    area = rnd.choice([num(1.5, 3.9, 0.1), num(4, 60, 0.5)])
    w, h = D(rnd.choice([200, 300, 330, 400, 450, 600, 600, 800])), D(rnd.choice([200, 300, 330,
                                                                                   600, 1200]))
    layout = rnd.choice(list(WASTE))
    k = WASTE[layout] + (D("0.03") if area < 4 else 0) + (D("0.03") if max(w, h) >= 600 else 0)
    pack = num(0.9, 2.2, 0.01)
    add(f"gen-tile-{i:03d}", "tile_packs", "pack",
        {"area": str(area), "layout": layout, "tile_w": str(w), "tile_h": str(h),
         "m2_per_pack": str(pack)},
        ceil_d(area * (1 + k) / pack),
        "независимый пересчёт: ceil(S × (1 + запас) / м² в упаковке); запас: раскладка + 3% при "
        "S < 4 м² + 3% при стороне ≥ 600 мм")

# ---- grout: kg = A x (a + b)/(a x b) x c x j x rho ------------------------------------------
for i in range(16):
    area = num(2, 40, 0.5)
    a, b = D(rnd.choice([200, 300, 450, 600])), D(rnd.choice([200, 300, 600, 1200]))
    c, j = D(rnd.choice([6, 8, 9, 10])), D(rnd.choice([2, 3, 4, 5]))
    q = (a + b) * c * j * D("1.6") / (a * b)
    add(f"gen-grout-{i:03d}", "grout_kg", "continuous",
        {"area": str(area), "tile_w": str(a), "tile_h": str(b), "thickness": str(c),
         "joint": str(j)}, area * q,
        "независимый пересчёт: q = (A+B)/(A·B) × C × D × ρ, ρ = 1,6 кг/дм³ (Ceresit/Litokol)")

# ---- tile adhesive: card rate or table by largest side ---------------------------------------
TABLE = [(50, D("1.7")), (100, D("2.0")), (150, D("2.7")), (250, D("3.6")), (300, D("4.2")),
         (10**6, D("5.5"))]
for i in range(14):
    area = num(2, 40, 0.5)
    a, b = D(rnd.choice([100, 150, 200, 300, 450, 600])), D(rnd.choice([100, 200, 300, 600]))
    if rnd.random() < 0.4:
        rate = num(3, 6, 0.1)
        add(f"gen-adh-{i:03d}", "adhesive_kg", "continuous",
            {"area": str(area), "tile_w": str(a), "tile_h": str(b), "kg_per_m2": str(rate)},
            area * rate, "независимый пересчёт: S × расход из карточки")
    else:
        side = max(a, b)
        rate = next(r for lim, r in TABLE if side <= lim)
        add(f"gen-adh-{i:03d}", "adhesive_kg", "continuous",
            {"area": str(area), "tile_w": str(a), "tile_h": str(b)}, area * rate,
            "независимый пересчёт: S × норма по таблице Ceresit CM 11 (по большей стороне)")

# ---- waterproofing: Ceresit CR 65 ---------------------------------------------------------
CR65 = {"high_humidity": D("3.5"), "water_no_pressure": D("4.5"), "water_pressure": D("6.0")}
for i in range(9):
    area, cond = num(3, 50, 0.5), rnd.choice(list(CR65))
    add(f"gen-wp-{i:03d}", "waterproofing_kg", "continuous",
        {"area": str(area), "condition": cond}, area * CR65[cond],
        "независимый пересчёт: S × расход по условиям эксплуатации (Ceresit CR 65)")

# ---- wallpaper: strips per wall / strips per roll ----------------------------------------------
for i in range(26):
    L, W, H = num(2.5, 7, 0.1), num(2, 5, 0.1), D(rnd.choice(["2.4", "2.5", "2.6", "2.7", "3.0"]))
    rw, rl = D(rnd.choice(["0.53", "1.06"])), D(rnd.choice(["10.05", "15", "25"]))
    rap = D(rnd.choice(["0", "0", "0.32", "0.64"]))
    reserve = rnd.choice([0, 0, 1])
    doors = [{"kind": "door", "w": "0.9", "h": "2.05", "wall": rnd.randrange(4)}
             for _ in range(rnd.choice([0, 1, 2]))]
    walls = [L, W, L, W]
    net = list(walls)
    for dr in doors:
        net[dr["wall"]] -= D("0.9")  # type: ignore[index]
    if any(n <= 0 for n in net):
        continue
    strip = H + D("0.1")
    if rap > 0:
        strip = ceil_d(strip / rap) * rap
    per_roll = floor(rl / strip)
    if per_roll < 1:
        continue
    strips = sum(ceil_d(n / rw) for n in net)
    inputs: dict[str, object] = {"length": str(L), "width": str(W), "height": str(H),
                                 "roll_width": str(rw), "roll_length": str(rl),
                                 "rapport": str(rap), "reserve": reserve, "openings": doors}
    add(f"gen-wp2-{i:03d}", "wallpaper_rolls", "pack", inputs,
        ceil_d(D(strips) / per_roll) + reserve,
        "независимый пересчёт: полотен по стенам = ceil(чистая ширина / ширина рулона); "
        "полотен в рулоне = floor(длина рулона / длина полотна); длина полотна = H + 0,1 м, "
        "округлена вверх до раппорта")

# ---- skirting: ceil((perimeter - doors) x 1.05 / piece) ------------------------------------
for i in range(14):
    L, W, H = num(2, 8, 0.1), num(2, 6, 0.1), D("2.5")
    nd = rnd.choice([0, 1, 2])
    doors = [{"kind": "door", "w": "0.9", "h": "2.05", "wall": rnd.randrange(4)}
             for _ in range(nd)]
    ln = 2 * (L + W) - D("0.9") * nd
    piece = D(rnd.choice(["2.2", "2.5", "2.7"]))
    add(f"gen-skirt-{i:03d}", "skirting_pieces", "pack",
        {"length": str(L), "width": str(W), "height": str(H), "piece_len": str(piece),
         "openings": doors}, ceil_d(ln * D("1.05") / piece),
        "независимый пересчёт: ceil((периметр − двери) × 1,05 / длина планки)")


# ---- pack optimiser: brute-force minimum cost to cover the requirement -----------------------
def brute(req: D, packs: list[tuple[D, D]]) -> D:
    best: D | None = None
    caps = [ceil(req / s) + 1 for s, _ in packs]

    def rec(i: int, size: D, cost: D) -> None:
        nonlocal best
        if best is not None and cost >= best:
            return
        if i == len(packs):
            if size >= req and (best is None or cost < best):
                best = cost
            return
        for n in range(caps[i] + 1):
            rec(i + 1, size + packs[i][0] * n, cost + packs[i][1] * n)

    rec(0, D(0), D(0))
    assert best is not None
    return best


for i in range(12):
    req = num(3, 40, 0.5)
    base = [(D("2.5"), D(1000)), (D(5), D(1750)), (D(9), D(3000)), (D(10), D(3200))]
    packs = rnd.sample(base, rnd.choice([2, 3]))
    add(f"gen-pack-{i:03d}", "pack_cost", "continuous",
        {"required": str(req),
         "packs": [{"sku": f"S{k}", "size": str(s), "price": str(p)}
                   for k, (s, p) in enumerate(packs)]},
        brute(req, packs), "независимый перебор: минимальная стоимость покрытия требуемого объёма")

# write
data = {"cases": cases}
header = ("# GENERATED by scripts/make_golden.py -- do not edit by hand.\n"
          "# Independent re-derivations (verified: false); see the generator's docstring.\n")
OUT.write_text(header + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=100),
               encoding="utf-8")
print(f"wrote {len(cases)} cases to {OUT}")
