"""Rule fixes found by running the pipeline on real maxidom.ru product names."""
from maxicalc.catalog.schema import Product
from maxicalc.ml.rules import apply_rules


def calc_of(name: str) -> str | None:
    r = apply_rules(Product(sku="x", name=name))
    return r.calc_template.label if r.calc_template else None


def test_tile_adhesive_with_abbreviated_ceramic() -> None:
    assert calc_of("клей для керам.плитки LITOKOL Litoacril Plus 1кг") == "tile_adhesive"


def test_sealant_and_trim_profiles_are_not_tiles() -> None:
    assert calc_of("герметик силиконовый Ветонит Комфорт для плитки 280 мл") != "tile"
    assert calc_of("профиль ПВХ SALAG для ванной подплиточный 1,85м белый") != "tile"
