import json
from dataclasses import asdict, replace
from datetime import date
from fractions import Fraction
from typing import Any, cast

import pytest

from app.agent.ingredient_tool import resolve_food
from app.agent.substitute_tool import (
    SUBSTITUTE_TOOL,
    SubstituteToolError,
    _percent,
    substitute_tool_spec,
)
from app.agent.substitute_tool import execute_substitute as _execute_substitute
from app.domain.budget import BudgetResult
from app.domain.catalog import RECIPES
from app.domain.curated_foods import ALL_INGREDIENTS, ALL_NUTRITION
from app.domain.grocery import (
    SAMPLE_ESTIMATE_NOTICE,
    SUPPORTED_RECIPE_IDS,
    GroceryRequest,
)
from app.domain.plan_revision import PlanRevisionInput
from app.services.meal_nutrition import (
    GRAMS_PER_EACH,
    MacroTotals,
    MealNutrition,
    ingredients_macros,
    meal_nutrition,
)

_SECRET = "do-not-echo-raw-input"
_KEYS = ("energy_kcal", "protein_mg", "carbohydrate_mg", "fat_mg")


def budget(available_cents: int = 10_000) -> BudgetResult:
    return BudgetResult(available_cents, 250, False, ())


def execute_substitute(
    arguments: object,
    available_cents: int = 10_000,
    plan: PlanRevisionInput | None = None,
) -> dict[str, object]:
    return _execute_substitute(arguments, budget(available_cents), plan)


def plan_with(recipe_id: str, servings: int) -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "snapshot": {
                "meals": [{"recipe_id": recipe_id, "servings": servings}],
                "pantry_ingredient_ids": [],
            },
        }
    )


def swap(**extra: object) -> dict[str, object]:
    args: dict[str, object] = {
        "recipe_id": "chicken_tacos",
        "servings": 2,
        "replace_ingredient_id": "chicken_breast",
        "with_ingredient_id": "chickpeas",
    }
    args.update(extra)
    return args


def scaled(percent: int, ingredient_id: str = "chicken_breast") -> dict[str, object]:
    return {
        "recipe_id": "chicken_tacos",
        "servings": 2,
        "scale_ingredient_id": ingredient_id,
        "scale_factor_percent": percent,
    }


def reference(recipe_id: str, servings: int) -> MealNutrition:
    request = GroceryRequest.model_validate(
        {
            "meals": [{"recipe_id": recipe_id, "servings": servings}],
            "budget_period": date(2026, 9, 1),
        }
    )
    return meal_nutrition(request).meals[0]


def test_spec_declares_schema_without_extra_keys() -> None:
    spec = cast(dict[str, Any], substitute_tool_spec()["toolSpec"])
    schema = spec["inputSchema"]["json"]
    assert spec["name"] == SUBSTITUTE_TOOL == "what_if_substitute"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["recipe_id"]
    assert "plan's servings" in spec["description"]
    props = schema["properties"]
    assert set(props) == {
        "recipe_id",
        "servings",
        "replace_ingredient_id",
        "with_food",
        "with_ingredient_id",
        "quantity_per_serving",
        "scale_ingredient_id",
        "scale_factor_percent",
    }
    assert props["with_food"] == {"type": "string", "minLength": 1, "maxLength": 64}
    assert "with_food" in spec["description"]
    assert "protein" in spec["description"]
    assert props["recipe_id"]["enum"] == list(SUPPORTED_RECIPE_IDS)
    assert props["servings"] == {"type": "integer", "minimum": 1, "maximum": 8}
    for name in ("replace_ingredient_id", "with_ingredient_id", "scale_ingredient_id"):
        assert props[name] == {
            "type": "string",
            "description": "An ingredient ID from get_ingredient_facts or get_meal.",
        }
    assert props["quantity_per_serving"]["minimum"] == 1
    assert props["quantity_per_serving"]["maximum"] == 1000
    assert props["scale_factor_percent"]["minimum"] == 10
    assert props["scale_factor_percent"]["maximum"] == 400


