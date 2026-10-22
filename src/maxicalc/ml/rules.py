"""Rules layer: high-precision labels from category path, name and extracted attributes.

Two scans with the same ordered table (specific before general): one over the store's category
path, one over the product name. Agreement raises confidence; disagreement is a conflict
(a likely store miscategorisation) and goes to review.
"""
import re
from dataclasses import dataclass, field

from maxicalc.catalog.normalize import normalize_text
from maxicalc.catalog.schema import Product
from maxicalc.ml.extract import extract


@dataclass(frozen=True)
class LabelHit:
    label: str
    reason: str
    confidence: float


@dataclass
class RuleResult:
    work_categories: dict[str, LabelHit] = field(default_factory=dict)
    room_types: dict[str, LabelHit] = field(default_factory=dict)
    properties: dict[str, LabelHit] = field(default_factory=dict)
    calc_template: LabelHit | None = None
    conflict: bool = False


# (calc_template, work_categories, pattern). Order matters: first match wins per scan.
_TABLE: list[tuple[str, tuple[str, ...], str]] = [
    ("wallpaper_glue", ("wall_finish_wallpaper",),
     r"клей\s+для\s+обо|обойн\w+\s+клей|клей\s+обойн"),
    ("none", ("tools_consumables",),
     r"герметик|профил\w*\s+(?:пвх|алюм\w*|для\s+(?:зеркал|плитк|ванн))|подплиточн"),
    ("none", ("tools_consumables",),
     r"аэрозол|пальчиков|маркер|краск\w+\s+для\s+(?:обув|ткан|волос|авто)|для\s+обув"
     r"|эмаль\S*\s+(?:по\s+|для\s+)?(?:металл|авто)|грунт-эмаль|баллон"
     r"|\bковш|ванночк|ведро\s+для|синька|смывк|блестк|холодная\s+сварка|отвердител"
     r"|шпатлевк\w*\s+(?:\S+\s+){0,3}(?:по\s+дереву|эпоксид)|клей-шпатлевк|набор\s+для\s+ремонта"
     r"|шпатлевк\w*\s+автомобильн|автомобильн\w+\s+шпатлевк|крышк\w+\s+для|ведр\w*\s*для"
     r"|краск\w+\s+для\s+(?:печ|кафел|дорожн|разметк)|краска\s+ак-|грунт-краска|для\s+пола"
     r"|полы\s+и\s+лестн|антисептик|древесин"
     r"|\bэмаль\b|краск\w*\s+масляная|\bпф-\d|\bма-\d"),
    ("tile_adhesive", ("wall_tile", "floor_finish"),
     r"клей\s+(?:для\s+)?(?:керам\w*\.?\s*)?(?:плит|керамогранит|камн)|плиточн\w+\s+клей"
     r"|клей\s+плиточн"),
    ("grout", ("wall_tile", "floor_finish"), r"затирк|\bфуг[аи]\b"),
    ("tile_spacers", ("wall_tile", "floor_finish"),
     r"крестик|\bсвп\b|систем\w+\s+выравнивани\w+\s+плит|клин\w+\s+для\s+плит"),
    ("waterproofing", ("waterproofing",),
     r"гидроизоляц|обмазочн|битумн|битум\w*\s+мастик|резинобитум"),
    ("self_leveling", ("floor_prep",), r"самовыравн|наливн\w+\s+пол"),
    # a rug mat is not a floor underlay
    ("none", ("tools_consumables",), r"подложк\w*\s+(?:под|для)\s+ков(?:е)?р"),
    ("underlay", ("floor_prep",), r"подложк"),
    ("none", ("floor_prep",), r"т[её]пл\w+\s+пол"),   # underfloor heating is not tile / laminate
    # underfloor heating is not tile / laminate
    ("none", ("floor_prep",), r"т[её]пл\w+\s+пол"),
    ("none", ("ceiling",), r"потолочн\w+\s+(?:плинтус|багет|плитк)|\bбагет"),
    ("skirting", ("floor_finish",), r"плинтус"),
    ("laminate", ("floor_finish",),
     r"ламинат|\bspc\b|кварцвинил|виниловая\s+плитка|паркет|инженерн\w+\s+доск"),
    ("wallpaper", ("wall_finish_wallpaper",), r"обои|фотообои"),
    ("paint", ("wall_finish_paint",), r"краск|эмаль"),
    ("primer", ("wall_prep",), r"грунт"),
    ("putty", ("wall_prep",), r"шпатлевк|шпаклевк|штукатурк|гипсов\w+\s+смес"),
    ("drywall", ("drywall",),
     r"гипсокартон|\bгклв?\b|гипсоволокн|профил\w*\s+(?:для\s+)?гкл|профил\w*\s+(?:cd|ud|cw|uw)\b"),
    ("electrical", ("electrical",),
     r"розетк|выключател|кабел|\bпровод\b|\bузо\b|светильник|электрощит|автоматическ\w+\s+выключ"),
    ("tile", ("wall_tile", "floor_finish"), r"плитк|керамогранит|мозаик|клинкер"),
    ("none", ("plumbing",), r"смесител|унитаз|раковин|сифон|душев|ванн[аыу]\b|полотенцесушител"),
    ("none", ("insulation",), r"утеплител|минеральн\w+\s+ват|пенопласт|пеноплэкс|шумоизоляц"),
    ("none", ("doors_windows",), r"\bдвер[ьи]\b|дверн\w+\s+блок|\bокн[оа]\b|подоконник|откос"),
    ("none", ("tools_consumables",),
     r"инструмент|шпатель|валик|кисть|малярн\w+\s+лент|перчатк|рулетк|\bуровень\b|\bдрель\b"),
]
_COMPILED = [(c, w, re.compile(p)) for c, w, p in _TABLE]

