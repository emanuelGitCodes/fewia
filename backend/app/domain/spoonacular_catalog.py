"""Values are Spoonacular ingredient ids."""

from app.domain.catalog import INGREDIENTS

SPOONACULAR_IDS: dict[str, int] = {
    "chicken_breast": 5062,
    "eggs": 1123,
    "black_beans": 16015,
    "tortillas": 18363,
    "salsa": 6164,
    "rice": 20444,
    "pasta": 20420,
    "tomato": 11529,
    "onion": 11282,
    "garlic": 11215,
    "olive_oil": 4053,
    "cumin": 2014,
    "salt": 2047,
    "lentils": 16069,
    "chickpeas": 16057,
    "coconut_milk": 12117,
    "curry_powder": 2015,
    "mixed_vegetables": 11583,
    "soy_sauce": 16124,
    "potato": 11352,
    "oats": 8120,
    "oat_milk": 93790,
}

if set(SPOONACULAR_IDS) != set(INGREDIENTS):
    raise ValueError("SPOONACULAR_IDS keys MUST match INGREDIENTS")
