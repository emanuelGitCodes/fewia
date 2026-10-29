import pytest

from app.domain.catalog import RECIPES
from app.domain.recipe_variant import (
    RecipeChange,
    RecipeVariantError,
    apply_change,
    ingredient_grams,
    parse_change,
    round_half_up,
    variant_recipes,
)

TACOS = (
    ("chicken_breast", 100),
    ("tortillas", 2),
    ("salsa", 40),
    ("onion", 30),
    ("cumin", 1),
    ("olive_oil", 10),
    ("salt", 1),
)


def swap(old: str, new: str, quantity: int | None = None) -> RecipeChange:
    return RecipeChange(
        replace_ingredient_id=old, with_ingredient_id=new, quantity_per_serving=quantity
    )


def scale(ingredient_id: str, percent: int) -> RecipeChange:
    return RecipeChange(scale_ingredient_id=ingredient_id, scale_factor_percent=percent)


def test_fixture_matches_catalog() -> None:
    assert RECIPES["chicken_tacos"].ingredients == TACOS


@pytest.mark.parametrize(
    ("numerator", "denominator", "expected"),
    [(0, 5, 0), (1, 3, 0), (2, 3, 1), (1, 2, 1), (3, 2, 2), (5, 2, 3), (7, 7, 1)],
)
def test_round_half_up(numerator: int, denominator: int, expected: int) -> None:
    assert round_half_up(numerator, denominator) == expected


def test_ingredient_grams_converts_each_units() -> None:
    assert ingredient_grams("rice", 75) == 75
    assert ingredient_grams("eggs", 2) == 100
    assert ingredient_grams("tortillas", 2) == 48
    assert ingredient_grams("potato", 1) == 213


def test_default_substitute_keeps_grams_and_position() -> None:
    result = apply_change("chicken_tacos", swap("chicken_breast", "chickpeas"))
    assert result == (("chickpeas", 100), *TACOS[1:])


def test_substitute_does_not_mutate_catalog() -> None:
    apply_change("chicken_tacos", swap("chicken_breast", "chickpeas"))
    assert RECIPES["chicken_tacos"].ingredients == TACOS


def test_explicit_quantity_is_used_as_is_in_new_unit() -> None:
    result = apply_change("chicken_tacos", swap("chicken_breast", "chickpeas", 150))
    assert result[0] == ("chickpeas", 150)
    eggs = apply_change("chicken_tacos", swap("chicken_breast", "eggs", 3))
    assert eggs[0] == ("eggs", 3)
    for quantity in (1, 1000):
        edge = apply_change("chicken_tacos", swap("chicken_breast", "rice", quantity))
        assert edge[0] == ("rice", quantity)


def test_each_to_g_uses_grams_per_each() -> None:
    result = apply_change("chicken_tacos", swap("tortillas", "rice"))
    assert result[1] == ("rice", 48)
    eggs = apply_change("breakfast_burritos", swap("eggs", "rice"))
    assert eggs[0] == ("rice", 100)


@pytest.mark.parametrize(
    ("recipe_id", "old", "new", "expected"),
    [
        ("chicken_and_rice_bowls", "rice", "eggs", 2),  # 75 g is 1.5 eggs
        ("chicken_tacos", "chicken_breast", "eggs", 2),  # 100 g is 2 eggs
        ("chickpea_curry", "chickpeas", "eggs", 2),  # 120 g is 2.4 eggs
        ("chicken_and_rice_bowls", "rice", "potato", 1),  # 0.35 potato, min 1
        ("egg_fried_rice", "eggs", "potato", 1),  # 100 g is 0.47 potato, min 1
        ("chicken_tacos", "tortillas", "eggs", 1),  # 48 g is 0.96 eggs
    ],
)
def test_g_or_each_to_each_rounds_half_up_with_minimum_one(
    recipe_id: str, old: str, new: str, expected: int
) -> None:
    result = dict(apply_change(recipe_id, swap(old, new)))
    assert result[new] == expected
    assert old not in result


def test_each_to_each_converts_through_grams() -> None:
    result = apply_change("egg_fried_rice", swap("eggs", "tortillas"))
    assert result[0] == ("tortillas", 4)  # 100 g / 24 g = 4.17


@pytest.mark.parametrize(
    ("ingredient_id", "percent", "expected"),
    [
        ("chicken_breast", 50, 50),
        ("tortillas", 50, 1),
        ("olive_oil", 25, 3),  # 2.5 rounds up
        ("onion", 15, 5),  # 4.5 rounds up
        ("cumin", 150, 2),  # 1.5 rounds up
        ("salt", 10, 1),  # 0.1 is raised to 1
        ("chicken_breast", 10, 10),
        ("chicken_breast", 400, 400),
        ("chicken_breast", 100, 100),
    ],
)
def test_scale_rounds_half_up_with_minimum_one(
    ingredient_id: str, percent: int, expected: int
) -> None:
    result = apply_change("chicken_tacos", scale(ingredient_id, percent))
    assert [item for item, _ in result] == [item for item, _ in TACOS]
    assert dict(result)[ingredient_id] == expected
    others = {key: value for key, value in dict(result).items() if key != ingredient_id}
    assert others == {k: v for k, v in TACOS if k != ingredient_id}


