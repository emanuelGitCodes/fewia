from dataclasses import FrozenInstanceError

import pytest

from app.domain.nutrition import USDA_NUTRITION_NOTICE, NutritionFacts


def facts(
    *,
    fdc_id: int = 171077,
    energy_kcal: int = 165,
    protein_mg: int = 31000,
    fat_mg: int = 3600,
    carbohydrate_mg: int = 0,
    sodium_mg: int = 74,
) -> NutritionFacts:
    return NutritionFacts(
        fdc_id=fdc_id,
        energy_kcal=energy_kcal,
        protein_mg=protein_mg,
        fat_mg=fat_mg,
        carbohydrate_mg=carbohydrate_mg,
        sodium_mg=sodium_mg,
    )


def test_constructs_integer_nutrition_facts() -> None:
    result = facts()
    assert result.fdc_id == 171077
    assert result.energy_kcal == 165
    assert result.protein_mg == 31000
    assert result.fat_mg == 3600
    assert result.carbohydrate_mg == 0
    assert result.sodium_mg == 74


def test_notice_matches_usda_export() -> None:
    assert USDA_NUTRITION_NOTICE == (
        "Nutrition facts are from USDA FoodData Central. They are not a medical claim."
    )


def test_zero_mass_and_energy_are_valid() -> None:
    result = facts(
        energy_kcal=0,
        protein_mg=0,
        fat_mg=0,
        carbohydrate_mg=0,
        sodium_mg=0,
    )
    assert result.energy_kcal == 0
    assert result.protein_mg == 0
    assert result.fat_mg == 0
    assert result.carbohydrate_mg == 0
    assert result.sodium_mg == 0


@pytest.mark.parametrize("fdc_id", [0, -1])
def test_rejects_non_positive_fdc_id(fdc_id: int) -> None:
    with pytest.raises(ValueError, match="fdc_id MUST be a positive integer") as caught:
        facts(fdc_id=fdc_id)
    assert str(fdc_id) not in str(caught.value)


@pytest.mark.parametrize(
    "field",
    ["energy_kcal", "protein_mg", "fat_mg", "carbohydrate_mg", "sodium_mg"],
)
def test_rejects_negative_mass_and_energy(field: str) -> None:
    with pytest.raises(
        ValueError, match="Mass and energy fields MUST be non-negative integers"
    ) as caught:
        facts(**{field: -1})
    assert "-1" not in str(caught.value)


def test_nutrition_facts_are_frozen() -> None:
    result = facts()
    with pytest.raises(FrozenInstanceError):
        result.energy_kcal = 1  # type: ignore[misc]
