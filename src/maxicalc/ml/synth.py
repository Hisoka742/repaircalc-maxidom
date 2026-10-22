"""Synthetic repair-catalog generator for developing and testing the matching pipeline.

NOT real data. Every product is built from a template family, so any metric computed on it
measures the machinery (rules, classifier, calibration, review routing), not real-world quality.
Difficulty is injected on purpose: brands shared between families, 'keyword-free' names with no
category words, and ~7% wrong store categories.
"""
import random
from dataclasses import dataclass, field

from maxicalc.catalog.schema import Product


@dataclass(frozen=True)
class Labels:
    work: set[str]
    rooms: set[str]
    props: set[str]
    calc: str


@dataclass(frozen=True)
class SynthItem:
    product: Product
    gold: Labels
    group: str
    miscategorised: bool
    keyword_free: bool


@dataclass(frozen=True)
class Special:
    """Optional text variant that adds visible properties / room types."""

    suffix: str
    rooms: frozenset[str] = frozenset()
    props: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Family:
    key: str
    calc: str
    works: frozenset[str]
    category: str
    kw: str          # keyword name template: {b} brand, {m} model, {s} size
    keyless: str     # name template without category words
    brands: tuple[str, ...]
    prefix: str
    sizes: tuple[str, ...]
    specials: tuple[Special, ...] = ()
    size_props: dict[str, frozenset[str]] = field(default_factory=dict)


def _f(*a: str) -> frozenset[str]:
    return frozenset(a)


