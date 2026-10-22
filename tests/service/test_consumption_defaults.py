"""Resolution order: fact -> LLM-inferred >= threshold -> brand+type default -> type default."""
from decimal import Decimal as D

import pytest

from maxicalc.catalog.schema import Product
from maxicalc.engine.geometry import Room
from maxicalc.recommend.defaults import default_for
from maxicalc.recommend.inferred import effective_entry
from maxicalc.recommend.select import CatalogEntry, Inferred
from maxicalc.service.property_calc import calc_room


def prod(name: str, brand: str | None = None) -> Product:
    return Product(sku="S", name=name, brand=brand, price=D(100))


def entry(name: str, calc: str, brand: str | None = None, attrs: dict | None = None,  # type: ignore[type-arg]
          inferred: dict | None = None) -> CatalogEntry:  # type: ignore[type-arg]
    return CatalogEntry(prod(name, brand), work=set(), rooms={"any"}, props=set(), calc=calc,
                        status="verified", attrs=attrs or {}, inferred=inferred or {})


def test_brand_type_beats_type_and_cites_the_source() -> None:
    h = default_for(prod("краска акриловая Harmony матовая 9л", "TIKKURILA"), "paint")
    assert h and h.level == "brand+type" and h.value == D(8) and "harmony" in h.url
    t = default_for(prod("краска акриловая матовая 9л", "NONAME"), "paint")
    assert t and t.level == "type" and t.value == D(8)


def test_ceiling_paint_uses_the_ceiling_figure() -> None:
    h = default_for(prod("краска акриловая для потолков белая 5л", "PARADE"), "paint")
    assert h and h.type_id == "wall_paint_ceiling" and h.value == D(7)


def test_gypsum_vs_polymer_vs_plaster_putty() -> None:
    g = default_for(prod("шпатлевка гипсовая финишная 20кг", "KNAUF"), "putty")
    assert g and g.value == D("1.0")
    v = default_for(prod("шпатлевка полимерная Vetonit LR+ 25кг", "VETONIT"), "putty")
    assert v and v.value == D("1.2")
    plaster = default_for(prod("штукатурка гипсовая Ротбанд 30кг", "KNAUF"), "putty")
    assert plaster and plaster.type_id == "plaster_gypsum"


def test_unknown_type_gets_no_default() -> None:
    assert default_for(prod("эмаль алкидная ПФ-115 белая 1кг", "ЛАКРА"), "paint") is None
    assert default_for(prod("шпатлевка по дереву дуб", "ТЕКС"), "putty") is None


def test_fact_beats_inferred_beats_default() -> None:
    p = "краска акриловая матовая 9л"
    fact = entry(p, "paint", attrs={"spread_m2_per_l": D(13)})
    eff, notes, _ = effective_entry(fact, "low")
    assert eff.attrs["spread_m2_per_l"] == D(13) and not notes
    inf = entry(p, "paint", inferred={"spread_m2_per_l": Inferred(D(10), "medium", "10 м2/л")})
    eff, notes, _ = effective_entry(inf, "medium")
    assert eff.attrs["spread_m2_per_l"] == D(10) and "получено моделью" in notes[0]
    held = entry(p, "paint", inferred={"spread_m2_per_l": Inferred(D(10), "low", "10 м2/л")})
    eff, notes, _ = effective_entry(held, "medium")
    assert eff.attrs["spread_m2_per_l"] == D(8) and "по умолчанию" in notes[-1]


def test_room_calc_says_a_default_was_used(monkeypatch: pytest.MonkeyPatch) -> None:
    e = entry("краска акриловая для потолков 5л", "paint", "PARADE",
              attrs={"pack_volume_l": D("5")})
    est = calc_room(Room.rectangle(4, 3, "2.5"), "living", "cosmetic", [e])
    line = next(ln for ln in est.basket.lines if ln.sku == "S")
    assert any("по умолчанию" in x and "Nova_2" in x for x in line.explain)