def test_chicken_to_chickpeas_matches_independent_macros() -> None:
    result = execute_substitute(swap())
    before_meal = reference("chicken_tacos", 2)
    hand_list = (("chickpeas", 100), *RECIPES["chicken_tacos"].ingredients[1:])
    after_each = ingredients_macros(hand_list)
    after_total = ingredients_macros(hand_list, servings=2)
    assert after_each is not None and after_total is not None
    assert result["recipe_id"] == "chicken_tacos"
    assert result["servings"] == 2
    assert result["change"] == {
        "replace_ingredient_id": "chicken_breast",
        "with_ingredient_id": "chickpeas",
    }
    before = cast(dict[str, Any], result["before"])
    after = cast(dict[str, Any], result["after"])
    assert before["per_serving"] == asdict(before_meal.per_serving)
    assert before["total"] == asdict(before_meal.total)
    assert after["per_serving"] == asdict(after_each)
    assert after["total"] == asdict(after_total)
    assert before["ingredients"][0] == {
        "ingredient_id": "chicken_breast",
        "name": "chicken breast",
        "quantity": 100,
        "unit": "g",
    }
    assert after["ingredients"][0] == {
        "ingredient_id": "chickpeas",
        "name": "chickpeas",
        "quantity": 100,
        "unit": "g",
    }
    assert [i["ingredient_id"] for i in after["ingredients"]] == [
        item for item, _ in hand_list
    ]
    delta = cast(dict[str, Any], result["delta"])
    for key in _KEYS:
        assert (
            delta["per_serving"][key]
            == after["per_serving"][key] - before["per_serving"][key]
        )
        assert delta["total"][key] == after["total"][key] - before["total"][key]
    assert delta["per_serving"]["protein_mg"] < 0
    assert result["diets_after"] == ["vegan", "vegetarian"]
    assert result["assumptions"] == ["Same weight per serving: 100 g."]
    json.dumps(result)


def test_total_comes_from_unrounded_sums() -> None:
    result = execute_substitute(swap(servings=3))
    after = cast(dict[str, Any], result["after"])
    hand_list = (("chickpeas", 100), *RECIPES["chicken_tacos"].ingredients[1:])
    total = ingredients_macros(hand_list, servings=3)
    assert total is not None
    assert after["total"] == asdict(total)
    before = cast(dict[str, Any], result["before"])
    assert before["total"] == asdict(reference("chicken_tacos", 3).total)


def test_delta_percent_matches_independent_rounding() -> None:
    result = execute_substitute(swap())
    before = cast(dict[str, Any], result["before"])["per_serving"]
    delta = cast(dict[str, Any], result["delta"])["per_serving"]
    percent = cast(dict[str, Any], result["delta_percent"])
    assert set(percent) == set(_KEYS)
    for key in _KEYS:
        ratio = Fraction(abs(delta[key]) * 100, before[key])
        magnitude = int(ratio + Fraction(1, 2))
        assert percent[key] == (-magnitude if delta[key] < 0 else magnitude)
    assert percent["protein_mg"] < 0


@pytest.mark.parametrize(
    ("delta", "base", "expected"),
    [
        (1, 3, 33),
        (-1, 3, -33),
        (1, 6, 17),
        (-1, 6, -17),
        (1, 200, 1),
        (-1, 200, -1),
        (0, 10, 0),
        (100, 100, 100),
        (-100, 100, -100),
        (5, 0, None),
        (-5, 0, None),
    ],
)
def test_percent_rounds_symmetrically(
    delta: int, base: int, expected: int | None
) -> None:
    assert _percent(delta, base) == expected


