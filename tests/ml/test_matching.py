import pytest

from maxicalc.catalog.schema import Product
from maxicalc.ml.calibrate import pick_threshold
from maxicalc.ml.metrics import coverage_at_precision, multilabel_scores
from maxicalc.ml.rules import apply_rules
from maxicalc.ml.taxonomy import load_taxonomy


def prod(name: str, cat: str = "", desc: str = "", chars: dict[str, str] | None = None) -> Product:
    return Product(sku="1", name=name, category_path=[x.strip() for x in cat.split(">") if x],
                   description=desc, characteristics=chars or {})


# ---------- taxonomy ----------
def test_taxonomy_is_consistent() -> None:
    t = load_taxonomy()
    assert {"floor_finish", "wall_finish_wallpaper", "waterproofing", "drywall",
            "electrical"} <= set(t.work_categories)
    assert {"bathroom", "kitchen", "kids", "balcony", "hallway", "living", "bedroom",
            "any"} == set(t.room_types)
    assert {"wallpaper", "paint", "tile", "tile_adhesive", "grout", "laminate",
            "skirting", "none"} <= set(t.calc_templates)
    assert all(v for v in t.work_categories.values()), "every label needs a description"


# ---------- rules ----------
@pytest.mark.parametrize(("name", "cat", "work", "calc"), [
    ("Обои флизелиновые 1,06х10,05 м", "Обои > Флизелиновые", "wall_finish_wallpaper", "wallpaper"),
    ("Клей для обоев Метилан 250 г", "Обои > Клей для обоев", "wall_finish_wallpaper",
     "wallpaper_glue"),
    ("Краска водоэмульсионная 2,5 л", "Краски", "wall_finish_paint", "paint"),
    ("Клей плиточный Ceresit CM 11, 25 кг", "Плитка > Клей для плитки", "wall_tile",
     "tile_adhesive"),
    ("Затирка цементная 2 кг", "Плитка > Затирки", "wall_tile", "grout"),
    ("Ламинат 33 класс 8 мм", "Напольные покрытия > Ламинат", "floor_finish", "laminate"),
    ("Плинтус напольный 2,5 м", "Плинтусы", "floor_finish", "skirting"),
    ("Смесь самовыравнивающаяся 25 кг", "Строительные смеси > Наливные полы", "floor_prep",
     "self_leveling"),
    ("Гидроизоляция обмазочная 15 кг", "Строительные смеси > Гидроизоляция", "waterproofing",
     "waterproofing"),
    ("Гипсокартон ГКЛ 12,5 мм", "Гипсокартон", "drywall", "drywall"),
    ("Розетка двойная", "Электротовары > Розетки", "electrical", "electrical"),
])
def test_rules_assign_work_and_calc(name: str, cat: str, work: str, calc: str) -> None:
    r = apply_rules(prod(name, cat))
    assert work in r.work_categories
    assert r.calc_template is not None and r.calc_template.label == calc


def test_rules_properties_and_rooms() -> None:
    r = apply_rules(prod("Розетка IP44", "Электротовары > Розетки"))
    assert "moisture_resistant" in r.properties
    r2 = apply_rules(prod("Краска для детской комнаты", "Краски", desc="Класс эмиссии E1"))
    assert "kids" in r2.room_types and "low_emission" in r2.properties
    r3 = apply_rules(prod("Ламинат 33 класс", "Напольные покрытия > Ламинат"))
    assert "wear_class_33" in r3.properties
    r4 = apply_rules(prod("Плитка для ванной и санузла", "Плитка"))
    assert "bathroom" in r4.room_types


def test_rules_silent_on_unknown() -> None:
    r = apply_rules(prod("Ceresit CM 11 PRO 25 кг"))
    assert r.calc_template is None and not r.work_categories


def test_rules_report_reason() -> None:
    r = apply_rules(prod("Обои", "Обои"))
    assert r.calc_template is not None and r.calc_template.reason


def test_name_and_category_conflict_is_flagged() -> None:
    # store put a wallpaper glue under "Краски"
    r = apply_rules(prod("Клей для обоев Метилан", "Краски"))
    assert r.conflict


# ---------- calibration ----------
def test_pick_threshold_lowest_meeting_precision() -> None:
    probs = [0.99, 0.98, 0.97, 0.9, 0.85, 0.5, 0.4]
    y = [1, 1, 1, 1, 0, 0, 0]
    assert pick_threshold(probs, y, target=0.95, min_support=3) == 0.9


def test_pick_threshold_unreachable_returns_none() -> None:
    assert pick_threshold([0.9, 0.8, 0.7, 0.6], [0, 1, 0, 1], target=0.95, min_support=2) is None


def test_pick_threshold_respects_min_support() -> None:
    # precision is 1.0 only at the top item, but support 1 < min_support 3
    assert pick_threshold([0.99, 0.6, 0.5, 0.4], [1, 0, 0, 0], target=0.95, min_support=3) is None


# ---------- metrics ----------
def test_multilabel_scores_exact() -> None:
    gold = [{"x"}, {"x", "y"}, {"y"}]
    pred = [{"x"}, {"x"}, {"x", "y"}]
    s = multilabel_scores(gold, pred)
    assert s.per_label["x"].precision == pytest.approx(2 / 3)
    assert s.per_label["x"].recall == pytest.approx(1.0)
    assert s.per_label["y"].precision == pytest.approx(1.0)
    assert s.per_label["y"].recall == pytest.approx(0.5)
    assert s.macro_f1 == pytest.approx((0.8 + 2 / 3) / 2)
    assert s.micro_f1 == pytest.approx(0.75)


def test_coverage_at_precision() -> None:
    auto = [True, True, True, False, False]
    correct = [True, True, False, True, False]
    cov, prec = coverage_at_precision(auto, correct)
    assert cov == pytest.approx(3 / 5)
    assert prec == pytest.approx(2 / 3)
    assert coverage_at_precision([False], [True]) == (0.0, 1.0)
