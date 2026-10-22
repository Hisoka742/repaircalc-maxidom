"""Attribute extraction: structured characteristics -> regex on name/description -> (optional) LLM.

Every value is range-checked; impossible values are returned in `rejected`, never in `attrs`.
Attribute names carry units (roll_width_m, tile_w_mm, ...). Source priority:
characteristics > name > description > llm.
"""
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from maxicalc.catalog.normalize import normalize_text, parse_number
from maxicalc.catalog.schema import Product
from maxicalc.ml.llm_client import LLMClient, LLMError

Value = Decimal | int | str
Source = Literal["characteristics", "name", "description", "llm", "derived"]
Confidence = Literal["high", "medium", "low"]

_D = Decimal
# attr -> (min, max) inclusive, for numeric attrs
RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "roll_width_m": (_D("0.5"), _D("1.1")),
    "roll_length_m": (_D(5), _D(25)),
    "rapport_cm": (_D(1), _D(100)),
    "tile_w_mm": (_D(10), _D(3000)),
    "tile_h_mm": (_D(10), _D(3000)),
    "length_mm": (_D(100), _D(6000)),
    "width_mm": (_D(10), _D(2000)),
    "thickness_mm": (_D("0.5"), _D(60)),
    "m2_per_pack": (_D("0.05"), _D(30)),
    "coverage_m2_per_pack": (_D(1), _D(200)),
    "pack_mass_kg": (_D("0.05"), _D(50)),
    "pack_volume_l": (_D("0.05"), _D(30)),
    "pcs_per_pack": (_D(1), _D(10000)),
    "spread_m2_per_l": (_D(1), _D(30)),
    "consumption_l_per_m2": (_D("0.01"), _D(2)),
    "consumption_kg_per_m2": (_D("0.05"), _D(30)),
    "consumption_kg_per_m2_per_mm": (_D("0.1"), _D(4)),
}
WEAR_CLASSES = {21, 22, 23, 31, 32, 33, 34, 41, 42, 43}
EMISSION_CLASSES = {"E0", "E05", "E1", "E2"}
INT_ATTRS = {"pcs_per_pack"}


@dataclass(frozen=True)
class Attr:
    value: Value
    source: Source
    confidence: Confidence
    evidence: str


@dataclass(frozen=True)
class Rejected:
    name: str
    value: object
    reason: str
    evidence: str


@dataclass
class ExtractionResult:
    attrs: dict[str, Attr] = field(default_factory=dict)
    rejected: list[Rejected] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _validate(name: str, value: Value) -> str | None:
    """Return a rejection reason, or None if the value is plausible."""
    if name == "wear_class":
        return None if value in WEAR_CLASSES else f"класс износостойкости {value} не существует"
    if name == "ip_rating":
        v = int(value)  # type: ignore[arg-type]
        return None if 0 <= v <= 69 and v // 10 <= 6 else f"IP{v} не существует"
    if name == "emission_class":
        return None if value in EMISSION_CLASSES else f"класс эмиссии {value} не существует"
    if name in RANGES:
        lo, hi = RANGES[name]
        v = Decimal(value)  # type: ignore[arg-type]
        if not lo <= v <= hi:
            return f"{v} вне допустимого диапазона {lo}–{hi}"
        return None
    return None


class _Collector:
    def __init__(self) -> None:
        self.res = ExtractionResult()

    def add(
        self, name: str, value: Value, source: Source, conf: Confidence, evidence: str
    ) -> None:
        if name in self.res.attrs:
            return
        if name in INT_ATTRS and isinstance(value, Decimal):
            if value != value.to_integral_value():
                self.res.rejected.append(Rejected(name, value, "не целое число", evidence))
                return
            value = int(value)
        reason = _validate(name, value)
        if reason:
            self.res.rejected.append(Rejected(name, value, reason, evidence))
            return
        self.res.attrs[name] = Attr(value, source, conf, evidence)

    def finish(self) -> ExtractionResult:
        self.res.rejected = [r for r in self.res.rejected if r.name not in self.res.attrs]
        return self.res


