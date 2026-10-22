"""Product role head and routing of accessories away from the main calculator pool."""
from decimal import Decimal as D

from maxicalc.catalog.schema import Product
from maxicalc.ml.readiness import readiness_report
from maxicalc.ml.roles import product_role
from maxicalc.ml.rules import apply_rules
from maxicalc.recommend.companions import pick_companions
from maxicalc.recommend.select import CatalogEntry, recommend


def prod(name: str, cat: str) -> Product:
    return Product(sku=name, name=name, category_path=cat.split(" > "), price=D(100))


def test_roles_by_family() -> None:
    cases = {
        ("профиль потолочный 3000х27х60х0,6мм",
         "Строительные материалы > Гипсокартон > Профили и аксессуары для гипсокартона"):
            "accessory",
        ("гипсокартон ГКЛ 12.5мм 2500х1200", "Строительные материалы > Гипсокартон > Гипсокартон"):
            "main",
        ("перчатки нейлон 2 пары", "Электроинструмент > Средства защиты > Перчатки, рукавицы"):
            "ppe",
        ("сверло по металлу 8х117", "Электроинструмент > Расходные материалы > Свёрла"):
            "consumable",
        ("шпатель малярный 100мм", "Краска и малярный инструмент > Шпатели"): "tool",
        ("крестики для плитки 2мм", "Плитка > Системы выравнивания плитки"): "consumable",
    }
    for (name, cat), want in cases.items():
        assert product_role(prod(name, cat)).role == want, name


def test_accessory_is_not_main_product_of_a_calculator() -> None:
    sheet = CatalogEntry(prod("гипсокартон ГКЛ 12.5мм", "Строительные материалы > Гипсокартон"),
                         work=set(), rooms={"any"}, props=set(), calc="drywall",
                         attrs={"thickness_mm": D("12.5")}, role="main")
    prof = CatalogEntry(prod("профиль ПН 27х28", "Строительные материалы > Профили"),
                        work=set(), rooms={"any"}, props=set(), calc="drywall", role="accessory")
    res = recommend([sheet, prof], "living", calc="drywall")
    assert [c.entry.product.sku for c in res.items] == [sheet.product.sku]
    comp = pick_companions([prof], [])
    assert comp and comp[0].entry.role == "accessory"
    rep = readiness_report([sheet, prof])
    assert rep["drywall"].total == 1          # the profile is not counted


def test_underfloor_heating_is_not_a_tile() -> None:
    p = prod("мат нагревательный 150Вт", "Плитка > Теплый пол под плитку")
    assert apply_rules(p).calc_template.label == "none"   # type: ignore[union-attr]