FAMILIES: tuple[Family, ...] = (
    Family("wp_vinyl", "wallpaper", _f("wall_finish_wallpaper"), "Обои > Виниловые",
           "Обои виниловые {b} {m} {s}", "{b} {m} {s}", ("Erismann", "Rasch", "Marburg"), "WV",
           ("1,06х10,05 м", "0,53х10,05 м"),
           (Special(" для кухни", _f("kitchen")), Special(" моющиеся", props=_f("washable")),
            Special(" без запаха", props=_f("low_emission")))),
    Family("wp_glue", "wallpaper_glue", _f("wall_finish_wallpaper"), "Обои > Клей для обоев",
           "Клей для обоев {b} {m} {s}", "{b} {m} {s}", ("Metylan", "Quelyd", "Pufas"), "WG",
           ("250 г", "500 г")),
    Family("paint_wall", "paint", _f("wall_finish_paint"), "Краски > Водоэмульсионные",
           "Краска {b} {m} {s}", "{b} {m} {s}", ("Dulux", "Tikkurila", "Caparol"), "PW",
           ("0,9 л", "2,5 л", "9 л"),
           (Special(" для детской", _f("kids")), Special(" без запаха", props=_f("low_emission")),
            Special(" моющаяся", props=_f("washable")),
            Special(" морозостойкая", props=_f("frost_resistant")),
            Special(" моющаяся влагостойкая", props=_f("washable", "moisture_resistant")))),
    Family("paint_ceiling", "paint", _f("wall_finish_paint", "ceiling"),
           "Краски > Для потолков", "Краска для потолков {b} {m} {s}", "{b} {m} {s} потолок",
           ("Dulux", "Tikkurila", "Parade"), "PC", ("2,5 л", "9 л")),
    Family("primer", "primer", _f("wall_prep"), "Строительные смеси > Грунтовки",
           "Грунтовка {b} {m} {s}", "{b} {m} {s} грунт", ("Ceresit", "Knauf", "Optimist"), "PR",
           ("5 л", "10 л"), (Special(" морозостойкая", props=_f("frost_resistant")),)),
    Family("putty", "putty", _f("wall_prep"), "Строительные смеси > Шпатлевки",
           "Шпатлевка финишная {b} {m} {s}", "{b} {m} {s} финиш", ("Vetonit", "Knauf", "Sheetrock"),
           "PT", ("5 кг", "20 кг", "25 кг")),
    Family("plaster", "putty", _f("wall_prep"), "Строительные смеси > Штукатурки",
           "Штукатурка гипсовая {b} {m} {s}", "{b} {m} {s} гипс", ("Knauf", "Volma", "Ceresit"),
           "PL", ("25 кг", "30 кг")),
    Family("tile_floor", "tile", _f("floor_finish"), "Плитка > Напольная",
           "Плитка напольная {b} {m} {s}", "{b} {m} {s} пол", ("Kerama Marazzi", "Cersanit", "Gracia"),
           "TF", ("33x33 см", "40x40 см", "60x60 см"),
           (Special(" противоскользящая R10", props=_f("anti_slip")),
            Special(" для ванной", _f("bathroom")))),
    Family("tile_wall", "tile", _f("wall_tile"), "Плитка > Настенная",
           "Плитка настенная {b} {m} {s}", "{b} {m} {s} стена", ("Kerama Marazzi", "Cersanit", "Axima"),
           "TW", ("20x30 см", "25x40 см"), (Special(" для ванной", _f("bathroom")),)),
    Family("porcelain", "tile", _f("floor_finish", "wall_tile"), "Плитка > Керамогранит",
           "Керамогранит {b} {m} {s}", "{b} {m} {s} матовый", ("Italon", "Estima", "Kerama Marazzi"),
           "PG", ("60x60 см", "120x60 см")),
    Family("tile_adhesive", "tile_adhesive", _f("wall_tile", "floor_finish"),
           "Плитка > Клей для плитки", "Клей плиточный {b} {m} {s}", "{b} {m} {s} клей",
           ("Ceresit", "Knauf", "Litokol"), "TA", ("5 кг", "25 кг"),
           (Special(" морозостойкий", props=_f("frost_resistant")),)),
    Family("grout", "grout", _f("wall_tile", "floor_finish"), "Плитка > Затирки",
           "Затирка цементная {b} {m} {s}", "{b} {m} {s} шов", ("Ceresit", "Litokol", "Mapei"),
           "GR", ("2 кг", "5 кг"), (Special(" морозостойкая", props=_f("frost_resistant")),)),
    Family("laminate", "laminate", _f("floor_finish"), "Напольные покрытия > Ламинат",
           "Ламинат {b} {m} {s}", "{b} {m} {s} доска", ("Tarkett", "Quick-Step", "Kronospan"),
           "LM", ("32 класс 1292x194x8 мм", "33 класс 1380x193x8 мм"),
           size_props={"32 класс 1292x194x8 мм": _f("wear_class_32"),
                       "33 класс 1380x193x8 мм": _f("wear_class_33")}),
    Family("spc", "laminate", _f("floor_finish"), "Напольные покрытия > SPC",
           "Кварцвиниловая плитка SPC {b} {m} {s}", "{b} {m} {s} кварц", ("Alpine Floor", "Tarkett"),
           "SP", ("34 класс 1220x180x4 мм",), size_props={"34 класс 1220x180x4 мм": _f("wear_class_34")}),
    Family("underlay", "underlay", _f("floor_prep"), "Напольные покрытия > Подложка",
           "Подложка под ламинат {b} {m} {s}", "{b} {m} {s} рулон", ("Isoplaat", "Tarkett", "Solid"),
           "UL", ("3 мм", "5 мм")),
    Family("skirting", "skirting", _f("floor_finish"), "Плинтусы > Напольные",
           "Плинтус напольный {b} {m} {s}", "{b} {m} {s} профиль", ("Идеал", "Wimar", "Salag"),
           "SK", ("2,5 м", "2,2 м")),
    Family("self_level", "self_leveling", _f("floor_prep"), "Строительные смеси > Наливные полы",
           "Наливной пол {b} {m} {s}", "{b} {m} {s} ровнитель", ("Ceresit", "Knauf", "Vetonit"),
           "SL", ("20 кг", "25 кг")),
    Family("waterproof", "waterproofing", _f("waterproofing"),
           "Строительные смеси > Гидроизоляция", "Гидроизоляция обмазочная {b} {m} {s}",
           "{b} {m} {s} эластик", ("Ceresit", "Knauf", "Litokol"), "WP", ("5 кг", "15 кг", "25 кг"),
           (Special(" для ванной комнаты", _f("bathroom")),)),
    Family("gkl", "drywall", _f("drywall"), "Гипсокартон > Листы",
           "Гипсокартон {b} {m} {s}", "{b} {m} {s} лист", ("Knauf", "Волма", "Gyproc"), "GK",
           ("12,5 мм", "9,5 мм"), (Special(" ГКЛВ влагостойкий", props=_f("moisture_resistant")),)),
    Family("gkl_profile", "drywall", _f("drywall"), "Гипсокартон > Профили",
           "Профиль для гипсокартона {b} {m} {s}", "{b} {m} {s} стойка", ("Knauf", "Гипрок", "Албес"),
           "GP", ("60x27 мм 3 м", "27x28 мм 3 м")),
    Family("socket", "electrical", _f("electrical"), "Электротовары > Розетки",
           "Розетка {b} {m} {s}", "{b} {m} {s} розет", ("Legrand", "Schneider", "Werkel"), "SO",
           ("IP20", "IP44"), size_props={"IP44": _f("moisture_resistant")}),
    Family("cable", "electrical", _f("electrical"), "Электротовары > Кабель",
           "Кабель ВВГнг {b} {m} {s}", "{b} {m} {s} бухта", ("Севкабель", "Конкорд", "Рыбинсккабель"),
           "CB", ("3x1,5 мм 100 м", "3x2,5 мм 100 м")),
    Family("faucet", "none", _f("plumbing"), "Сантехника > Смесители",
           "Смеситель {b} {m} {s}", "{b} {m} {s} хром", ("Grohe", "Lemark", "Iddis"), "FC",
           ("для кухни", "для ванны")),
    Family("insulation", "none", _f("insulation"), "Утеплители",
           "Утеплитель минеральная вата {b} {m} {s}", "{b} {m} {s} плита", ("Rockwool", "Технониколь"),
           "IN", ("50 мм", "100 мм")),
    Family("roller", "none", _f("tools_consumables"), "Инструмент > Малярный",
           "Валик малярный {b} {m} {s}", "{b} {m} {s} ручка", ("Hardy", "Matrix", "Sparta"), "RL",
           ("180 мм", "250 мм")),
    Family("door", "none", _f("doors_windows"), "Двери",
           "Дверь межкомнатная {b} {m} {s}", "{b} {m} {s} полотно", ("Profil Doors", "Верда"), "DR",
           ("800 мм", "900 мм")),
)