_ROOMS = {
    "bathroom": r"ванн|санузе?л|санузл|душев|туалет",
    "kitchen": r"кухн|фартук|столешниц",
    "kids": r"детск",
    "balcony": r"балкон|лоджи|веранд",
    "hallway": r"прихож|коридор",
    "living": r"гостин",
    "bedroom": r"спальн",
}
_PROPS = {
    "moisture_resistant": r"влагостойк|влагозащищ|влагоустойчив|для\s+влажных|\bгклв\b|водостойк",
    "washable": r"моющ|стойк\w+\s+к\s+мытью|устойчив\w+\s+к\s+мытью|истиранию",
    "frost_resistant": r"морозостойк|морозоустойчив|всесезонн",
    "low_emission": r"без\s+запах|низк\w+\s+voc|\bэко\b|экологичн",
    "anti_slip": r"противоскольз|антискользящ|\br1[0-3]\b",
    "heat_resistant": r"термостойк|жаростойк|жаропрочн",
    "uv_resistant": r"\buv\b|уф-стойк|ультрафиолет|светостойк|не\s+выгорает",
}
_ROOM_RE = {k: re.compile(v) for k, v in _ROOMS.items()}
_PROP_RE = {k: re.compile(v) for k, v in _PROPS.items()}


def _prep(s: str) -> str:
    return normalize_text(s).lower().replace("ё", "е")


def _scan(text: str) -> tuple[str, tuple[str, ...], str] | None:
    for calc, works, pat in _COMPILED:
        m = pat.search(text)
        if m:
            return calc, works, m.group(0)
    return None


def apply_rules(p: Product) -> RuleResult:
    res = RuleResult()
    cat_text = _prep(" ".join(p.category_path))
    name_text = _prep(p.name)
    # most specific category first: the root «Краска и малярный инструмент» must not turn a
    # primer ("Грунтовка") into a paint/primer conflict
    cat_hit = next((h for seg in reversed(p.category_path)
                    if (h := _scan(_prep(seg))) is not None), None)
    name_hit = _scan(name_text)

    chosen: tuple[str, tuple[str, ...], str, str, float] | None = None
    if cat_hit and name_hit:
        if cat_hit[0] == name_hit[0]:
            chosen = (*name_hit, "категория и название совпадают", 0.99)
        else:
            res.conflict = True
            chosen = (*name_hit, f"конфликт: категория «{cat_hit[2]}» vs название «{name_hit[2]}»",
                      0.5)
    elif name_hit:
        chosen = (*name_hit, "по названию", 0.95)
    elif cat_hit:
        chosen = (*cat_hit, "по категории магазина", 0.97)
    if chosen:
        calc, works, word, why, conf = chosen
        reason = f"«{word}»: {why}"
        res.calc_template = LabelHit(calc, reason, conf)
        for w in works:
            res.work_categories[w] = LabelHit(w, reason, conf)
        name_l = name_text
        if calc == "paint" and "потолк" in name_l:
            res.work_categories["ceiling"] = LabelHit("ceiling", "«потолк» в названии", 0.9)
        if calc == "tile":
            if "напольн" in name_l or "для пола" in name_l:
                res.work_categories.pop("wall_tile", None)
            elif "настенн" in name_l or "для стен" in name_l:
                res.work_categories.pop("floor_finish", None)

    attrs = extract(p).attrs
    text = _prep(" ".join([p.name, p.description, *p.characteristics.values()]))
    for room, rx in _ROOM_RE.items():
        m = rx.search(text) or rx.search(cat_text)
        if m:
            res.room_types[room] = LabelHit(room, f"«{m.group(0)}» в тексте", 0.95)
    for prop, rx in _PROP_RE.items():
        m = rx.search(text)
        if m:
            res.properties[prop] = LabelHit(prop, f"«{m.group(0)}» в тексте", 0.95)
    ip = attrs.get("ip_rating")
    if ip is not None and int(ip.value) >= 44:  # type: ignore[arg-type]
        res.properties["moisture_resistant"] = LabelHit(
            "moisture_resistant", f"IP{ip.value} ≥ IP44", 0.99)
    wear = attrs.get("wear_class")
    if wear is not None and int(wear.value) in (32, 33, 34):  # type: ignore[arg-type]
        lab = f"wear_class_{wear.value}"
        res.properties[lab] = LabelHit(lab, f"класс износостойкости {wear.value}", 0.99)
    emission = attrs.get("emission_class")
    if emission is not None and emission.value in ("E0", "E05", "E1"):
        res.properties["low_emission"] = LabelHit(
            "low_emission", f"класс эмиссии {emission.value}", 0.99)
    return res
