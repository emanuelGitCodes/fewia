"""Values are per 100 g from USDA FoodData Central."""

from app.domain.catalog import INGREDIENTS
from app.domain.nutrition import USDA_NUTRITION_NOTICE, NutritionFacts

__all__ = ["USDA_NUTRITION_NOTICE"]

NUTRITION_BASIS_G = 100

NUTRITION: dict[str, NutritionFacts] = {
    "chicken_breast": NutritionFacts(171077, 120, 22500, 2620, 0, 45),
    "eggs": NutritionFacts(171287, 143, 12560, 9510, 720, 142),
    "black_beans": NutritionFacts(173735, 132, 8860, 540, 23710, 1),
    "tortillas": NutritionFacts(175036, 218, 5700, 2850, 44640, 45),
    "salsa": NutritionFacts(174524, 29, 1520, 170, 6640, 711),
    "rice": NutritionFacts(168877, 365, 7130, 660, 79950, 5),
    "pasta": NutritionFacts(169736, 371, 13040, 1510, 74670, 6),
    "tomato": NutritionFacts(170051, 16, 790, 250, 3470, 115),
    "onion": NutritionFacts(170000, 40, 1100, 100, 9340, 4),
    "garlic": NutritionFacts(169230, 149, 6360, 500, 33060, 17),
    "olive_oil": NutritionFacts(171413, 884, 0, 100000, 0, 2),
    "cumin": NutritionFacts(170923, 375, 17810, 22270, 44240, 168),
    "salt": NutritionFacts(173468, 0, 0, 0, 0, 38758),
    "lentils": NutritionFacts(172420, 352, 24630, 1060, 63350, 6),
    "chickpeas": NutritionFacts(173757, 164, 8860, 2590, 27420, 7),
    "coconut_milk": NutritionFacts(170173, 197, 2020, 21330, 2810, 13),
    "curry_powder": NutritionFacts(170924, 325, 14290, 14010, 55830, 52),
    "mixed_vegetables": NutritionFacts(170471, 72, 3330, 520, 13470, 47),
    "soy_sauce": NutritionFacts(174277, 53, 8140, 570, 4930, 5493),
    "potato": NutritionFacts(170027, 79, 2140, 80, 18070, 5),
    "oats": NutritionFacts(173904, 379, 13150, 6520, 67700, 6),
    "oat_milk": NutritionFacts(2257046, 48, 800, 2750, 5100, 42),
}

if set(NUTRITION) != set(INGREDIENTS):
    raise ValueError("NUTRITION keys MUST match INGREDIENTS")
