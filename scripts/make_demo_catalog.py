"""Build a SYNTHETIC demo catalog (CSV) and a trained matching model for load tests / demos.

    uv run python scripts/make_demo_catalog.py --n 10000 --out data/demo_catalog.csv \
        --model data/demo_model.joblib

The data is generated from templates (maxicalc.ml.synth); card texts carry consumption figures
so calculators have inputs. NOT Maxidom data and not a quality benchmark.
"""
import argparse
import csv
import random
import sys
import time
from pathlib import Path

from maxicalc.ml.classify import MatchModel, weak_labels
from maxicalc.ml.synth import SynthItem, generate, split_by_group

# family key -> description text (the engine's inputs live in the card, as on real products)
CARD_TEXT = {
    "paint_wall": "Расход {spread} м2/л в один слой",
    "paint_ceiling": "Расход {spread} м2/л в один слой",
    "primer": "Расход 0,15 л/м2",
    "putty": "Расход 1,1 кг/м2 на 1 мм слоя",
    "plaster": "Расход 8,5 кг/м2 при толщине слоя 10 мм",
    "self_level": "Расход 1,8 кг/м2 на 1 мм слоя",
    "waterproof": "Расход 3,5 кг/м2",
    "laminate": "В упаковке 2,131 м2",
    "spc": "В упаковке 2,2 м2",
    "underlay": "В упаковке 10 м2",
    "tile_floor": "В упаковке 1,44 м2",
    "tile_wall": "В упаковке 1,5 м2",
    "porcelain": "В упаковке 1,44 м2",
}


def price_for(family: str, rnd: random.Random) -> int:
    base = {"paint_wall": 900, "paint_ceiling": 700, "tile_floor": 1100, "laminate": 1700,
            "porcelain": 2200}.get(family, 500)
    return int(base * rnd.uniform(0.5, 2.5))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/demo_catalog.csv")
    ap.add_argument("--model", default="data/demo_model.joblib")
    a = ap.parse_args()
    rnd = random.Random(a.seed)

    items = generate(a.n, seed=a.seed)
    rows: list[SynthItem] = items
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["sku", "name", "category", "brand", "price", "description"])
        for it in rows:
            fam = it.group.split(":")[0]
            desc = CARD_TEXT.get(fam, "").format(spread=rnd.choice([8, 10, 12]))
            p = it.product
            w.writerow([p.sku, p.name, " > ".join(p.category_path), p.brand or "",
                        price_for(fam, rnd), desc])
    print(f"wrote {len(rows)} products to {out}")

    t0 = time.perf_counter()
    train, dev, _ = split_by_group(items, seed=a.seed)
    prods, labels = weak_labels([i.product for i in train])
    model = MatchModel().fit(prods, labels, [i.product for i in dev], [i.gold for i in dev])
    Path(a.model).parent.mkdir(parents=True, exist_ok=True)
    model.save(Path(a.model))
    print(f"trained and saved model to {a.model} in {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
