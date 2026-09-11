from app.domain.catalog import INGREDIENTS
from app.domain.nutrition import USDA_NUTRITION_NOTICE as DOMAIN_NOTICE
from app.domain.nutrition_catalog import (
    NUTRITION,
    NUTRITION_BASIS_G,
    USDA_NUTRITION_NOTICE,
)


def test_nutrition_keys_match_ingredients() -> None:
    assert set(NUTRITION) == set(INGREDIENTS)


def test_fdc_ids_are_positive() -> None:
    for facts in NUTRITION.values():
        assert facts.fdc_id > 0


def test_mass_and_energy_fields_are_non_negative() -> None:
    for facts in NUTRITION.values():
        assert facts.energy_kcal >= 0
        assert facts.protein_mg >= 0
        assert facts.fat_mg >= 0
        assert facts.carbohydrate_mg >= 0
        assert facts.sodium_mg >= 0


def test_nutrition_basis_is_100_g() -> None:
    assert NUTRITION_BASIS_G == 100


def test_notice_matches_domain_constant() -> None:
    assert USDA_NUTRITION_NOTICE == DOMAIN_NOTICE


def test_salt_sodium_mg() -> None:
    assert NUTRITION["salt"].sodium_mg == 38758


def test_olive_oil_fat_mg() -> None:
    assert NUTRITION["olive_oil"].fat_mg == 100000
