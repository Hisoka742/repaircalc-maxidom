from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

TAXONOMY_FILE = Path(__file__).resolve().parents[1] / "knowledge" / "taxonomy.yaml"


@dataclass(frozen=True)
class Taxonomy:
    work_categories: dict[str, str]
    room_types: dict[str, str]
    properties: dict[str, str]
    calc_templates: dict[str, str]


@cache
def load_taxonomy() -> Taxonomy:
    raw = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8"))
    return Taxonomy(raw["work_categories"], raw["room_types"], raw["properties"],
                    raw["calc_templates"])