# ---------- unit scaling ----------
# attr -> (default unit, {unit: multiplier into attr's canonical unit})
_LEN_MM = {"мм": _D(1), "см": _D(10), "м": _D(1000)}
SCALES: dict[str, tuple[str, dict[str, Decimal]]] = {
    "roll_width_m": ("м", {"м": _D(1), "см": _D("0.01"), "мм": _D("0.001")}),
    "roll_length_m": ("м", {"м": _D(1), "см": _D("0.01"), "мм": _D("0.001")}),
    "rapport_cm": ("см", {"см": _D(1), "мм": _D("0.1"), "м": _D(100)}),
    "tile_w_mm": ("мм", _LEN_MM), "tile_h_mm": ("мм", _LEN_MM),
    "length_mm": ("мм", _LEN_MM), "width_mm": ("мм", _LEN_MM),
    "thickness_mm": ("мм", _LEN_MM),
    "pack_mass_kg": ("кг", {"кг": _D(1), "г": _D("0.001")}),
    "pack_volume_l": ("л", {"л": _D(1), "мл": _D("0.001")}),
    "m2_per_pack": ("м2", {"м2": _D(1)}),
    "coverage_m2_per_pack": ("м2", {"м2": _D(1)}),
}

# normalized characteristic key -> attr
CHAR_KEYS: dict[str, str] = {
    "ширина рулона": "roll_width_m", "длина рулона": "roll_length_m", "раппорт": "rapport_cm",
    "площадь в упаковке": "m2_per_pack", "площадь упаковки": "m2_per_pack",
    "площадь в упаковке, м2": "m2_per_pack", "площадь покрытия упаковкой": "m2_per_pack",
    "вес": "pack_mass_kg", "масса": "pack_mass_kg", "вес упаковки": "pack_mass_kg",
    "масса упаковки": "pack_mass_kg", "вес нетто": "pack_mass_kg",
    "объем": "pack_volume_l", "объём": "pack_volume_l", "объем упаковки": "pack_volume_l",
    "литраж банки": "pack_volume_l",
    "класс износостойкости": "wear_class", "класс нагрузки": "wear_class",
    "степень защиты": "ip_rating", "степень защиты ip": "ip_rating", "ip": "ip_rating",
    "класс эмиссии": "emission_class", "эмиссия": "emission_class",
    "толщина": "thickness_mm", "длина": "length_mm", "ширина": "width_mm",
    "количество в упаковке": "pcs_per_pack", "штук в упаковке": "pcs_per_pack",
    "кол-во в упаковке": "pcs_per_pack",
    "размер": "size", "формат": "size", "размер плитки": "size", "габариты": "size",
}

_NUM = r"(\d+(?:[.,]\d+)?)"
_X = r"\s*[xх×*]\s*"
_KEY_UNIT = re.compile(r"^(.*?)\s*(?:,|\()\s*([^,()]+?)\s*\)?$")
_LEADING_NUM = re.compile(r"[-+]?\d[\d\s ]*(?:[.,]\d+)?")


_KV_M = re.compile(r"кв\.?\s*м\.?")


def _norm(s: str) -> str:
    return _KV_M.sub("м2", normalize_text(s).lower().replace("ё", "е"))


# characteristic keys that hold a consumption ("Расход материала: 0,11л/кв.м")
CONSUMPTION_KEYS = {"расход материала", "расход", "расход краски", "расход на слой",
                    "расход на 1 м2", "расход на м2"}
_CONS = re.compile(_NUM + r"\s*(л|мл|кг|г)\s*/\s*м2")
_CONS_SPREAD = re.compile(_NUM + r"\s*м2\s*/\s*л")


def _consumption(c: "_Collector", raw_val: str, ev: str) -> None:
    val = _norm(raw_val)
    m = _CONS.search(val)
    if m:
        num = parse_number_safe(m.group(1))
        if num is None:
            return
        unit = m.group(2)
        if unit in ("л", "мл"):
            c.add("consumption_l_per_m2", num / (1000 if unit == "мл" else 1),
                  "characteristics", "high", ev)
        else:
            c.add("consumption_kg_per_m2", num / (1000 if unit == "г" else 1),
                  "characteristics", "high", ev)
        return
    s = _CONS_SPREAD.search(val)
    num = parse_number_safe(s.group(1)) if s else None
    if num is not None:
        c.add("spread_m2_per_l", num, "characteristics", "high", ev)


