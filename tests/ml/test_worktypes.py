"""Work-type rules, metrics, and the gold-set tooling (on synthetic fixtures, not real labels)."""
import csv
import importlib.util
import sys
from decimal import Decimal as D
from pathlib import Path

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.worktype_eval import (
    average_precision,
    evaluate_sets,
    name_has_keyword,
    ndcg,
    non_literal_pairs,
    ranking_report,
)
from maxicalc.ml.worktypes import WorkMatcher, WorkModel, load_rules, rule_labels, work_type_ids

ROOT = Path(__file__).resolve().parents[2] / "scripts"


def prod(name: str, *cat: str, sku: str = "1") -> Product:
    return Product(sku=sku, name=name, category_path=list(cat), price=D(1))


def test_taxonomy_has_42_work_types_with_stages_and_rules_are_valid() -> None:
    assert len(work_type_ids()) == 42
    assert len(load_rules()) > 100


def test_primer_maps_to_every_work_it_serves_with_roles() -> None:
    lab = rule_labels(prod("грунтовка акриловая 5л", "Краска и малярный инструмент",
                           "Грунты, пропитки, олифы", "Грунтовка"))
    assert lab["priming"][0] == "m"
    for w in ("wall_painting", "tile_laying", "wallpapering", "puttying"):
        assert lab[w][0] == "c"


def test_tool_and_consumable_roles() -> None:
    roller = rule_labels(prod("валик 250мм", "Краска и малярный инструмент",
                              "Малярно-штукатурный инструмент", "Валики"))
    tape = rule_labels(prod("лента малярная", "Краска и малярный инструмент",
                            "Малярно-штукатурный инструмент", "Ленты малярные, клейкие"))
    assert roller["wall_painting"][0] == "t" and tape["wall_painting"][0] == "c"


def test_product_outside_repair_scope_gets_no_work() -> None:
    assert rule_labels(prod("кувшин 1л", "Посуда", "Кувшины")) == {}


def test_metrics_hand_computed() -> None:
    gold = [{"a", "b"}, {"a"}, set()]
    pred = [{"a"}, {"a", "c"}, set()]
    r = evaluate_sets(gold, pred, ["a", "b", "c"])
    # tp=2 (a,a), fp=1 (c), fn=1 (b): micro-F1 = 2*2/(4+1+1)
    assert r.micro_f1 == pytest.approx(4 / 6)
    assert r.hamming_loss == pytest.approx(2 / 9)
    assert r.exact_match == pytest.approx(1 / 3)
    assert r.samples_f1 == pytest.approx((2 * 1 / 3 + 2 * 1 / 3 + 1) / 3)
    assert r.per_class["a"].f1 == 1.0 and r.per_class["b"].recall == 0.0


def test_ranking_metrics() -> None:
    assert average_precision([True, False, True], 3) == pytest.approx((1 + 2 / 3) / 2)
    assert ndcg([True, False, True], 3, 2) == pytest.approx((1 + 0.5) / (1 + 1 / 1.5849625))
    gold = [{"w"}, set(), {"w"}, {"w"}, set()]
    rep = ranking_report(gold, {"w": [0.9, 0.1, 0.8, 0.7, 0.2]}, k=3, min_pos=3)
    assert rep.map_at_k == 1.0 and rep.ndcg_at_k == 1.0


def test_non_literal_pairs_ignore_named_matches() -> None:
    products = [prod("краска белая", "x"), prod("матовая эмульсия", "x")]
    gold = [{"wall_painting"}, {"wall_painting"}]
    pred = [{"wall_painting"}, set()]
    assert name_has_keyword(products[0], "wall_painting") and not name_has_keyword(
        products[1], "wall_painting")
    s = non_literal_pairs(products, gold, pred)
    assert (s.tp, s.fp, s.fn) == (0, 0, 1)         # only the second product counts


def test_model_learns_a_text_pattern_and_review_band_works() -> None:
    train, labels = [], []
    for i in range(40):
        train.append(prod(f"плитка керамическая {i}", "Плитка", "Плитка для ванной", sku=f"t{i}"))
        labels.append({"tile_laying"})
        train.append(prod(f"краска акриловая {i}", "Краска", "Краски для стен", sku=f"p{i}"))
        labels.append({"wall_painting"})
    m = WorkModel().fit(train, labels)
    out = WorkMatcher(m, use_rules=False).predict(
        [prod("плитка настенная 20х30", "Плитка"), prod("краска матовая", "Краска")])
    assert "tile_laying" in out[0].works and "wall_painting" in out[1].works


