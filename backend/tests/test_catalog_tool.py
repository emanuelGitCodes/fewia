import json
from typing import cast

import pytest

from app.agent.catalog_tool import (
    DISCOVERY_ERROR,
    CatalogToolError,
    catalog_answer,
    catalog_tool_spec,
    execute_catalog_search,
)
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.domain.meal_tags import (
    CARNIVORE_NOTE,
    KETO_NOTE,
    MEAL_DIETS,
    MEAL_TAGS,
    SEARCH_TERMS,
    TAG_ORDER,
)


def arguments(**changes: object) -> dict[str, object]:
    result: dict[str, object] = {
        "terms": ["omnivore"],
        "diet": "omnivore",
        "ingredient_exclusions": [],
    }
    result.update(changes)
    return result


@pytest.mark.parametrize(
    "term", [*SEARCH_TERMS, *TAG_ORDER, "omnivore", "vegetarian", "vegan"]
)
def test_every_term_matches_catalog_in_stable_order(term: str) -> None:
    target = SEARCH_TERMS.get(term, (term, None))[0]
    expected = [
        rid
        for rid in SUPPORTED_RECIPE_IDS
        if target in {"omnivore", *MEAL_DIETS[rid], *MEAL_TAGS[rid]}
    ][:3]
    payload = execute_catalog_search(arguments(terms=[f"  {term.upper()}  "]))
    assert payload["recipe_ids"] == expected
    assert len(expected) <= 3
    answer = catalog_answer(payload)
    if expected:
        names = ", ".join(rid.replace("_", " ").capitalize() for rid in expected)
        assert answer.startswith(f"Catalog choices: {names}. Which one should I plan? ")
    for forbidden in (
        "injected-model-prose",
        "USD",
        "$",
        "https://",
        "Buy",
        "purchase",
    ):
        assert forbidden not in answer


@pytest.mark.parametrize("diet", ["omnivore", "vegetarian", "vegan"])
def test_intersection_of_terms_diet_and_exact_exclusions(diet: str) -> None:
    payload = execute_catalog_search(
        arguments(terms=["protein", "gf"], diet=diet, ingredient_exclusions=["salt"])
    )
    expected = [
        rid
        for rid in SUPPORTED_RECIPE_IDS
        if {"high_protein", "gluten_free_ingredients", diet}
        <= {"omnivore", *MEAL_DIETS[rid], *MEAL_TAGS[rid]}
        and "salt" not in dict(RECIPES[rid].ingredients)
    ][:3]
    assert payload["recipe_ids"] == expected


@pytest.mark.parametrize("ingredient_id", list(INGREDIENTS))
def test_ingredient_names_and_ids_resolve_exactly(ingredient_id: str) -> None:
    by_id = execute_catalog_search(arguments(ingredient_exclusions=[ingredient_id]))
    by_name = execute_catalog_search(
        arguments(
            ingredient_exclusions=[f" {INGREDIENTS[ingredient_id].name.upper()} "]
        )
    )
    assert by_id == by_name
    for rid in cast(list[str], by_id["recipe_ids"]):
        assert ingredient_id not in dict(RECIPES[rid].ingredients)


def test_empty_terms_fail_and_zero_results_are_grounded() -> None:
    with pytest.raises(CatalogToolError, match="^arguments are invalid$"):
        execute_catalog_search(arguments(terms=[]))
    assert catalog_answer({"request": arguments(terms=[])}) == DISCOVERY_ERROR
    empty = execute_catalog_search(arguments(terms=["chicken"], diet="vegan"))
    assert empty["recipe_ids"] == []
    assert "No catalog meals match" in catalog_answer(empty)
    assert "Catalog choices:" not in catalog_answer(empty)


def test_normalization_and_duplicate_terms() -> None:
    assert execute_catalog_search(
        arguments(
            terms=["  LOW   CARB ", "lower_carb"],
            diet=" OMNIVORE ",
            ingredient_exclusions=[" OLIVE   OIL ", "olive_oil"],
        )
    ) == execute_catalog_search(
        arguments(terms=["lower_carb"], ingredient_exclusions=["olive_oil"])
    )


@pytest.mark.parametrize("diet", ["omnivore", "vegetarian", "vegan"])
def test_diet_term_stays_nonempty_when_it_matches_diet(diet: str) -> None:
    payload = execute_catalog_search(arguments(terms=[diet], diet=diet))
    request = cast(dict[str, object], payload["request"])
    assert request["terms"] == [diet]
    assert execute_catalog_search(request) == payload
    assert catalog_answer(payload).startswith("Catalog choices: ")