def parse_number_safe(s: str) -> Decimal | None:
    try:
        return parse_number(s)
    except ValueError:
        return None


def _scaled(attr: str, num: Decimal, unit: str | None) -> Decimal | None:
    default, table = SCALES[attr]
    u = (unit or default).lower().replace("²", "2").replace(".", "")
    mult = table.get(u)
    return None if mult is None else num * mult


def _from_characteristics(
    c: _Collector, chars: dict[str, str], hints: "_Hints"
) -> None:
    for raw_key, raw_val in chars.items():
        key = _norm(raw_key)
        unit: str | None = None
        m = _KEY_UNIT.match(key)
        base = key
        if m:
            base, unit = m.group(1), m.group(2)
        ev = f"{raw_key}: {raw_val}"
        if base in CONSUMPTION_KEYS or key in CONSUMPTION_KEYS:
            _consumption(c, raw_val, ev)
            continue
        attr = CHAR_KEYS.get(base) or CHAR_KEYS.get(key)
        if not attr:
            continue
        val = _norm(raw_val)
        if attr == "size":
            _from_text(c, raw_val, "characteristics", hints)
        elif attr == "ip_rating":
            mm = re.search(r"(\d{2})", val)
            if mm:
                c.add(attr, int(mm.group(1)), "characteristics", "high", ev)
        elif attr == "emission_class":
            mm = re.search(r"[eе]\s?(0[5]?|1|2)", val)
            if mm:
                c.add(attr, "E" + mm.group(1), "characteristics", "high", ev)
        elif attr == "wear_class":
            mm = re.search(r"(\d{2})", val)
            if mm:
                c.add(attr, int(mm.group(1)), "characteristics", "high", ev)
        elif attr == "pcs_per_pack":
            if re.search(r"м\s?[2²]", val):
                n = _LEADING_NUM.match(val)
                num = parse_number_safe(n.group(0)) if n else None
                if num is not None:
                    c.add("m2_per_pack", num, "characteristics", "high", ev)
            else:
                n = _LEADING_NUM.match(val)
                num = parse_number_safe(n.group(0)) if n else None
                if num is not None:
                    c.add(attr, num, "characteristics", "high", ev)
        else:
            n = _LEADING_NUM.match(val)
            num = parse_number_safe(n.group(0)) if n else None
            if num is None:
                continue
            vu = re.search(r"\d\s*(мм|см|м2|м|кг|г|мл|л)\b", val)
            value = _scaled(attr, num, vu.group(1) if vu else unit)
            if value is not None:
                c.add(attr, value, "characteristics", "high", ev)


# ---------- free-text patterns ----------
_GLUE_COVERAGE = re.compile(
    r"(?:хватает\s+на|покрыва\w*|рассчитан\w*\s+на|на|до)\s*" + _NUM +
    r"\s*(?:м2|м²|кв\.?\s*м)", re.IGNORECASE)
_MM_ONLY = re.compile(_NUM + r"\s*мм(?![\w])")
_DIM3 = re.compile(_NUM + _X + _NUM + _X + _NUM + r"\s*(мм|см|м)?(?![\w])")
_DIM2 = re.compile(_NUM + r"\s*(?:мм|см|м)?" + _X + _NUM + r"\s*(мм|см|м)?(?![\w])")
_M2_PACK = [
    re.compile(_NUM + r"\s*м2\s*(?:/|в\s*)\s*уп"),
    re.compile(r"в\s*упаковке\s*[:\-]?\s*(?:\d+\s*шт\.?\s*,?\s*)?" + _NUM + r"\s*м2"),
    re.compile(r"площадь\s*(?:упаковки|в\s*упаковке)\s*[:\-]?\s*" + _NUM),
]
_PCS = [
    re.compile(r"(\d+)\s*шт\.?\s*(?:в\s*уп|/\s*уп)"),
    re.compile(r"в\s*упаковке\s*[:\-]?\s*(\d+)\s*шт"),
]
_MASS = re.compile(_NUM + r"\s*кг(?![\w/])")
_VOL = re.compile(_NUM + r"\s*(?:л|литр\w*)(?![\w/])")
_WEAR = [re.compile(r"(\d{2})\s*(?:-?й\s*)?класс"),
         re.compile(r"класс\s*(?:износостойкости|нагрузки)?\s*[:\-]?\s*(\d{2})")]