# a few families' size strings imply a room via the visible text
_SIZE_ROOMS = {"для кухни": "kitchen", "для ванны": "bathroom"}
MODELS_PER_FAMILY = 8


def _models(f: Family) -> list[str]:
    return [f"{f.prefix}{10 + i * 3}" for i in range(MODELS_PER_FAMILY)]


def generate(
    n: int, seed: int = 0, keyless_share: float = 0.35, miscategorised_share: float = 0.07,
    special_share: float = 0.3,
) -> list[SynthItem]:
    rnd = random.Random(seed)
    out: list[SynthItem] = []
    for i in range(n):
        fam = rnd.choice(FAMILIES)
        model = rnd.choice(_models(fam))
        brand = rnd.choice(fam.brands)
        size = rnd.choice(fam.sizes)
        keyless = rnd.random() < keyless_share
        tpl = fam.keyless if keyless else fam.kw
        name = tpl.format(b=brand, m=model, s=size)
        rooms: set[str] = set()
        props: set[str] = set(fam.size_props.get(size, ()))
        if size in _SIZE_ROOMS:
            rooms.add(_SIZE_ROOMS[size])
        if fam.specials and rnd.random() < special_share:
            sp = rnd.choice(fam.specials)
            name += sp.suffix
            rooms |= sp.rooms
            props |= sp.props
        cat = fam.category
        mis = rnd.random() < miscategorised_share
        if mis:
            other = rnd.choice([x for x in FAMILIES if x.key != fam.key])
            cat = other.category
        product = Product(
            sku=f"S{seed}-{i}", name=name, category_path=[c.strip() for c in cat.split(">")],
            brand=brand)
        gold = Labels(set(fam.works), rooms or {"any"}, props, fam.calc)
        out.append(SynthItem(product, gold, f"{fam.key}:{model}", mis, keyless))
    return out


def split_by_group(
    items: list[SynthItem], seed: int = 0, shares: tuple[float, float] = (0.6, 0.2)
) -> tuple[list[SynthItem], list[SynthItem], list[SynthItem]]:
    """Train / dev / test split by product group so test models are unseen in training."""
    groups = sorted({i.group for i in items})
    random.Random(seed).shuffle(groups)
    n_tr = int(len(groups) * shares[0])
    n_dev = int(len(groups) * shares[1])
    which = {g: (0 if k < n_tr else 1 if k < n_tr + n_dev else 2) for k, g in enumerate(groups)}
    parts: tuple[list[SynthItem], list[SynthItem], list[SynthItem]] = ([], [], [])
    for it in items:
        parts[which[it.group]].append(it)
    return parts
