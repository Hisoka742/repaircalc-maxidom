"""What a product card must contain for each calculator: the single source of truth.

Used by the room/product calculators (to skip unusable SKUs) and by the readiness report
(to tell, before a demo, how much of a catalog the calculators can actually serve).
"""
from collections.abc import Mapping

# calc template -> (attributes that must all be present, groups of which at least one is needed)
REQUIREMENTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "drywall": (("thickness_mm",), ()),   # a sheet has a thickness; a profile does not
    "paint": (("spread_m2_per_l", "pack_volume_l"), ()),
    "primer": (("consumption_l_per_m2", "pack_volume_l"), ()),
    "putty": (("consumption_kg_per_m2_per_mm", "pack_mass_kg"), ()),
    "self_leveling": (("consumption_kg_per_m2_per_mm", "pack_mass_kg"), ()),
    "wallpaper": (("roll_width_m", "roll_length_m"), ()),
    "wallpaper_glue": ((), ("coverage_m2_per_pack", "consumption_kg_per_m2")),
    "laminate": (("m2_per_pack",), ()),
    "underlay": (("m2_per_pack",), ()),
    "tile": (("tile_w_mm", "tile_h_mm"), ("m2_per_pack", "pcs_per_pack")),
    "tile_adhesive": (("pack_mass_kg",), ()),
    "tile_spacers": (("pcs_per_pack",), ()),
    "grout": (("pack_mass_kg",), ()),
    "waterproofing": (("pack_mass_kg",), ()),
}


def missing_attrs(calc: str, attrs: Mapping[str, object]) -> list[str]:
    """Names of the attributes a product of this calc type lacks (empty = calculable)."""
    required, any_of = REQUIREMENTS.get(calc, ((), ()))
    miss = [a for a in required if a not in attrs]
    if any_of and not any(a in attrs for a in any_of):
        miss.append("/".join(any_of))
    return miss