_IP = re.compile(r"\bip\s?(\d{2})\b")
_EMISSION = [re.compile(r"класс(?:\s*эмиссии)?\s*[:\-]?\s*[eе]\s?(0[5]?|1|2)(?!\d)"),
             re.compile(r"(?<![\w])[eе]([01])(?![\w])")]
_RAPPORT = re.compile(r"раппорт\s*[:\-]?\s*" + _NUM + r"\s*(см|мм|м)?(?![\w])")
_THICK = re.compile(r"толщина\s*[:\-]?\s*" + _NUM + r"\s*(мм|см)?(?![\w])")
_KG_M2 = re.compile(r"расход[^\d]{0,30}" + _NUM + r"\s*кг\s*/\s*м2")
_AT_THICK = re.compile(r"\s*[^\d]{0,12}толщин\w*\s+слоя\s*(?:в\s*)?" + _NUM + r"\s*мм")
_KG_M2_PER_MM = re.compile(r"\s*(?:/\s*мм|на\s*1\s*мм)")
_SPREAD = re.compile(_NUM + r"(?:\s*[-–]\s*" + _NUM + r")?\s*м2\s*/\s*л")
_L_M2 = re.compile(_NUM + r"\s*л\s*/\s*м2")


def _prep(s: str) -> str:
    """NFKC (м² -> м2), lowercase, single spaces."""
    return _KV_M.sub("м2", normalize_text(s).lower().replace("ё", "е"))


def _num(s: str) -> Decimal:
    return parse_number(s)


def _from_text(c: _Collector, raw: str, source: Source, hints: "_Hints") -> None:
    text = _prep(raw)
    if not text:
        return
    ev = lambda m: m.group(0)  # noqa: E731

    work = text
    for m in _DIM3.finditer(text):
        a, b, t = _num(m.group(1)), _num(m.group(2)), _num(m.group(3))
        unit = m.group(4)
        if hints.tile and not (hints.plank or hints.drywall_sheet):
            # a tile / mosaic "30,5х30,5х0,4 см": two sides and the thickness
            tu = unit or ("см" if max(a, b) <= 200 else "мм")
            tconf: Confidence = "medium" if unit else "low"
            for attr, v in (("tile_w_mm", a), ("tile_h_mm", b), ("thickness_mm", t)):
                sv = _scaled(attr, v, tu)
                if sv is not None:
                    c.add(attr, sv, source, tconf, ev(m))
        else:
            for attr, v in (("length_mm", a), ("width_mm", b), ("thickness_mm", t)):
                sv = _scaled(attr, v, unit)
                if sv is not None:
                    c.add(attr, sv, source, "medium", ev(m))
        work = work.replace(m.group(0), " ")
    for m in _DIM2.finditer(work):
        a, b = _num(m.group(1)), _num(m.group(2))
        unit = m.group(3)
        if hints.wallpaper:
            lo, hi = min(a, b), max(a, b)
            rw, rl = _scaled("roll_width_m", lo, unit), _scaled("roll_length_m", hi, unit)
            if rw is not None and rl is not None:
                c.add("roll_width_m", rw, source, "medium", ev(m))
                c.add("roll_length_m", rl, source, "medium", ev(m))
        elif hints.plank:
            lw = (max(a, b), min(a, b))
            for attr, v in zip(("length_mm", "width_mm"), lw, strict=True):
                sv = _scaled(attr, v, unit)
                if sv is not None:
                    c.add(attr, sv, source, "medium" if unit else "low", ev(m))
        elif hints.tile:
            conf: Confidence = "medium"
            if unit is None:
                unit, conf = ("см" if max(a, b) <= 200 else "мм"), "low"
            for attr, v in (("tile_w_mm", a), ("tile_h_mm", b)):
                sv = _scaled(attr, v, unit)
                if sv is not None:
                    c.add(attr, sv, source, conf, ev(m))

    # "хватает на 40 м2": the area one pack of wallpaper glue covers
    if hints.wp_glue and (m := _GLUE_COVERAGE.search(text)):
        c.add("coverage_m2_per_pack", _num(m.group(1)), source, "medium", ev(m))

    if hints.drywall_sheet and "thickness_mm" not in c.res.attrs:
        # "лист ГКЛВ 12,5 мм": a lone millimetre figure on a drywall sheet is its thickness
        for m in _MM_ONLY.finditer(text):
            v = _num(m.group(1))
            if _D(6) <= v <= _D(25):
                c.add("thickness_mm", v, source, "medium", m.group(0))
                break

    for pat in _M2_PACK:
        if m := pat.search(text):
            c.add("m2_per_pack", _num(m.group(1)), source, "medium", ev(m))
            break
    for pat in _PCS:
        if m := pat.search(text):
            c.add("pcs_per_pack", _num(m.group(1)), source, "medium", ev(m))
            break
    if m := _MASS.search(text):
        c.add("pack_mass_kg", _num(m.group(1)), source, "medium", ev(m))
    if m := _VOL.search(text):
        c.add("pack_volume_l", _num(m.group(1)), source, "medium", ev(m))
    for pat in _WEAR:
        if m := pat.search(text):
            c.add("wear_class", int(m.group(1)), source, "medium", ev(m))
            break
    if m := _IP.search(text):
        c.add("ip_rating", int(m.group(1)), source, "medium", ev(m))
    for pat in _EMISSION:
        if m := pat.search(text):
            c.add("emission_class", "E" + m.group(1), source, "medium", ev(m))
            break
    if m := _RAPPORT.search(text):
        v = _scaled("rapport_cm", _num(m.group(1)), m.group(2))
        if v is not None:
            c.add("rapport_cm", v, source, "medium", ev(m))
    if m := _THICK.search(text):
        v = _scaled("thickness_mm", _num(m.group(1)), m.group(2))
        if v is not None:
            c.add("thickness_mm", v, source, "medium", ev(m))
    if m := _KG_M2.search(text):
        value = _num(m.group(1))
        at = _AT_THICK.match(text, m.end())
        if at and _num(at.group(1)) > 0:
            # "8,5 кг/м2 при толщине слоя 10 мм" -> per-mm rate (plain division, no LLM)
            c.add("consumption_kg_per_m2_per_mm", value / _num(at.group(1)), source,
                  "medium", ev(m) + at.group(0))
        elif _KG_M2_PER_MM.match(text, m.end()):
            c.add("consumption_kg_per_m2_per_mm", value, source, "medium", ev(m))
        else:
            c.add("consumption_kg_per_m2", value, source, "medium", ev(m))
    if m := _SPREAD.search(text):
        lo = _num(m.group(1))  # for a range take the conservative (smaller) coverage
        c.add("spread_m2_per_l", lo, source, "medium", ev(m))
    if m := _L_M2.search(text):
        c.add("consumption_l_per_m2", _num(m.group(1)), source, "medium", ev(m))


