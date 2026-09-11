from dataclasses import dataclass

USDA_NUTRITION_NOTICE = (
    "Nutrition facts are from USDA FoodData Central. They are not a medical claim."
)

_FDC_ID_ERROR = "fdc_id MUST be a positive integer."
_MASS_ENERGY_ERROR = "Mass and energy fields MUST be non-negative integers."


def _require_positive_int(value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(_FDC_ID_ERROR)


def _require_non_negative_int(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(_MASS_ENERGY_ERROR)


@dataclass(frozen=True, slots=True)
class NutritionFacts:
    fdc_id: int
    energy_kcal: int
    protein_mg: int
    fat_mg: int
    carbohydrate_mg: int
    sodium_mg: int

    def __post_init__(self) -> None:
        _require_positive_int(self.fdc_id)
        _require_non_negative_int(self.energy_kcal)
        _require_non_negative_int(self.protein_mg)
        _require_non_negative_int(self.fat_mg)
        _require_non_negative_int(self.carbohydrate_mg)
        _require_non_negative_int(self.sodium_mg)