def _load(name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def test_merge_computes_agreement_and_majority_gold(tmp_path: Path) -> None:
    cols = ["sku", "name", "category", "description", "params", "suggested", "work_types",
            "group", "split", "overlap"]

    def write(k: int, rows: list[list[str]]) -> None:
        with (tmp_path / f"worktype_annotator{k}.csv").open("w", encoding="utf-8-sig",
                                                            newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(cols)
            w.writerows(rows)

    def row(sku: str, wt: str, overlap: str = "1", sugg: str = "") -> list[str]:
        return [sku, "n", "c", "", "", sugg, wt, "stratified", "dev", overlap]

    ov = [f"s{i}" for i in range(12)]
    pattern = ["tile_laying", "priming", "none", "grouting"] * 3
    for k in (1, 2, 3):
        write(k, [row(s, pattern[i]) for i, s in enumerate(ov)]
              + ([row("u1", "=", "0", "wall_painting;priming")] if k == 1 else []))
    # annotator 3 disagrees on one cell of the first row
    rows3 = [row(s, pattern[i]) for i, s in enumerate(ov)]
    rows3[0] = row("s0", "tile_laying;grouting")
    write(3, rows3)
    mod = _load("merge_worktype_gold")
    sys.argv = ["x", "--dir", str(tmp_path)]
    assert mod.main() == 0
    gold = list(csv.DictReader((tmp_path / "worktype_gold.csv").read_text(
        encoding="utf-8-sig").splitlines(), delimiter=";"))
    by = {g["sku"]: g["works"] for g in gold}
    assert by["s0"] == "tile_laying"              # 2 of 3 say tile only: majority
    assert by["u1"] == "priming;wall_painting"    # "=" accepted the suggestion
    text = (tmp_path / "AGREEMENT.md").read_text(encoding="utf-8")
    assert "Krippendorff" in text and "Cohen" in text


def test_rug_mat_is_not_laminate_underlay() -> None:
    from maxicalc.catalog.schema import Product
    from maxicalc.ml.rules import apply_rules

    p = Product(sku="1", name="подложка под ковер ВИЛИНА противоскользящая 60х120см",
                category_path=["Напольные покрытия", "Подложки"])
    assert apply_rules(p).calc_template.label == "none"   # type: ignore[union-attr]
    q = Product(sku="2", name="подложка под ламинат 3мм 1,05х10м",
                category_path=["Напольные покрытия", "Подложки"])
    assert apply_rules(q).calc_template.label == "underlay"   # type: ignore[union-attr]


def _prod(name: str, cat: str, desc: str = "") -> Product:
    return Product(sku=name, name=name, category_path=cat.split(" > "), description=desc,
                   price=D(1))


def test_policy_ppe_is_its_own_work_type() -> None:
    p = _prod("перчатки усиленные HONEYWELL",
              "Электроинструмент > Средства защиты > Перчатки, рукавицы")
    assert set(rule_labels(p)) == {"ppe_consumables"}


def test_policy_primer_walls_only_unless_card_says_floor() -> None:
    cat = "Краска и малярный инструмент > Грунты, пропитки, олифы > Грунтовка"
    wall = set(rule_labels(_prod("грунт акриловый для стен 5л", cat)))
    assert "screed" not in wall and "self_leveling" not in wall and "wall_painting" in wall
    floor = set(rule_labels(_prod("грунт акриловый 5л", cat, "Грунт для пола и оснований")))
    assert {"screed", "self_leveling"} <= floor
    universal = set(rule_labels(_prod("грунт универсальный 10л", cat)))
    assert "screed" in universal


def test_policy_decorative_profiles_and_moldings_are_skirting() -> None:
    p = _prod("профиль алюминиевый П-образный 10х10",
              "Скобяные изделия > Профили > Профили П-образные")
    assert set(rule_labels(p)) == {"skirting_install"}