@dataclass(frozen=True)
class _Hints:
    """Product-type hints from category/name. Bare 'AxB' dimensions are only interpreted as
    wallpaper rolls or tiles when the product is one; otherwise 60x27 mm may be a profile."""

    wallpaper: bool
    tile: bool
    plank: bool = False
    drywall_sheet: bool = False
    wp_glue: bool = False


_WALLPAPER_WORDS = ("обои", "фотообои")
_TILE_WORDS = ("плитк", "керамогранит", "мозаик", "клинкер")
_PLANK_WORDS = ("ламинат", "паркет", "spc", "кварцвинил", "инженерная доска")
_DRYWALL_WORDS = ("гипсокартон", "гклв", "гкл ", "гкло", "гвл")
_WP_GLUE_WORDS = ("клей для обо", "обойный клей", "клей обойный", "для обоев")
_NOT_SHEET = ("профил", "саморез", "лент", "шпатл", "грунт", "подвес", "уголок", "дюбел")


def _hints(p: Product) -> _Hints:
    text = _prep(" ".join([*p.category_path, p.name]))
    return _Hints(
        any(w in text for w in _WALLPAPER_WORDS),
        any(w in text for w in _TILE_WORDS) and not any(w in text for w in _PLANK_WORDS),
        any(w in text for w in _PLANK_WORDS),
        any(w in text + " " for w in _DRYWALL_WORDS)
        and not any(w in text for w in _NOT_SHEET),
        "клей" in text and any(w in text for w in _WP_GLUE_WORDS),
    )


