import copy
import json
from dataclasses import replace
from typing import Any, cast

import pytest

from app.agent.plan_tools import execute_get_plan
from app.agent.price_tool import (
    PRICE_TOOL,
    PriceToolError,
    execute_price_lines,
    price_tool_spec,
)
from app.domain.budget import BudgetResult
from app.domain.catalog import RECIPES
from app.domain.curated_foods import ALL_INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS
from app.domain.plan_revision import PlanRevisionInput

BUDGET = BudgetResult(10_000, 250, False, ())
REVISION_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
_SECRET = "do-not-echo-raw-input"
_ESTIMATE_KEYS = {
    "lines",
    "total_cents",
    "price_complete",
    "available_cents",
    "accepted",
    "notice",
}


def meal(recipe_id: str, servings: int = 1, **change: object) -> dict[str, object]:
    return {"recipe_id": recipe_id, "servings": servings, **change}


def price(
    meals: list[dict[str, object]],
    pantry: list[str] | None = None,
    cap: int | None = None,
    budget: BudgetResult = BUDGET,
) -> dict[str, Any]:
    arguments: dict[str, object] = {"meals": meals}
    if pantry is not None:
        arguments["pantry_ingredient_ids"] = pantry
    return cast(dict[str, Any], execute_price_lines(arguments, budget, cap))


def plan_of(
    meals: list[dict[str, object]], pantry: list[str], cap: int
) -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": REVISION_ID,
            "snapshot": {
                "meals": meals,
                "pantry_ingredient_ids": pantry,
                "plan_cap_cents": cap,
            },
        }
    )


def test_omitted_servings_use_plan_or_default() -> None:
    plan = plan_of([meal("chicken_tacos", 2)], [], 5_000)
    result = cast(
        dict[str, Any],
        execute_price_lines(
            {"meals": [{"recipe_id": "chicken_tacos"}, {"recipe_id": "bean_tacos"}]},
            BUDGET,
            None,
            plan,
        ),
    )
    first, second = result["meals"]
    assert (first["servings"], first["servings_source"]) == (2, "plan")
    assert (second["servings"], second["servings_source"]) == (1, "default")
    assert len(result["assumptions"]) == 2
    assert "Servings from your plan: 2." in result["assumptions"][0]
    assert "Servings not given; used 1." in result["assumptions"][1]
    expected = price([meal("chicken_tacos", 2), meal("bean_tacos", 1)])
    assert result["estimate"] == expected["estimate"]


def test_explicit_servings_win_and_add_no_assumption() -> None:
    plan = plan_of([meal("chicken_tacos", 2)], [], 5_000)
    result = cast(
        dict[str, Any],
        execute_price_lines({"meals": [meal("chicken_tacos", 3)]}, BUDGET, None, plan),
    )
    assert result["meals"][0]["servings"] == 3
    assert result["meals"][0]["servings_source"] == "request"
    assert result["assumptions"] == []


def line_of(lines: list[dict[str, Any]], ingredient_id: str) -> dict[str, Any]:
    return next(line for line in lines if line["ingredient_id"] == ingredient_id)


def test_spec_declares_schema_without_extra_keys() -> None:
    spec = cast(dict[str, Any], price_tool_spec()["toolSpec"])
    schema = spec["inputSchema"]["json"]
    assert spec["name"] == PRICE_TOOL == "price_lines"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["meals"]
    assert set(schema["properties"]) == {"meals", "pantry_ingredient_ids"}
    meals = schema["properties"]["meals"]
    assert meals["minItems"] == 1 and meals["maxItems"] == 3
    item = meals["items"]
    assert item["additionalProperties"] is False
    assert item["required"] == ["recipe_id"]
    assert "plan's servings" in spec["description"]
    assert set(item["properties"]) == {
        "recipe_id",
        "servings",
        "replace_ingredient_id",
        "with_ingredient_id",
        "quantity_per_serving",
        "scale_ingredient_id",
        "scale_factor_percent",
    }
    assert item["properties"]["recipe_id"]["enum"] == list(SUPPORTED_RECIPE_IDS)
    assert item["properties"]["servings"]["maximum"] == 8
    pantry = schema["properties"]["pantry_ingredient_ids"]
    help_text = "An ingredient ID from get_ingredient_facts or get_meal."
    assert pantry["items"] == {"type": "string", "description": help_text}
    for name in ("replace_ingredient_id", "with_ingredient_id", "scale_ingredient_id"):
        assert item["properties"][name] == {"type": "string", "description": help_text}


