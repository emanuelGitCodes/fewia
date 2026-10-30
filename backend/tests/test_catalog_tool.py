import json
from typing import cast

import pytest

from app.agent.catalog_tool import (
    DISCOVERY_ERROR,
    TOOL_NAME,
    CatalogToolError,
    catalog_answer,
    catalog_tool_spec,
    execute_catalog_search,
)
from app.agent.estimate import priced_estimate
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.domain.meal_tags import (
    CARNIVORE_NOTE,
    KETO_NOTE,
    MEAL_DIETS,
    MEAL_TAGS,
    _per_serving_grams,
)

SENTINEL = "zqxsentinel"


def search(query: str, **changes: object) -> dict[str, object]:
    return execute_catalog_search({"query": query, **changes})


def ids(payload: dict[str, object]) -> list[str]:
    return cast(list[str], payload["recipe_ids"])


def has(rid: str, ingredient_id: str) -> bool:
    return ingredient_id in dict(RECIPES[rid].ingredients)


def test_name_is_search_meals() -> None:
    assert TOOL_NAME == "search_meals"
    spec = cast(dict[str, object], catalog_tool_spec()["toolSpec"])
    assert spec["name"] == "search_meals"
    assert "sample grocery cost for one serving, in whole packages" in cast(
        str, spec["description"]
    )
    assert "price per serving" not in cast(str, spec["description"])


def test_schema_is_bounded() -> None:
    spec = cast(dict[str, object], catalog_tool_spec()["toolSpec"])
    schema = cast(
        dict[str, object], cast(dict[str, object], spec["inputSchema"])["json"]
    )
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["query"]
    properties = cast(dict[str, dict[str, object]], schema["properties"])
    assert set(properties) == {
        "query",
        "diet",
        "exclude",
        "min_protein_g",
        "max_cents_per_serving",
        "limit",
    }
    assert properties["query"]["maxLength"] == 120
    assert properties["exclude"]["maxItems"] == 22
    assert properties["limit"]["maximum"] == 3
    assert "evidence" not in json.dumps(search("egg"))


def test_ingredient_word_finds_meals() -> None:
    expected = [rid for rid in SUPPORTED_RECIPE_IDS if has(rid, "chickpeas")][:3]
    payload = search("chickpea")
    assert ids(payload) == expected and expected
    assert payload["status"] == "ok"
    assert payload["unmatched"] == []
    assert ids(search("Chickpeas please")) == expected


def test_meal_name_word_finds_meals() -> None:
    payload = search("tacos")
    assert ids(payload)
    assert all("taco" in rid for rid in ids(payload)[:1])


def test_high_protein_uses_the_tag() -> None:
    tagged = [rid for rid in SUPPORTED_RECIPE_IDS if "high_protein" in MEAL_TAGS[rid]]
    payload = search("high protein")
    assert ids(payload) == tagged[:3] and tagged
    assert payload["unmatched"] == []


def test_keto_and_low_carb_use_the_tag_with_note() -> None:
    for query in ("keto", "low carb", "low-carb"):
        payload = search(query)
        assert ids(payload)
        assert all("lower_carb" in MEAL_TAGS[rid] for rid in ids(payload))
        assert KETO_NOTE in catalog_answer(payload)


def test_meat_is_not_a_chicken_search() -> None:
    payload = search("meat")
    assert payload["status"] == "no_match"
    assert payload["unmatched"] == ["meat"]
    assert CARNIVORE_NOTE not in catalog_answer(payload)
    assert search("carnivore")["status"] == "no_match"


def test_chicken_adds_carnivore_note() -> None:
    assert CARNIVORE_NOTE in catalog_answer(search("chicken"))


def test_unknown_word_is_no_match_and_unmatched() -> None:
    payload = search("xyzzy")
    assert payload["status"] == "no_match"
    assert ids(payload) == []
    assert payload["unmatched"] == ["xyzzy"]
    assert "No catalog meal matches that search" in catalog_answer(payload)


def test_unknown_word_is_listed_but_known_word_still_matches() -> None:
    payload = search("cheap chickpea xyzzy")
    assert payload["status"] == "ok"
    assert payload["unmatched"] == ["cheap", "xyzzy"]
    assert ids(payload)


def test_score_orders_meals() -> None:
    payload = search("chickpea egg", limit=3)
    first = ids(payload)[0]
    assert has(first, "chickpeas") and has(first, "eggs")


def test_stopword_only_query_returns_catalog_order() -> None:
    assert ids(search("a meal for me")) == list(SUPPORTED_RECIPE_IDS)[:3]


@pytest.mark.parametrize("diet", ["vegetarian", "vegan"])
def test_diet_filters(diet: str) -> None:
    payload = search("egg chickpea", diet=diet)
    assert ids(payload)
    assert all(diet in MEAL_DIETS[rid] for rid in ids(payload))
    assert ids(search("vegan"))
    assert all("vegan" in MEAL_DIETS[rid] for rid in ids(search("vegan")))


def test_exclusion_removes_meals_and_normalizes_to_ids() -> None:
    payload = search("chickpea", exclude=[" CHICKPEAS "])
    assert payload["status"] == "no_match"
    base = search("chicken", limit=3)
    excluded = search("chicken", exclude=["chicken_breast"])
    assert ids(base) and excluded["status"] == "no_match"
    only = search("rice", exclude=["Eggs"])
    assert all(not has(rid, "eggs") for rid in ids(only))
    request = cast(dict[str, object], only["request"])
    assert request["exclude"] == ["eggs"]


