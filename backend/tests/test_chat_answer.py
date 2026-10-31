from datetime import date
from typing import cast

import pytest

from app.agent import chat_answer
from app.agent.catalog_tool import (
    DISCOVERY_ERROR,
    catalog_answer,
    execute_catalog_search,
)
from app.agent.chat_answer import (
    CLARIFICATION,
    TYPE_CLARIFICATION,
    _vegan_meal_names,
    render_public_answer,
)
from app.agent.planning_tool import execute_plan
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.domain.catalog import Recipe
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS

PERIOD = date(2026, 9, 1)


def test_meal_type_fallback_names_no_recipe() -> None:
    errors: list[dict[str, object] | None] = [
        None,
        {"error": "unsupported tool"},
        {"error_code": "unsupported_recipe"},
    ]
    for error in errors:
        answer = render_public_answer(None, error, meal_type=True)
        assert TYPE_CLARIFICATION in answer
        assert not any(r.replace("_", " ") in answer for r in SUPPORTED_RECIPE_IDS)
    assert render_public_answer(None, meal_type=False) == CLARIFICATION


def _budget(available_cents: int = 10_000, *, stale: bool = False) -> BudgetResult:
    warnings = (STALE_SPENDING_WARNING,) if stale else ()
    return BudgetResult(available_cents, 250, stale, warnings)


def _args(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD.isoformat(),
    }
    values.update(overrides)
    return values


def _usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    magnitude = -cents if cents < 0 else cents
    return f"USD {sign}${magnitude // 100}.{magnitude % 100:02d}"


def _exclusion(
    recipe_id: object = "vegetable_pasta",
    ingredient_id: object = "onion",
    error_code: object = "exclusion_reject",
) -> dict[str, object]:
    return {
        "error": "ingredient is excluded",
        "error_code": error_code,
        "recipe_id": recipe_id,
        "ingredient_id": ingredient_id,
    }


def test_accepted_candidate_uses_plan_total_and_notice() -> None:
    payload = execute_plan(_args(), _budget(), PERIOD)
    plan = payload["plan"]
    assert isinstance(plan, dict)
    total = cast(int, plan["total_cents"])
    answer = render_public_answer(payload)
    assert answer.startswith("The plan is accepted.")
    assert _usd(total) in answer
    assert SAMPLE_ESTIMATE_NOTICE in answer
    assert "The plan is over budget." not in answer
    assert STALE_SPENDING_WARNING not in answer


def test_over_budget_candidate_uses_plan_total() -> None:
    payload = execute_plan(_args(plan_cap_cents=100), _budget(), PERIOD)
    plan = payload["plan"]
    budget = payload["budget"]
    assert isinstance(plan, dict)
    assert isinstance(budget, dict)
    assert plan["accepted"] is False
    total = cast(int, plan["total_cents"])
    available = cast(int, budget["available_cents"])
    answer = render_public_answer(payload)
    assert "The plan is over budget." in answer
    assert _usd(total) in answer
    assert _usd(available) in answer
    assert f"The estimate exceeds the available budget of {_usd(available)}." in answer
    assert SAMPLE_ESTIMATE_NOTICE in answer
    assert "The plan is accepted." not in answer


def test_missing_price_candidate_omits_invented_total() -> None:
    candidate = {
        "plan": {"total_cents": None, "accepted": False},
        "budget": {"stale": False},
    }
    answer = render_public_answer(candidate)
    assert "A purchase price is missing, so this estimate is incomplete." in answer
    assert SAMPLE_ESTIMATE_NOTICE in answer
    assert "USD $" not in answer
    assert "The plan is accepted." not in answer


def test_stale_candidate_keeps_stale_warning() -> None:
    payload = execute_plan(_args(), _budget(stale=True), PERIOD)
    answer = render_public_answer(payload)
    assert STALE_SPENDING_WARNING in answer
    assert SAMPLE_ESTIMATE_NOTICE in answer
    assert "The plan is accepted." in answer


def test_validated_exclusion_names_ingredient_without_ids() -> None:
    answer = render_public_answer(None, _exclusion())
    assert "onion" in answer
    assert "Change the recipe or the restriction." in answer
    assert "vegetable_pasta" not in answer
    assert "ingredient_id" not in answer
    assert CLARIFICATION not in answer
    named = render_public_answer(
        None, _exclusion(recipe_id="chicken_tacos", ingredient_id="chicken_breast")
    )
    assert "chicken breast" in named
    assert "chicken_breast" not in named
    assert "chicken_tacos" not in named