def test_g_to_each_uses_grams_per_each_and_half_up() -> None:
    result = execute_substitute(
        {
            "recipe_id": "chicken_and_rice_bowls",
            "servings": 1,
            "replace_ingredient_id": "rice",
            "with_ingredient_id": "eggs",
        }
    )
    after = cast(dict[str, Any], result["after"])
    line = next(i for i in after["ingredients"] if i["ingredient_id"] == "eggs")
    assert line == {
        "ingredient_id": "eggs",
        "name": "eggs",
        "quantity": 2,
        "unit": "each",
    }
    assert result["assumptions"] == [
        "Closest whole amount: 2 each (100 g) per serving instead of 75 g."
    ]
    hand = tuple(
        ("eggs", 2) if item == "rice" else (item, qty)
        for item, qty in RECIPES["chicken_and_rice_bowls"].ingredients
    )
    expected = ingredients_macros(hand)
    assert expected is not None
    assert after["per_serving"] == asdict(expected)


def test_each_to_g_assumption_reports_grams() -> None:
    result = execute_substitute(
        swap(replace_ingredient_id="tortillas", with_ingredient_id="rice")
    )
    after = cast(dict[str, Any], result["after"])
    assert after["ingredients"][1]["quantity"] == 48
    assert result["assumptions"] == ["Same weight per serving: 48 g."]


def test_explicit_quantity_assumption_and_echo() -> None:
    each = execute_substitute(swap(with_ingredient_id="eggs", quantity_per_serving=2))
    assert each["assumptions"] == ["Quantity set to 2 each per serving."]
    assert each["change"] == {
        "replace_ingredient_id": "chicken_breast",
        "with_ingredient_id": "eggs",
        "quantity_per_serving": 2,
    }
    after = cast(dict[str, Any], each["after"])
    assert after["ingredients"][0]["quantity"] == 2
    grams = execute_substitute(swap(quantity_per_serving=150))
    assert grams["assumptions"] == ["Quantity set to 150 g per serving."]
    hand = (("chickpeas", 150), *RECIPES["chicken_tacos"].ingredients[1:])
    expected = ingredients_macros(hand)
    assert expected is not None
    assert cast(dict[str, Any], grams["after"])["per_serving"] == asdict(expected)


def test_scale_halves_with_half_up_and_minimum_one() -> None:
    result = execute_substitute(scaled(50))
    assert result["assumptions"] == ["Scaled to 50 percent."]
    assert result["change"] == {
        "scale_ingredient_id": "chicken_breast",
        "scale_factor_percent": 50,
    }
    after = cast(dict[str, Any], result["after"])
    assert after["ingredients"][0]["quantity"] == 50
    delta = cast(dict[str, Any], result["delta"])["per_serving"]
    assert all(delta[key] <= 0 for key in _KEYS)
    assert delta["protein_mg"] < 0
    oil = execute_substitute(scaled(25, "olive_oil"))
    quantity = cast(dict[str, Any], oil["after"])["ingredients"][5]["quantity"]
    assert quantity == 3
    assert oil["assumptions"] == ["Scaled to 25 percent."]
    tiny = execute_substitute(scaled(10, "salt"))
    assert cast(dict[str, Any], tiny["after"])["ingredients"][6]["quantity"] == 1
    assert tiny["assumptions"] == ["Scaled to the minimum of 1 g per serving."]
    assert result["diets_after"] == []


def test_default_substitute_reports_the_closest_whole_amount() -> None:
    result = execute_substitute(
        {
            "recipe_id": "chicken_and_rice_bowls",
            "servings": 1,
            "replace_ingredient_id": "rice",
            "with_ingredient_id": "potato",
        }
    )
    assert result["assumptions"] == [
        "Closest whole amount: 1 each (213 g) per serving instead of 75 g."
    ]


def test_scale_that_rounds_to_the_stored_amount_keeps_the_percent_sentence() -> None:
    result = execute_substitute(scaled(150, "olive_oil"))
    quantity = cast(dict[str, Any], result["after"])["ingredients"][5]["quantity"]
    assert quantity == 15
    assert result["assumptions"] == ["Scaled to 150 percent."]