@pytest.mark.parametrize("cap", [5_000, 20_000])
def test_no_change_estimate_equals_get_plan(cap: int) -> None:
    meals = [meal("chicken_tacos", 2), meal("bean_tacos", 1)]
    pantry = ["salt", "onion"]
    expected = execute_get_plan({}, plan_of(meals, pantry, cap), BUDGET)["estimate"]
    result = price(meals, pantry, cap)
    assert result["estimate"] == expected
    assert set(result["estimate"]) == _ESTIMATE_KEYS
    assert result["estimate"]["available_cents"] == min(BUDGET.available_cents, cap)


def test_hand_computed_total_with_pantry() -> None:
    result = price([meal("chicken_tacos", 2)], ["salt"])
    estimate = result["estimate"]
    # One package of each ingredient except the pantry salt.
    assert estimate["total_cents"] == 799 + 299 + 249 + 129 + 199 + 599 == 2274
    salt = line_of(estimate["lines"], "salt")
    assert salt == {
        "ingredient_id": "salt",
        "quantity": 2,
        "unit": "g",
        "packages": 0,
        "cost_cents": 0,
        "from_pantry": True,
    }
    without = price([meal("chicken_tacos", 2)], [])
    assert without["estimate"]["total_cents"] == 2373
    assert price([meal("chicken_tacos", 2)])["estimate"] == without["estimate"]
    assert estimate["price_complete"] is True
    assert estimate["accepted"] is True
    assert estimate["notice"] == SAMPLE_ESTIMATE_NOTICE


def test_swap_prices_the_variant_recipe() -> None:
    swapped = meal(
        "chicken_tacos",
        2,
        replace_ingredient_id="chicken_breast",
        with_ingredient_id="chickpeas",
    )
    result = price([swapped])
    lines = result["estimate"]["lines"]
    assert [line["ingredient_id"] for line in lines] == [
        "chickpeas",
        "cumin",
        "olive_oil",
        "onion",
        "salsa",
        "salt",
        "tortillas",
    ]
    assert line_of(lines, "chickpeas")["quantity"] == 200
    assert line_of(lines, "chickpeas")["cost_cents"] == 129
    assert result["estimate"]["total_cents"] == 2373 - 799 + 129 == 1703
    echoed = result["meals"][0]
    assert echoed["recipe_id"] == "chicken_tacos"
    assert echoed["servings"] == 2
    assert echoed["change"] == {
        "replace_ingredient_id": "chicken_breast",
        "with_ingredient_id": "chickpeas",
    }
    assert echoed["ingredients"][0] == {
        "ingredient_id": "chickpeas",
        "name": "chickpeas",
        "quantity": 100,
        "unit": "g",
    }


def test_scale_prices_the_variant_recipe() -> None:
    scaled = meal(
        "chicken_tacos",
        8,
        scale_ingredient_id="chicken_breast",
        scale_factor_percent=50,
    )
    result = price([scaled])
    chicken = line_of(result["estimate"]["lines"], "chicken_breast")
    assert chicken["quantity"] == 400
    assert chicken["packages"] == 1
    plain = price([meal("chicken_tacos", 8)])
    assert line_of(plain["estimate"]["lines"], "chicken_breast")["packages"] == 2
    assert plain["estimate"]["total_cents"] - result["estimate"]["total_cents"] == 799
    assert result["meals"][0]["change"] == {
        "scale_ingredient_id": "chicken_breast",
        "scale_factor_percent": 50,
    }


def test_meals_without_change_echo_none_and_catalog_ingredients() -> None:
    result = price([meal("bean_tacos", 3)])
    assert set(result) == {"meals", "assumptions", "estimate"}
    echoed = result["meals"][0]
    assert echoed["change"] is None
    assert [(i["ingredient_id"], i["quantity"]) for i in echoed["ingredients"]] == list(
        RECIPES["bean_tacos"].ingredients
    )
    assert echoed["servings"] == 3


def test_shared_ingredients_aggregate_into_one_line() -> None:
    result = price([meal("chicken_tacos"), meal("bean_tacos")])
    lines = result["estimate"]["lines"]
    ids = [line["ingredient_id"] for line in lines]
    assert len(ids) == len(set(ids)) == 8
    tortillas = line_of(lines, "tortillas")
    assert tortillas["quantity"] == 4
    assert tortillas["packages"] == 1
    assert result["estimate"]["total_cents"] == 2502