@pytest.mark.parametrize(
    ("recipe_id", "change"),
    [
        ("chicken_tacos", swap("rice", "chickpeas")),
        ("chicken_tacos", swap("chicken_breast", "salsa")),
        ("chicken_tacos", swap("chicken_breast", "chicken_breast")),
        ("chicken_tacos", swap("chicken_breast", "unicorn")),
        ("chicken_tacos", swap("unicorn", "chickpeas")),
        ("chicken_tacos", swap("chicken_breast", "chickpeas", 0)),
        ("chicken_tacos", swap("chicken_breast", "chickpeas", 1001)),
        ("chicken_tacos", swap("chicken_breast", "chickpeas", True)),
        ("chicken_tacos", scale("chicken_breast", 9)),
        ("chicken_tacos", scale("chicken_breast", 401)),
        ("chicken_tacos", scale("chicken_breast", True)),
        ("chicken_tacos", scale("rice", 50)),
        ("chicken_tacos", scale("unicorn", 50)),
        ("chicken_tacos", RecipeChange()),
        ("chicken_tacos", RecipeChange(replace_ingredient_id="chicken_breast")),
        ("chicken_tacos", RecipeChange(with_ingredient_id="chickpeas")),
        ("chicken_tacos", RecipeChange(scale_ingredient_id="salsa")),
        ("chicken_tacos", RecipeChange(scale_factor_percent=50)),
        ("chicken_tacos", RecipeChange(quantity_per_serving=5)),
        (
            "chicken_tacos",
            RecipeChange(
                replace_ingredient_id="chicken_breast",
                with_ingredient_id="chickpeas",
                scale_ingredient_id="salsa",
                scale_factor_percent=50,
            ),
        ),
        (
            "chicken_tacos",
            RecipeChange(
                scale_ingredient_id="salsa",
                scale_factor_percent=50,
                quantity_per_serving=5,
            ),
        ),
        (
            "chicken_tacos",
            RecipeChange(
                replace_ingredient_id="chicken_breast",
                with_ingredient_id="chickpeas",
                scale_factor_percent=50,
            ),
        ),
        (
            "chicken_tacos",
            RecipeChange(
                replace_ingredient_id=["x"],  # type: ignore[arg-type]
                with_ingredient_id="rice",
            ),
        ),
        ("not_a_recipe", swap("chicken_breast", "chickpeas")),
    ],
)
def test_invalid_changes_raise(recipe_id: str, change: RecipeChange) -> None:
    with pytest.raises(RecipeVariantError):
        apply_change(recipe_id, change)


def test_recipe_variant_error_is_value_error() -> None:
    assert issubclass(RecipeVariantError, ValueError)


def test_parse_change_returns_none_without_change_keys() -> None:
    assert parse_change({}) is None
    assert parse_change({"recipe_id": "chicken_tacos", "servings": 2}) is None


def test_parse_change_builds_each_form_and_ignores_other_keys() -> None:
    fields = {"recipe_id": "chicken_tacos", "servings": 2}
    assert parse_change(
        {
            **fields,
            "replace_ingredient_id": "chicken_breast",
            "with_ingredient_id": "eggs",
            "quantity_per_serving": 2,
        }
    ) == swap("chicken_breast", "eggs", 2)
    assert parse_change(
        {**fields, "scale_ingredient_id": "salt", "scale_factor_percent": 50}
    ) == scale("salt", 50)


@pytest.mark.parametrize(
    "fields",
    [
        {"replace_ingredient_id": None},
        {"with_ingredient_id": None},
        {"quantity_per_serving": None},
        {"scale_ingredient_id": None},
        {"scale_factor_percent": None},
        {"replace_ingredient_id": 5},
        {"with_ingredient_id": ["eggs"]},
        {"quantity_per_serving": "5"},
        {"quantity_per_serving": True},
        {"quantity_per_serving": 2.0},
        {"scale_factor_percent": False},
        {"scale_ingredient_id": b"salt"},
    ],
)
def test_parse_change_rejects_wrong_types_and_null(fields: dict[str, object]) -> None:
    with pytest.raises(RecipeVariantError):
        parse_change(fields)


def test_variant_recipes_replaces_only_the_changed_recipe() -> None:
    recipes = variant_recipes({"chicken_tacos": swap("chicken_breast", "chickpeas")})
    assert set(recipes) == set(RECIPES)
    assert recipes["chicken_tacos"].id == "chicken_tacos"
    assert recipes["chicken_tacos"].ingredients == (("chickpeas", 100), *TACOS[1:])
    for recipe_id, recipe in RECIPES.items():
        if recipe_id != "chicken_tacos":
            assert recipes[recipe_id] is recipe
    assert RECIPES["chicken_tacos"].ingredients == TACOS


def test_variant_recipes_without_changes_equals_the_catalog() -> None:
    recipes = variant_recipes({})
    assert recipes == dict(RECIPES)
    assert recipes is not RECIPES


def test_variant_recipes_raises_for_an_invalid_change() -> None:
    with pytest.raises(RecipeVariantError):
        variant_recipes({"chicken_tacos": swap("rice", "eggs")})