def test_spoofed_exclusion_does_not_echo_identifiers() -> None:
    cases = (
        _exclusion(recipe_id="not_a_recipe", ingredient_id="onion"),
        _exclusion(recipe_id="vegetable_pasta", ingredient_id="peanuts"),
        _exclusion(recipe_id="chicken_tacos", ingredient_id="oats"),
        _exclusion(error_code="not_exclusion"),
        _exclusion(recipe_id=1, ingredient_id="onion"),
        {
            "error": "arguments are invalid",
            "recipe_id": "sushi",
            "ingredient_id": "peanuts",
        },
    )
    for error in cases:
        answer = render_public_answer(None, error)
        assert answer == CLARIFICATION
        dumped = str(error)
        if "not_a_recipe" in dumped:
            assert "not_a_recipe" not in answer
        assert "peanuts" not in answer
        assert "sushi" not in answer
        assert "oats" not in answer


def test_unsupported_recipe_offers_three_vegan_names() -> None:
    error = {
        "error": "recipe is not supported",
        "error_code": "unsupported_recipe",
        "supported_recipe_ids": ["sushi", *SUPPORTED_RECIPE_IDS],
    }
    answer = render_public_answer(None, error)
    assert "bean tacos" in answer
    assert "vegetable pasta" in answer
    assert "lentil soup" in answer
    assert CLARIFICATION in answer
    assert "Which meal should I plan" in answer
    assert "servings" in answer
    assert "restrictions" in answer
    assert "pantry" in answer
    assert "chickpea curry" not in answer
    assert "chicken tacos" not in answer
    assert "sushi" not in answer
    for recipe_id in SUPPORTED_RECIPE_IDS:
        assert recipe_id not in answer
    lowered = answer.lower()
    assert "exclusion" not in lowered
    assert "satisfy" not in lowered
    assert "without peanuts" not in lowered
    assert "fit your" not in lowered


@pytest.mark.parametrize(
    ("recipe_id", "ingredient_id", "diet", "expected"),
    [
        (
            "chicken_tacos",
            "chicken_breast",
            "vegan",
            "Chicken tacos are not vegan. Change the recipe or the restriction.",
        ),
        ("unknown", "chicken_breast", "vegan", CLARIFICATION),
        ("chicken_tacos", "unknown", "vegan", CLARIFICATION),
        ("chicken_tacos", "oats", "vegan", CLARIFICATION),
        ("chicken_tacos", "chicken_breast", "keto", CLARIFICATION),
        ("chicken_tacos", "chicken_breast", "omnivore", CLARIFICATION),
        ("chicken_tacos", "olive_oil", "vegan", CLARIFICATION),
        (1, "chicken_breast", "vegan", CLARIFICATION),
        ("chicken_tacos", [], "vegan", CLARIFICATION),
        ("chicken_tacos", "chicken_breast", [], CLARIFICATION),
    ],
)
def test_diet_conflict_answer_validates_catalog_evidence(
    recipe_id: object, ingredient_id: object, diet: object, expected: str
) -> None:
    error = {
        "error_code": "diet_conflict",
        "recipe_id": recipe_id,
        "ingredient_id": ingredient_id,
        "diet": diet,
    }
    assert render_public_answer(None, error) == expected


def test_diet_conflict_singular_recipe_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        chat_answer,
        "RECIPES",
        {"chicken_bowl": Recipe("chicken_bowl", (("chicken_breast", 100),))},
    )
    error = {
        "error_code": "diet_conflict",
        "recipe_id": "chicken_bowl",
        "ingredient_id": "chicken_breast",
        "diet": "vegetarian",
    }
    assert render_public_answer(None, error) == (
        "Chicken bowl is not vegetarian. Change the recipe or the restriction."
    )


def test_no_tool_and_generic_error_use_static_clarification() -> None:
    assert render_public_answer(None) == CLARIFICATION
    assert render_public_answer(None, {"error": "unsupported tool"}) == CLARIFICATION
    assert "USD" not in CLARIFICATION
    assert "bean tacos" in CLARIFICATION
    assert "vegetable pasta" in CLARIFICATION
    assert "lentil soup" in CLARIFICATION
    assert "Which meal should I plan" in CLARIFICATION
    assert "servings" in CLARIFICATION
    assert "pantry" in CLARIFICATION
    assert "restrictions" in CLARIFICATION
    lowered = CLARIFICATION.lower()
    assert "exclusion" not in lowered
    assert "satisfy" not in lowered
    assert "without peanuts" not in lowered
    assert "fit your" not in lowered


def test_non_int_plan_total_uses_clarification() -> None:
    for total in (17.5, True, "1703"):
        candidate = {"plan": {"accepted": False, "total_cents": total}}
        assert render_public_answer(candidate) == CLARIFICATION