def test_swap_shares_an_ingredient_with_another_meal() -> None:
    swapped = meal(
        "chicken_tacos",
        1,
        replace_ingredient_id="chicken_breast",
        with_ingredient_id="black_beans",
    )
    result = price([swapped, meal("bean_tacos")])
    lines = result["estimate"]["lines"]
    assert line_of(lines, "black_beans")["quantity"] == 220
    assert "chicken_breast" not in [line["ingredient_id"] for line in lines]
    assert result["estimate"]["total_cents"] == 2502 - 799 == 1703


def test_cap_lowers_available_cents_and_accepts_against_it() -> None:
    capped = price([meal("chicken_tacos", 2)], cap=1_000)["estimate"]
    assert capped["available_cents"] == 1_000
    assert capped["accepted"] is False
    assert capped["total_cents"] == 2373
    roomy = price([meal("chicken_tacos", 2)], cap=50_000)["estimate"]
    assert roomy["available_cents"] == BUDGET.available_cents
    assert roomy["accepted"] is True
    none = price([meal("chicken_tacos", 2)], cap=None)["estimate"]
    assert none["available_cents"] == BUDGET.available_cents
    low = price([meal("chicken_tacos", 2)], budget=BudgetResult(2_000, 0, False, ()))
    assert low["estimate"]["available_cents"] == 2_000
    assert low["estimate"]["accepted"] is False


def test_unpriced_swap_makes_the_estimate_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        ALL_INGREDIENTS,
        "chickpeas",
        replace(ALL_INGREDIENTS["chickpeas"], price_cents=None),
    )
    swapped = meal(
        "chicken_tacos",
        2,
        replace_ingredient_id="chicken_breast",
        with_ingredient_id="chickpeas",
    )
    estimate = price([swapped])["estimate"]
    assert estimate["price_complete"] is False
    assert estimate["total_cents"] is None
    assert estimate["accepted"] is False
    assert line_of(estimate["lines"], "chickpeas")["cost_cents"] is None


def test_inputs_and_catalog_are_not_mutated() -> None:
    swapped = meal(
        "chicken_tacos",
        2,
        replace_ingredient_id="chicken_breast",
        with_ingredient_id="chickpeas",
    )
    arguments: dict[str, object] = {
        "meals": [swapped, meal("bean_tacos")],
        "pantry_ingredient_ids": ["salt"],
    }
    before = copy.deepcopy(arguments)
    recipes = {key: value.ingredients for key, value in RECIPES.items()}
    execute_price_lines(arguments, BUDGET, 5_000)
    assert arguments == before
    assert {key: value.ingredients for key, value in RECIPES.items()} == recipes
    json.dumps(execute_price_lines(arguments, BUDGET, None))


_SWAP = {"replace_ingredient_id": "chicken_breast", "with_ingredient_id": "chickpeas"}


def swap_meal(**override: object) -> dict[str, object]:
    return meal("chicken_tacos", 1, **{**_SWAP, **override})


