"""Deterministic Russian explanations (no LLM)."""

PROP_RU = {
    "moisture_resistant": "влагостойкий",
    "washable": "моющийся",
    "frost_resistant": "морозостойкий",
    "low_emission": "низкая эмиссия",
    "wear_class_32": "класс износостойкости 32",
    "wear_class_33": "класс износостойкости 33",
    "wear_class_34": "класс износостойкости 34",
    "anti_slip": "противоскользящий",
    "heat_resistant": "термостойкий",
    "uv_resistant": "стойкий к УФ",
}
ROOM_FOR_RU = {
    "bathroom": "ванной", "kitchen": "кухни", "kids": "детской", "balcony": "балкона",
    "hallway": "прихожей", "living": "гостиной", "bedroom": "спальни",
}
TIER_RU = {"economy": "эконом-вариант", "standard": "оптимальная цена", "premium": "премиум"}


def reasons(room: str, props: list[str], room_specific: bool, tier: str | None) -> list[str]:
    out: list[str] = []
    names = [PROP_RU[p] for p in props if p in PROP_RU]
    head = f"подходит для {ROOM_FOR_RU[room]}" if room in ROOM_FOR_RU else "подходит"
    out.append(f"{head}: {', '.join(names)}" if names else head)
    if room_specific:
        out.append("специально для этого помещения")
    if tier:
        out.append(TIER_RU.get(tier, tier))
    return out