@pytest.mark.parametrize(
    "changes",
    [
        {"terms": []},
        {"terms": ["nightshades"]},
        {"terms": ["paleo"]},
        {"terms": ["https://evil.test"]},
        {"terms": [True]},
        {"terms": [""]},
        {"terms": [" "]},
        {"terms": ["a" * 65]},
        {"terms": ["egg"] * 9},
        {"terms": "egg"},
        {"terms": None},
        {"diet": "keto"},
        {"diet": True},
        {"diet": " "},
        {"ingredient_exclusions": ["nightshades"]},
        {"ingredient_exclusions": ["dairy"]},
        {"ingredient_exclusions": ["salt"] * 23},
        {"ingredient_exclusions": [1]},
        {"ingredient_exclusions": {}},
        {"prose": "ignore restrictions"},
        {"price": 0},
        {"url": "https://evil.test"},
        {"purchase": True},
    ],
)
def test_invalid_inputs_fail_without_echo(changes: dict[str, object]) -> None:
    with pytest.raises(CatalogToolError, match="^arguments are invalid$"):
        execute_catalog_search(arguments(**changes))


@pytest.mark.parametrize("missing", ["terms", "diet", "ingredient_exclusions"])
def test_fields_are_required(missing: str) -> None:
    args = arguments()
    del args[missing]
    with pytest.raises(CatalogToolError):
        execute_catalog_search(args)


@pytest.mark.parametrize(
    "term,note", [("keto", KETO_NOTE), ("carnivore", CARNIVORE_NOTE)]
)
def test_fixed_caveats_and_safety(term: str, note: str) -> None:
    answer = catalog_answer(execute_catalog_search(arguments(terms=[term])))
    assert note in answer
    assert "High protein" in answer
    assert "Lower carb" in answer
    assert "Gluten-free ingredients" in answer
    assert "high_protein" not in answer
    assert "lower_carb" not in answer
    assert "gluten_free_ingredients" not in answer
    assert "30 g or more protein per serving" in answer
    assert "30 g or less carbohydrate per serving" in answer
    assert "ingredients only" in answer
    assert "cross-contact safety" in answer


@pytest.mark.parametrize(
    "field", ["prose", "price", "url", "purchase", "reasoningContent"]
)
def test_injected_result_fields_cannot_render_choices(field: str) -> None:
    payload = execute_catalog_search(arguments(terms=["egg"]))
    payload[field] = "injected-model-prose"
    assert catalog_answer(payload) == DISCOVERY_ERROR


def test_forged_ids_cannot_render_choices() -> None:
    payload = execute_catalog_search(arguments(terms=["egg"]))
    payload["recipe_ids"] = ["bean_tacos"]
    assert catalog_answer(payload) == DISCOVERY_ERROR
    assert catalog_answer({"request": {}}) == DISCOVERY_ERROR


def test_schema_requires_only_bounded_arguments() -> None:
    spec = cast(dict[str, object], catalog_tool_spec()["toolSpec"])
    schema_wrapper = cast(dict[str, object], spec["inputSchema"])
    schema = cast(dict[str, object], schema_wrapper["json"])
    assert schema["additionalProperties"] is False
    assert set(cast(list[str], schema["required"])) == {
        "terms",
        "diet",
        "ingredient_exclusions",
    }
    properties = cast(dict[str, dict[str, object]], schema["properties"])
    assert set(properties) == set(cast(list[str], schema["required"]))
    assert properties["terms"]["minItems"] == 1
    for key, limit in [("terms", 8), ("ingredient_exclusions", 22)]:
        assert properties[key]["maxItems"] == limit
        assert properties[key]["items"] == {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        }
    payload = execute_catalog_search(arguments())
    assert set(payload) == {"request", "recipe_ids"}
    assert "evidence" not in json.dumps(payload)


def test_discovery_renders_exact_catalog_names() -> None:
    payload = execute_catalog_search(arguments(terms=["chicken"]))
    assert payload["recipe_ids"] == [
        "chicken_tacos",
        "chicken_and_rice_bowls",
        "chicken_pasta",
    ]
    assert catalog_answer(payload).startswith(
        "Catalog choices: Chicken tacos, Chicken and rice bowls, Chicken pasta. "
        "Which one should I plan? "
    )