def test_scale_hundred_percent_has_zero_delta() -> None:
    result = execute_substitute(scaled(100))
    delta = cast(dict[str, Any], result["delta"])
    assert all(delta["per_serving"][key] == 0 for key in _KEYS)
    assert all(delta["total"][key] == 0 for key in _KEYS)
    assert all(v == 0 for v in cast(dict[str, Any], result["delta_percent"]).values())


def test_diets_after_requires_every_remaining_ingredient() -> None:
    eggs = execute_substitute(
        {
            "recipe_id": "bean_tacos",
            "servings": 1,
            "replace_ingredient_id": "black_beans",
            "with_ingredient_id": "eggs",
        }
    )
    assert eggs["diets_after"] == ["vegetarian"]
    chicken = execute_substitute(
        {
            "recipe_id": "bean_tacos",
            "servings": 1,
            "replace_ingredient_id": "black_beans",
            "with_ingredient_id": "chicken_breast",
        }
    )
    assert chicken["diets_after"] == []
    vegan = execute_substitute(
        {
            "recipe_id": "chicken_chickpea_skillet",
            "servings": 1,
            "replace_ingredient_id": "chicken_breast",
            "with_ingredient_id": "lentils",
        }
    )
    assert vegan["diets_after"] == ["vegan", "vegetarian"]


def test_inputs_and_catalog_are_not_mutated() -> None:
    args = swap()
    before = json.dumps(args, sort_keys=True)
    recipes = {key: value.ingredients for key, value in RECIPES.items()}
    execute_substitute(args)
    assert json.dumps(args, sort_keys=True) == before
    assert {key: value.ingredients for key, value in RECIPES.items()} == recipes


def test_payload_has_a_price_block_and_no_evidence_fields() -> None:
    result = execute_substitute(swap())
    assert set(result) == {
        "status",
        "recipe_id",
        "servings",
        "servings_source",
        "change",
        "before",
        "after",
        "delta",
        "delta_percent",
        "diets_after",
        "assumptions",
        "price",
    }
    assert set(cast(dict[str, Any], result["price"])) == {
        "before",
        "after",
        "delta_cents",
    }
    assert "evidence" not in json.dumps(result)


def test_price_block_matches_hand_computed_package_math() -> None:
    price = cast(dict[str, Any], execute_substitute(swap())["price"])
    # Two servings of tacos, one package of each ingredient.
    before_total = 799 + 299 + 249 + 129 + 199 + 599 + 99
    after_total = before_total - 799 + 129
    assert before_total == 2373
    assert price["before"]["total_cents"] == before_total
    assert price["after"]["total_cents"] == after_total == 1703
    assert price["delta_cents"] == after_total - before_total == -670
    after_ids = [line["ingredient_id"] for line in price["after"]["lines"]]
    before_ids = [line["ingredient_id"] for line in price["before"]["lines"]]
    assert "chickpeas" in after_ids and "chicken_breast" not in after_ids
    assert "chicken_breast" in before_ids and "chickpeas" not in before_ids
    chickpeas = next(
        line for line in price["after"]["lines"] if line["ingredient_id"] == "chickpeas"
    )
    assert chickpeas == {
        "ingredient_id": "chickpeas",
        "quantity": 200,
        "unit": "g",
        "packages": 1,
        "cost_cents": 129,
        "from_pantry": False,
    }
    for side in ("before", "after"):
        assert price[side]["price_complete"] is True
        assert price[side]["available_cents"] == 10_000
        assert price[side]["accepted"] is True
        assert price[side]["notice"] == SAMPLE_ESTIMATE_NOTICE
        assert not any(line["from_pantry"] for line in price[side]["lines"])