def test_vegan_meal_names_omit_vegetarian_only_recipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        chat_answer,
        "SUPPORTED_RECIPE_IDS",
        ("breakfast_burritos", "bean_tacos", "vegetable_pasta", "lentil_soup"),
    )
    assert _vegan_meal_names() == ["bean tacos", "vegetable pasta", "lentil soup"]


def test_unsupported_diet_offers_catalog_choices() -> None:
    error = {
        "error": "diet is not supported",
        "error_code": "unsupported_diet",
        "supported_diets": ["keto", "paleo"],
    }
    answer = render_public_answer(None, error)
    assert "no preference" in answer
    assert "vegetarian" in answer
    assert "vegan" in answer
    assert "catalog ingredient" in answer
    assert "keto" not in answer
    assert "paleo" not in answer
    assert "diet is not supported" not in answer
    assert CLARIFICATION not in answer


def test_unsupported_ingredient_fields_ask_listed_items() -> None:
    pantry = render_public_answer(
        None,
        {
            "error": "ingredient is not supported",
            "error_code": "unsupported_ingredient",
            "field": "pantry_ingredients",
            "supported_ingredient_ids": ["uranium", "onion"],
        },
    )
    assert pantry == "Name a listed pantry ingredient."
    assert "uranium" not in pantry
    assert "onion" not in pantry
    exclude = render_public_answer(
        None,
        {
            "error": "ingredient is not supported",
            "error_code": "unsupported_ingredient",
            "field": "ingredient_exclusions",
            "ingredient_id": "mystery spice",
            "supported_ingredient_ids": ["peanuts"],
        },
    )
    assert exclude == chat_answer._UNKNOWN_RESTRICTION
    assert exclude == (
        "I cannot map the named restrictions to catalog ingredients. "
        "Which catalog ingredients should I exclude?"
    )
    assert "peanuts" not in exclude
    assert "mystery spice" not in exclude


def test_malformed_typed_errors_use_bounded_clarification() -> None:
    sentinels = (
        "DROP TABLE",
        "<script>",
        "mystery_field",
        "hostile_code",
        "not_a_diet",
        "xyzzy",
    )
    cases: tuple[dict[str, object], ...] = (
        {"error_code": "unsupported_ingredient"},
        {"error_code": "unsupported_ingredient", "field": None},
        {"error_code": "unsupported_ingredient", "field": 1},
        {"error_code": "unsupported_ingredient", "field": "mystery_field"},
        {"error_code": "unsupported_ingredient", "field": "<script>"},
        {"error_code": "hostile_code", "field": "pantry_ingredients"},
        {"error_code": ["unsupported_diet"], "field": "ingredient_exclusions"},
        {
            "error": "DROP TABLE",
            "error_code": "not_a_diet",
            "field": "xyzzy",
            "supported_ingredient_ids": ["DROP TABLE"],
        },
        {},
    )
    for error in cases:
        answer = render_public_answer(None, error)
        assert answer == CLARIFICATION
        for sentinel in sentinels:
            assert sentinel not in answer


def test_discovery_names_match_meal_type_without_a_plan() -> None:
    discovery = execute_catalog_search({"query": "chicken"})
    answer = render_public_answer(None, discovery=discovery)
    assert answer == catalog_answer(discovery)
    ids = cast(list[str], discovery["recipe_ids"])
    assert ids == ["chicken_tacos", "chicken_and_rice_bowls", "chicken_pasta"]
    assert answer.startswith(
        "Catalog choices: Chicken tacos, Chicken and rice bowls, Chicken pasta. "
        "Which one should I plan? "
    )
    assert "bean tacos" not in answer
    assert "Which one should I plan?" in answer
    assert "USD" not in answer
    assert "accepted" not in answer
    for forbidden in ("injected-model-prose", "$", "https://", "Buy", "purchase"):
        assert forbidden not in answer


def test_plan_and_error_take_precedence_over_discovery() -> None:
    discovery = execute_catalog_search({"query": "egg", "diet": "vegetarian"})
    candidate = execute_plan(_args(), _budget(), PERIOD)
    assert render_public_answer(candidate, discovery=discovery) == render_public_answer(
        candidate
    )
    assert render_public_answer(None, _exclusion(), discovery) == render_public_answer(
        None, _exclusion()
    )


def test_discovery_renderer_rejects_injected_fields() -> None:
    discovery = execute_catalog_search({"query": "egg", "diet": "vegetarian"})
    discovery["prose"] = "Buy sushi at https://evil.test for USD $0"
    assert render_public_answer(None, discovery=discovery) == DISCOVERY_ERROR