_PAINT_DENSITY = (_D("0.7"), _D("2.5"))   # kg/l, plausible range for liquid coatings


def _derive_paint(c: "_Collector") -> None:
    """Plain arithmetic on card facts (no LLM, no assumed density):
    consumption g/m2 -> l/m2 needs the product's OWN density (pack mass / pack volume);
    spread (m2/l) = 1 / consumption (l/m2)."""
    a = c.res.attrs
    if "consumption_l_per_m2" not in a and "consumption_kg_per_m2" in a:
        m, v = a.get("pack_mass_kg"), a.get("pack_volume_l")
        if m and v and Decimal(str(v.value)) > 0:
            rho = Decimal(str(m.value)) / Decimal(str(v.value))
            if _PAINT_DENSITY[0] <= rho <= _PAINT_DENSITY[1]:
                kg = Decimal(str(a["consumption_kg_per_m2"].value))
                c.add("consumption_l_per_m2", kg / rho, "derived", "medium",
                      f"{kg} кг/м2 / плотность {rho:.3f} кг/л ({m.value} кг / {v.value} л)")
    if "spread_m2_per_l" not in a and "consumption_l_per_m2" in a:
        cl = Decimal(str(a["consumption_l_per_m2"].value))
        if cl > 0:
            c.add("spread_m2_per_l", 1 / cl, "derived", a["consumption_l_per_m2"].confidence,
                  f"1 / {cl:.4f} л/м2")


def extract(p: Product) -> ExtractionResult:
    c = _Collector()
    h = _hints(p)
    _from_characteristics(c, p.characteristics, h)
    _from_text(c, p.name, "name", h)
    _from_text(c, p.description, "description", h)
    _derive_paint(c)
    return c.finish()


# ---------- LLM fallback ----------
LLM_NUMERIC = set(RANGES) | {"wear_class", "ip_rating"}
LLM_SYSTEM = (
    "Ты извлекаешь характеристики строительных товаров из текста. Отвечай только JSON по схеме. "
    "Для каждого поля верни value (число в указанных единицах) и quote — точную цитату из текста, "
    "из которой взято значение. Если значения нет в тексте — value и quote равны null. "
    "Ничего не вычисляй и не угадывай."
)
_UNITS_HINT = {a: SCALES[a][0] for a in SCALES}


def _llm_schema(fields: list[str]) -> dict[str, Any]:
    item = {
        "type": "object",
        "properties": {
            "value": {"type": ["number", "null"]},
            "quote": {"type": ["string", "null"]},
        },
        "required": ["value", "quote"],
        "additionalProperties": False,
    }
    return {"type": "object", "properties": {f: item for f in fields},
            "required": fields, "additionalProperties": False}


def extract_with_llm(
    p: Product,
    client: LLMClient,
    needed: Iterable[str],
    base: ExtractionResult | None = None,
) -> ExtractionResult:
    """Regex first; ask the LLM only for `needed` fields that are still missing.

    Each LLM value must come with a quote that literally occurs in the product text and must
    pass the same range validation. LLM values get confidence 'low' until benchmarked.
    """
    res = base or extract(p)
    missing = [f for f in dict.fromkeys(needed) if f in LLM_NUMERIC and f not in res.attrs]
    if not missing:
        return res
    full = " | ".join([p.name, p.description, *(f"{k}: {v}" for k, v in p.characteristics.items())])
    haystack = _prep(full)
    fields_desc = ", ".join(
        f"{f} ({_UNITS_HINT[f]})" if f in _UNITS_HINT else f for f in missing)
    try:
        data = client.chat_json(LLM_SYSTEM, f"Поля: {fields_desc}\nТекст: {full}",
                                _llm_schema(missing))
    except LLMError as e:
        res.errors.append(str(e))
        return res
    col = _Collector()
    col.res = res
    for f in missing:
        item = data.get(f) or {}
        value, quote = item.get("value"), item.get("quote")
        if value is None:
            continue
        if not quote or _prep(str(quote)) not in haystack:
            res.rejected.append(Rejected(f, value, "цитата не найдена в тексте товара",
                                         str(quote)))
            continue
        v: Value = Decimal(str(value))
        if f in ("wear_class", "ip_rating"):
            v = int(v)
        col.add(f, v, "llm", "low", str(quote))
    return col.finish()