def test_price_block_scales_with_servings() -> None:
    price = cast(dict[str, Any], execute_substitute(swap(servings=8))["price"])
    # Eight servings: chicken 800 g is 2 packages, tortillas 16 is 2 packages,
    # chickpeas 800 g is 2 packages, and the rest stay at one package.
    before_total = 2 * 799 + 2 * 299 + 249 + 129 + 199 + 599 + 99
    after_total = before_total - 2 * 799 + 2 * 129
    assert price["before"]["total_cents"] == before_total == 3471
    assert price["after"]["total_cents"] == after_total == 2131
    assert price["delta_cents"] == -1340


def test_price_block_compares_each_side_with_the_budget() -> None:
    price = cast(
        dict[str, Any], execute_substitute(swap(), available_cents=2000)["price"]
    )
    assert price["before"]["available_cents"] == 2000
    assert price["before"]["accepted"] is False
    assert price["after"]["accepted"] is True


def test_swap_to_an_unpriced_ingredient_leaves_delta_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        ALL_INGREDIENTS,
        "chickpeas",
        replace(ALL_INGREDIENTS["chickpeas"], price_cents=None),
    )
    price = cast(dict[str, Any], execute_substitute(swap())["price"])
    assert price["before"]["price_complete"] is True
    assert price["after"]["price_complete"] is False
    assert price["after"]["total_cents"] is None
    assert price["after"]["accepted"] is False
    chickpeas = next(
        line for line in price["after"]["lines"] if line["ingredient_id"] == "chickpeas"
    )
    assert chickpeas["cost_cents"] is None
    assert price["delta_cents"] is None


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        "x",
        {},
        {"recipe_id": "chicken_tacos"},
        {"servings": 1},
        swap(replace_ingredient_id="rice"),
        swap(with_ingredient_id="salsa"),
        swap(with_ingredient_id="chicken_breast"),
        swap(with_ingredient_id="unicorn"),
        swap(replace_ingredient_id="unicorn"),
        swap(recipe_id="not_a_recipe"),
        swap(recipe_id=1),
        swap(scale_ingredient_id="salsa", scale_factor_percent=50),
        swap(replace_ingredient_id=None, with_ingredient_id=None),
        swap(quantity_per_serving=None),
        swap(scale_ingredient_id=None),
        {**scaled(50), "scale_factor_percent": None},
        {**scaled(50), "quantity_per_serving": None},
        {"recipe_id": "chicken_tacos", "servings": 1},
        swap(quantity_per_serving=0),
        swap(quantity_per_serving=1001),
        swap(quantity_per_serving="5"),
        swap(quantity_per_serving=True),
        scaled(9),
        scaled(401),
        scaled(50, "rice"),
        scaled(True),
        {**scaled(50), "quantity_per_serving": 5},
        {**scaled(50), "with_ingredient_id": "rice"},
        {"recipe_id": "chicken_tacos", "servings": 1, "scale_ingredient_id": "salsa"},
        swap(servings=None),
        swap(servings=0),
        swap(servings=9),
        swap(servings=True),
        swap(servings="2"),
        swap(servings=2.0),
        swap(extra=_SECRET),
        swap(replace_ingredient_id=[_SECRET]),
        {"recipe_id": "bean_tacos", "replace_ingredient_id": "black_beans"},
        {"recipe_id": "bean_tacos", "with_ingredient_id": "ground_beef_80"},
    ],
)
def test_invalid_arguments_raise_static_error(arguments: object) -> None:
    with pytest.raises(SubstituteToolError) as caught:
        execute_substitute(arguments)
    assert str(caught.value) == "arguments are invalid"
    assert _SECRET not in str(caught.value)
    assert caught.value.__cause__ is None


def _without_servings() -> dict[str, object]:
    args = swap()
    del args["servings"]
    return args