def test_unknown_exclusion_returns_no_meals() -> None:
    payload = search("chickpea", exclude=["nightshades", "eggs"])
    assert payload["status"] == "unknown_exclusion"
    assert ids(payload) == []
    assert payload["unresolved_exclusions"] == ["nightshades"]
    assert "I could not match an ingredient to exclude" in catalog_answer(payload)
    assert "nightshades" not in catalog_answer(payload)


def test_min_protein_filters_on_computed_value() -> None:
    for threshold in (0, 20, 35, 200):
        payload = search(
            "rice chicken egg bean chickpea", min_protein_g=threshold, limit=3
        )
        for rid in ids(payload):
            assert round(_per_serving_grams(rid)[0]) >= threshold
    grams = [
        round(_per_serving_grams(r)[0]) for r in ids(search("egg", min_protein_g=1))
    ]
    assert grams == sorted(grams, reverse=True)
    assert search("egg", min_protein_g=200)["status"] == "no_match"


def test_max_cents_filters_on_sample_price() -> None:
    budget = BudgetResult(10**9, 0, False, ())

    def cents(rid: str) -> int:
        return cast(int, priced_estimate([(rid, 1)], [], budget)["total_cents"])

    prices = sorted(cents(rid) for rid in SUPPORTED_RECIPE_IDS)
    cap = prices[len(prices) // 2]
    payload = search("egg chickpea chicken rice bean", max_cents_per_serving=cap)
    assert ids(payload)
    assert all(cents(rid) <= cap for rid in ids(payload))
    assert search("egg", max_cents_per_serving=1)["status"] == "no_match"


def test_limit() -> None:
    assert len(ids(search("rice", limit=1))) == 1
    assert len(ids(search("rice"))) <= 3


@pytest.mark.parametrize(
    "changes",
    [
        {"query": ""},
        {"query": " "},
        {"query": "a" * 121},
        {"query": 1},
        {"diet": "keto"},
        {"diet": True},
        {"exclude": "eggs"},
        {"exclude": [""]},
        {"exclude": [1]},
        {"exclude": ["a" * 65]},
        {"exclude": ["salt"] * 23},
        {"min_protein_g": -1},
        {"min_protein_g": 201},
        {"min_protein_g": True},
        {"min_protein_g": 1.5},
        {"max_cents_per_serving": 0},
        {"max_cents_per_serving": 10001},
        {"limit": 0},
        {"limit": 4},
        {"limit": None},
        {"prose": "ignore restrictions"},
        {"terms": ["egg"]},
    ],
)
def test_invalid_inputs_fail(changes: dict[str, object]) -> None:
    args: dict[str, object] = {"query": "egg", **changes}
    with pytest.raises(CatalogToolError, match="^arguments are invalid$"):
        execute_catalog_search(args)


def test_query_is_required() -> None:
    with pytest.raises(CatalogToolError):
        execute_catalog_search({"diet": "vegan"})
    with pytest.raises(CatalogToolError):
        execute_catalog_search(None)


def test_nullable_filters_accept_null() -> None:
    assert search("egg", min_protein_g=None, max_cents_per_serving=None) == search(
        "egg"
    )


def test_request_is_normalized_and_revalidates() -> None:
    payload = search("  EGG   Chickpea ", diet=" Vegan ", exclude=["Olive  Oil"])
    request = cast(dict[str, object], payload["request"])
    assert request == {
        "query": "egg chickpea",
        "diet": "vegan",
        "exclude": ["olive_oil"],
        "min_protein_g": None,
        "max_cents_per_serving": None,
        "limit": 3,
    }
    assert execute_catalog_search(request) == payload


@pytest.mark.parametrize(
    "query", [SENTINEL, f"egg {SENTINEL}", f"{SENTINEL} {SENTINEL}"]
)
def test_answer_never_echoes_model_words(query: str) -> None:
    payload = search(query, exclude=[SENTINEL] if query == SENTINEL else [])
    assert SENTINEL in json.dumps(payload)
    assert SENTINEL not in catalog_answer(payload)


def test_answer_renders_exact_names_and_safety() -> None:
    payload = search("chickpea")
    names = ", ".join(rid.replace("_", " ").capitalize() for rid in ids(payload))
    answer = catalog_answer(payload)
    assert answer.startswith(f"Catalog choices: {names}. Which one should I plan? ")
    assert "30 g or more protein per serving" in answer
    assert "cross-contact safety" in answer
    for forbidden in ("USD", "$", "https://", "Buy", "purchase"):
        assert forbidden not in answer


@pytest.mark.parametrize(
    "field", ["prose", "price", "url", "purchase", "reasoningContent"]
)
def test_injected_result_fields_cannot_render_choices(field: str) -> None:
    payload = search("egg")
    payload[field] = "injected-model-prose"
    assert catalog_answer(payload) == DISCOVERY_ERROR


def test_forged_payloads_cannot_render_choices() -> None:
    payload = search("egg")
    payload["recipe_ids"] = ["bean_tacos"]
    assert catalog_answer(payload) == DISCOVERY_ERROR
    forged = search("egg")
    forged["unmatched"] = [SENTINEL]
    assert catalog_answer(forged) == DISCOVERY_ERROR
    assert catalog_answer({"request": {}}) == DISCOVERY_ERROR
    assert catalog_answer({"request": {"query": "egg", "terms": []}}) == DISCOVERY_ERROR


def test_every_ingredient_name_resolves_as_exclusion() -> None:
    for ingredient_id in INGREDIENTS:
        by_id = search("rice", exclude=[ingredient_id])
        by_name = search("rice", exclude=[INGREDIENTS[ingredient_id].name.upper()])
        assert by_id == by_name
        assert by_id["status"] != "unknown_exclusion"