_FOUR = [
    meal("chicken_tacos"),
    meal("bean_tacos"),
    meal("vegetable_pasta"),
    meal("lentil_soup"),
]


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        "x",
        {},
        {"pantry_ingredient_ids": []},
        {"meals": []},
        {"meals": "chicken_tacos"},
        {"meals": _FOUR},
        {"meals": [meal("chicken_tacos"), meal("chicken_tacos", 2)]},
        {"meals": [meal("chicken_tacos")], "extra": _SECRET},
        {"meals": [{**meal("chicken_tacos"), "extra": _SECRET}]},
        {"meals": ["chicken_tacos"]},
        {"meals": [{"recipe_id": "chicken_tacos", "servings": None}]},
        {"meals": [{"servings": 1}]},
        {"meals": [meal("not_a_recipe")]},
        {"meals": [meal(_SECRET)]},
        {"meals": [{"recipe_id": 1, "servings": 1}]},
        {"meals": [meal("chicken_tacos", 0)]},
        {"meals": [meal("chicken_tacos", 9)]},
        {"meals": [meal("chicken_tacos", True)]},
        {"meals": [meal("chicken_tacos", 1.0)]},
        {"meals": [meal("chicken_tacos")], "pantry_ingredient_ids": ["unicorn"]},
        {"meals": [meal("chicken_tacos")], "pantry_ingredient_ids": [_SECRET]},
        {"meals": [meal("chicken_tacos")], "pantry_ingredient_ids": ["salt", "salt"]},
        {"meals": [meal("chicken_tacos")], "pantry_ingredient_ids": "salt"},
        {"meals": [meal("chicken_tacos")], "pantry_ingredient_ids": None},
        {"meals": [meal("chicken_tacos")], "pantry_ingredient_ids": [["salt"]]},
        {"meals": [meal("chicken_tacos")], "pantry_ingredient_ids": [1]},
        {"meals": [meal("chicken_tacos", 1, replace_ingredient_id="chicken_breast")]},
        {"meals": [swap_meal(with_ingredient_id="unicorn")]},
        {"meals": [swap_meal(with_ingredient_id="salsa")]},
        {"meals": [swap_meal(with_ingredient_id=None)]},
        {"meals": [swap_meal(replace_ingredient_id="rice")]},
        {"meals": [swap_meal(quantity_per_serving=None)]},
        {"meals": [swap_meal(quantity_per_serving=0)]},
        {"meals": [swap_meal(quantity_per_serving="5")]},
        {"meals": [swap_meal(replace_ingredient_id=[_SECRET])]},
        {"meals": [meal("chicken_tacos", 1, scale_ingredient_id="chicken_breast")]},
        {
            "meals": [
                meal(
                    "chicken_tacos",
                    1,
                    scale_ingredient_id="chicken_breast",
                    scale_factor_percent=9,
                )
            ]
        },
        {
            "meals": [
                meal(
                    "chicken_tacos",
                    1,
                    scale_ingredient_id="rice",
                    scale_factor_percent=50,
                )
            ]
        },
        {
            "meals": [
                meal(
                    "chicken_tacos",
                    1,
                    **_SWAP,
                    scale_ingredient_id="salt",
                    scale_factor_percent=50,
                )
            ]
        },
        {"meals": [meal("chicken_tacos", 1, **_SWAP), meal("bean_tacos", 1, **_SWAP)]},
    ],
)
def test_invalid_arguments_raise_static_error(arguments: object) -> None:
    with pytest.raises(PriceToolError) as caught:
        execute_price_lines(arguments, BUDGET, None)
    assert str(caught.value) == "arguments are invalid"
    assert _SECRET not in str(caught.value)
    assert caught.value.__cause__ is None


def test_three_meals_are_accepted() -> None:
    result = price(_FOUR[:3])
    assert [m["recipe_id"] for m in result["meals"]] == [
        "chicken_tacos",
        "bean_tacos",
        "vegetable_pasta",
    ]


def test_error_is_value_error() -> None:
    assert issubclass(PriceToolError, ValueError)


def test_curated_swap_has_no_price_and_the_estimate_is_incomplete() -> None:
    beef = meal(
        "bean_tacos",
        2,
        replace_ingredient_id="black_beans",
        with_ingredient_id="ground_beef_80",
    )
    result = price([beef])
    estimate = result["estimate"]
    assert estimate["price_complete"] is False
    assert estimate["total_cents"] is None
    assert estimate["accepted"] is False
    line = line_of(estimate["lines"], "ground_beef_80")
    assert line["cost_cents"] is None
    assert line["quantity"] == 240
    ingredients = result["meals"][0]["ingredients"]
    assert ingredients[0] == {
        "ingredient_id": "ground_beef_80",
        "name": "ground beef (80% lean)",
        "quantity": 120,
        "unit": "g",
    }
    assert price([meal("bean_tacos", 2)])["estimate"]["price_complete"] is True


def test_curated_food_can_be_a_pantry_item() -> None:
    result = price([meal("bean_tacos")], pantry=["ground_beef_80"])
    assert result["estimate"]["price_complete"] is True


def test_curated_food_cannot_replace_a_recipe_ingredient() -> None:
    arguments = {
        "meals": [
            meal(
                "bean_tacos",
                1,
                replace_ingredient_id="ground_beef_80",
                with_ingredient_id="rice",
            )
        ]
    }
    with pytest.raises(PriceToolError):
        execute_price_lines(arguments, BUDGET, None)