def test_omitted_servings_use_the_plan() -> None:
    result = execute_substitute(_without_servings(), plan=plan_with("chicken_tacos", 2))
    assert result["servings"] == 2
    assert result["servings_source"] == "plan"
    assert "Servings from your plan: 2." in cast(list[str], result["assumptions"])
    expected = execute_substitute(swap(servings=2))
    assert result["after"] == expected["after"]
    assert result["delta"] == expected["delta"]


def test_explicit_servings_win_over_the_plan() -> None:
    result = execute_substitute(swap(servings=3), plan=plan_with("chicken_tacos", 2))
    assert result["servings"] == 3
    assert result["servings_source"] == "request"
    assert not any(
        "Servings" in item for item in cast(list[str], result["assumptions"])
    )


def test_omitted_servings_without_a_plan_meal_default_to_one() -> None:
    for plan in (None, plan_with("vegetable_stir_fry", 4)):
        result = execute_substitute(_without_servings(), plan=plan)
        assert result["servings"] == 1
        assert result["servings_source"] == "default"
        assert "Servings not given; used 1." in cast(list[str], result["assumptions"])


@pytest.mark.parametrize("servings", [1, 8])
@pytest.mark.parametrize("quantity", [1, 1000])
def test_range_edges_are_accepted(servings: int, quantity: int) -> None:
    result = execute_substitute(swap(servings=servings, quantity_per_serving=quantity))
    assert result["servings"] == servings


@pytest.mark.parametrize("percent", [10, 400])
def test_scale_range_edges_are_accepted(percent: int) -> None:
    assert execute_substitute(scaled(percent))["servings"] == 2


def test_error_is_value_error() -> None:
    assert issubclass(SubstituteToolError, ValueError)


def beef_swap(**extra: object) -> dict[str, object]:
    args: dict[str, object] = {
        "recipe_id": "bean_tacos",
        "servings": 2,
        "replace_ingredient_id": "black_beans",
        "with_ingredient_id": "ground_beef_80",
    }
    args.update(extra)
    return args


def hand_macros(items: tuple[tuple[str, int], ...], servings: int = 1) -> MacroTotals:
    """Sum grams x per-gram facts from ALL_NUTRITION, rounding once at the end."""
    sums = [0, 0, 0, 0]
    for ingredient_id, quantity in items:
        grams = quantity
        if ALL_INGREDIENTS[ingredient_id].unit == "each":
            grams = quantity * GRAMS_PER_EACH[ingredient_id]
        facts = ALL_NUTRITION[ingredient_id]
        sums[0] += facts.energy_kcal * grams
        sums[1] += facts.protein_mg * grams
        sums[2] += facts.carbohydrate_mg * grams
        sums[3] += facts.fat_mg * grams
    a, b, c, d = ((value * servings + 50) // 100 for value in sums)
    return MacroTotals(a, b, c, d)


def test_hand_macros_matches_ingredients_macros_for_catalog_items() -> None:
    items = RECIPES["bean_tacos"].ingredients
    assert hand_macros(items, 2) == ingredients_macros(items, servings=2)


def test_bean_tacos_to_curated_beef_uses_curated_nutrition() -> None:
    result = execute_substitute(beef_swap())
    hand_list = (("ground_beef_80", 120), *RECIPES["bean_tacos"].ingredients[1:])
    each = hand_macros(hand_list)
    total = hand_macros(hand_list, 2)
    assert result["assumptions"] == ["Same weight per serving: 120 g."]
    before = cast(dict[str, Any], result["before"])
    after = cast(dict[str, Any], result["after"])
    assert after["per_serving"] == asdict(each)
    assert after["total"] == asdict(total)
    assert after["ingredients"][0] == {
        "ingredient_id": "ground_beef_80",
        "name": "ground beef (80% lean)",
        "quantity": 120,
        "unit": "g",
    }
    assert before["per_serving"] == asdict(reference("bean_tacos", 2).per_serving)
    delta = cast(dict[str, Any], result["delta"])
    for key in _KEYS:
        assert (
            delta["per_serving"][key]
            == after["per_serving"][key] - (before["per_serving"][key])
        )
        assert delta["total"][key] == after["total"][key] - before["total"][key]
    assert delta["per_serving"]["fat_mg"] > 0
    assert result["diets_after"] == []
    assert result["change"] == {
        "replace_ingredient_id": "black_beans",
        "with_ingredient_id": "ground_beef_80",
    }


def test_curated_swap_price_is_incomplete() -> None:
    price = cast(dict[str, Any], execute_substitute(beef_swap())["price"])
    assert price["before"]["price_complete"] is True
    assert price["after"]["price_complete"] is False
    assert price["after"]["total_cents"] is None
    assert price["delta_cents"] is None
    beef = next(
        line
        for line in price["after"]["lines"]
        if line["ingredient_id"] == "ground_beef_80"
    )
    assert beef["cost_cents"] is None
    assert beef["quantity"] == 240


@pytest.mark.parametrize(
    "arguments",
    [
        beef_swap(replace_ingredient_id="ground_beef_80", with_ingredient_id="rice"),
        beef_swap(replace_ingredient_id="ground_beef_80", with_ingredient_id="salsa"),
        {
            "recipe_id": "bean_tacos",
            "servings": 1,
            "scale_ingredient_id": "ground_beef_80",
            "scale_factor_percent": 50,
        },
        beef_swap(with_ingredient_id="ground_beef_999"),
    ],
)
def test_curated_foods_cannot_be_recipe_ingredients(arguments: object) -> None:
    with pytest.raises(SubstituteToolError) as caught:
        execute_substitute(arguments)
    assert str(caught.value) == "arguments are invalid"


def food_swap(**extra: object) -> dict[str, object]:
    args: dict[str, object] = {"recipe_id": "bean_tacos", "with_food": "beef"}
    args.update(extra)
    return args


def candidates_of(result: dict[str, object]) -> list[tuple[str, str]]:
    items = cast(list[dict[str, str]], result["candidates"])
    return [(item["ingredient_id"], item["name"]) for item in items]


@pytest.mark.parametrize("food", ["beef", "Ground Beef", "  GROUND   beef "])
def test_with_food_swaps_the_only_protein_like_the_explicit_ids(food: str) -> None:
    plan = plan_with("bean_tacos", 2)
    result = execute_substitute(food_swap(with_food=food), plan=plan)
    expected = execute_substitute(beef_swap())
    assert result["status"] == "swapped"
    assert result["servings"] == 2
    assert result["servings_source"] == "plan"
    assert result["change"] == {
        "replace_ingredient_id": "black_beans",
        "with_ingredient_id": "ground_beef_80",
    }
    for key in ("before", "after", "delta", "delta_percent", "diets_after", "price"):
        assert result[key] == expected[key]
    assert "with_food" not in json.dumps(result["change"])


def test_explicit_id_and_scale_forms_gain_only_the_swapped_status() -> None:
    explicit = execute_substitute(beef_swap())
    assert explicit["status"] == "swapped"
    assert execute_substitute(scaled(50))["status"] == "swapped"
    assert execute_substitute(food_swap(servings=3))["servings_source"] == "request"


def test_with_food_with_a_given_replacement_swaps_even_with_two_proteins() -> None:
    result = execute_substitute(
        food_swap(recipe_id="chicken_lentil_stew", replace_ingredient_id="lentils")
    )
    assert result["status"] == "swapped"
    assert result["change"] == {
        "replace_ingredient_id": "lentils",
        "with_ingredient_id": "ground_beef_80",
    }


def test_with_food_honors_an_explicit_quantity() -> None:
    result = execute_substitute(food_swap(quantity_per_serving=150))
    assert result["assumptions"] == [
        "Quantity set to 150 g per serving.",
        "Servings not given; used 1.",
    ]


def test_ambiguous_food_asks_which_food_and_does_not_swap() -> None:
    result = execute_substitute(food_swap(with_food="pork"))
    assert set(result) == {"status", "recipe_id", "candidates"}
    assert result["status"] == "needs_food_choice"
    assert result["recipe_id"] == "bean_tacos"
    assert sorted(name for _, name in candidates_of(result)) == [
        "ground pork",
        "pork loin",
    ]
    assert [item for item, _ in candidates_of(result)] == list(resolve_food("pork").ids)


def test_unknown_food_returns_candidates_and_no_swap() -> None:
    result = execute_substitute(food_swap(with_food="tofu"))
    assert result == {
        "status": "unknown_food",
        "recipe_id": "bean_tacos",
        "candidates": [],
    }
    near = execute_substitute(food_swap(with_food="beef stew"))
    assert near["status"] == "unknown_food"
    assert candidates_of(near)[0] == ("ground_beef_80", "ground beef (80% lean)")


def test_no_protein_in_the_recipe_asks_for_the_ingredient_to_replace() -> None:
    result = execute_substitute(food_swap(recipe_id="vegetable_pasta"))
    assert set(result) == {"status", "recipe_id", "candidates"}
    assert result["status"] == "needs_ingredient_choice"
    assert result["recipe_id"] == "vegetable_pasta"
    assert candidates_of(result) == [
        (item, ALL_INGREDIENTS[item].name)
        for item, _ in RECIPES["vegetable_pasta"].ingredients
    ]


def test_two_proteins_ask_instead_of_picking_the_first() -> None:
    result = execute_substitute(food_swap(recipe_id="chicken_lentil_stew"))
    assert result["status"] == "needs_ingredient_choice"
    assert candidates_of(result) == [
        ("chicken_breast", "chicken breast"),
        ("lentils", "brown lentils"),
    ]


def test_with_food_and_a_replacement_in_a_meal_without_protein_swaps() -> None:
    result = execute_substitute(
        food_swap(recipe_id="vegetable_pasta", replace_ingredient_id="pasta")
    )
    assert result["status"] == "swapped"


@pytest.mark.parametrize(
    "arguments",
    [
        food_swap(with_ingredient_id="ground_beef_80"),
        food_swap(with_food=""),
        food_swap(with_food="a" * 65),
        food_swap(with_food="   "),
        food_swap(with_food=None),
        food_swap(with_food=5),
        food_swap(with_food=["beef"]),
        food_swap(scale_ingredient_id="black_beans", scale_factor_percent=50),
        food_swap(servings=0),
        food_swap(replace_ingredient_id="salsa_not_here"),
        food_swap(replace_ingredient_id=_SECRET),
        food_swap(with_food="black beans"),
        food_swap(extra=_SECRET),
    ],
)
def test_invalid_with_food_arguments_raise_static_error(arguments: object) -> None:
    with pytest.raises(SubstituteToolError) as caught:
        execute_substitute(arguments)
    assert str(caught.value) == "arguments are invalid"
    assert _SECRET not in str(caught.value)
    assert caught.value.__cause__ is None


def test_with_food_length_edges_are_accepted() -> None:
    assert execute_substitute(food_swap(with_food="a"))["status"] == "unknown_food"
    long = execute_substitute(food_swap(with_food="a" * 64))
    assert long["status"] == "unknown_food"


@pytest.mark.parametrize(
    "arguments",
    [
        food_swap(with_food="tofu"),
        food_swap(with_food=_SECRET),
        food_swap(recipe_id="vegetable_pasta", with_food=_SECRET + " beef"),
        food_swap(recipe_id="chicken_lentil_stew", with_food="beef"),
    ],
)
def test_question_payloads_never_contain_the_input_text(
    arguments: dict[str, object],
) -> None:
    result = execute_substitute(arguments)
    assert result["status"] != "swapped"
    assert str(arguments["with_food"]) not in json.dumps(result)
