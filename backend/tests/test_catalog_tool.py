import json
import re
from datetime import date
from itertools import combinations
from typing import cast

import pytest

from app.agent import catalog_tool
from app.agent.catalog_tool import (
    DISCOVERY_ERROR,
    TOOL_NAME,
    CatalogToolError,
    catalog_answer,
    catalog_choices,
    catalog_tool_spec,
    execute_catalog_search,
    next_search_arguments,
    page_arguments,
)
from app.agent.estimate import priced_estimate
from app.domain.budget import BudgetResult
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SUPPORTED_RECIPE_IDS, GroceryRequest, MealRequest
from app.domain.meal_tags import (
    CARNIVORE_NOTE,
    GLUTEN_INGREDIENT_IDS,
    KETO_NOTE,
    MEAL_DIETS,
    MEAL_TAGS,
    TAG_ORDER,
)
from app.services.meal_nutrition import meal_nutrition

SENTINEL = "zqxsentinel"
TAG_TYPES = [
    "high_protein",
    "lower_carb",
    "gluten_free_ingredients",
    "vegetarian",
    "vegan",
]


def test_catalog_choices_returns_ids_of_a_rechecked_ok_payload() -> None:
    payload = execute_catalog_search({"query": "lentils"})
    assert payload["status"] == "ok"
    assert catalog_choices(payload) == payload["recipe_ids"]
    assert catalog_choices(payload) is not payload["recipe_ids"]


def test_catalog_choices_is_empty_for_a_forged_payload() -> None:
    payload = execute_catalog_search({"query": "lentils"})
    extra = next(r for r in SUPPORTED_RECIPE_IDS if r not in payload["recipe_ids"])
    ids = cast(list[str], payload["recipe_ids"])
    forged_ids = {**payload, "recipe_ids": [*ids, extra]}
    forged_applied = {**payload, "applied": ["vegan"]}
    assert catalog_choices(forged_ids) == []
    assert catalog_choices(forged_applied) == []
    assert catalog_choices({**payload, "request": "x"}) == []
    assert catalog_choices({}) == []


def test_catalog_choices_is_empty_unless_the_status_is_ok() -> None:
    searches = {
        "no_match": {"query": SENTINEL},
        "unsupported_facet": {"query": "dairy free"},
        "unknown_exclusion": {"query": "chickpea", "exclude": ["nightshades"]},
    }
    for status, arguments in searches.items():
        payload = execute_catalog_search(arguments)
        assert payload["status"] == status
        assert catalog_choices(payload) == []
        assert catalog_choices({**payload, "status": "ok"}) == []


def protein_mg(rid: str) -> int:
    request = GroceryRequest(
        meals=[MealRequest(recipe_id=rid, servings=1)], budget_period=date(2026, 1, 1)
    )
    return meal_nutrition(request).meals[0].per_serving.protein_mg


def protein_g(rid: str) -> int:
    return (protein_mg(rid) + 500) // 1000


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
        "tags",
        "exclude",
        "min_protein_g",
        "max_cents_per_serving",
        "limit",
        "offset",
    }
    assert properties["offset"]["minimum"] == 0
    assert properties["offset"]["maximum"] == 39
    assert "maxItems" not in properties["tags"]
    assert properties["tags"]["uniqueItems"] is True
    assert cast(dict[str, object], properties["tags"]["items"])["enum"] == TAG_TYPES
    assert "Every result has every type in query and tags" in cast(
        str, spec["description"]
    )
    assert "Exclusions go in exclude" in cast(str, spec["description"])
    assert "Not for a meal the user names or has in the plan." in cast(
        str, spec["description"]
    )
    assert properties["query"]["maxLength"] == 120
    assert properties["exclude"]["maxItems"] == 22
    assert properties["limit"]["maximum"] == 3
    assert properties["min_protein_g"]["type"] == "integer"
    assert properties["max_cents_per_serving"]["type"] == "integer"
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
    assert "taco" in ids(payload)[0]
    for rid in ids(payload):
        items = RECIPES[rid].ingredients
        names = [rid, *(INGREDIENTS[item].name.lower() for item, _ in items)]
        assert any("taco" in name for name in names)


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


@pytest.mark.parametrize("query", ["meat", "carnivore"])
def test_meat_and_carnivore_are_a_chicken_search(query: str) -> None:
    payload = search(query)
    assert payload["status"] == "ok"
    assert payload["applied"] == ["chicken"]
    assert payload["unmatched"] == []
    assert ids(payload)
    assert all("chicken" in MEAL_TAGS[rid] for rid in ids(payload))
    assert CARNIVORE_NOTE in catalog_answer(payload)


@pytest.mark.parametrize(
    ("query", "texts"),
    [
        ("dairy free dinner", ["dairy free"]),
        ("paleo", ["paleo"]),
        ("nut-free lunch", ["nut-free"]),
        ("paleo and dairy free", ["paleo", "dairy free"]),
        ("keto dairy-free", ["dairy-free"]),
    ],
)
def test_a_type_the_system_cannot_check_fails_closed(
    query: str, texts: list[str]
) -> None:
    payload = search(query)
    assert payload["status"] == "unsupported_facet"
    assert payload["unsupported"] == texts
    assert ids(payload) == []
    answer = catalog_answer(payload)
    assert answer == (
        f"I cannot check {', '.join(texts)} in this catalog. I can search by: "
        "high protein, lower carb, gluten-free ingredients, vegetarian, vegan, "
        "chicken, egg, beans, lentils, or chickpeas."
    )
    assert "No catalog meal matches" not in answer


def test_unknown_exclusion_is_checked_before_an_unsupported_type() -> None:
    payload = search("paleo", exclude=["nightshades"])
    assert payload["status"] == "unknown_exclusion"
    assert payload["unsupported"] == ["paleo"]
    assert "I could not match an ingredient to exclude" in catalog_answer(payload)


def test_checkable_types_are_not_unsupported() -> None:
    for query in ("keto", "plant based", "plant-based", "tacos"):
        assert search(query)["unsupported"] == []
    assert search("keto")["status"] == "ok"
    assert "lower_carb" in cast(list[str], search("keto")["applied"])
    assert search("plant-based")["applied"] == ["vegan"]


def test_tags_are_hard_filters_and_echoed_in_order() -> None:
    payload = search("dinner", tags=["high_protein", "vegetarian"])
    both = [
        rid
        for rid in SUPPORTED_RECIPE_IDS
        if "high_protein" in MEAL_TAGS[rid] and "vegetarian" in MEAL_DIETS[rid]
    ]
    assert payload["status"] == ("ok" if both else "no_match")
    assert payload["applied"] == ["high_protein", "vegetarian"]
    assert ids(payload) == both[:3]
    vegan = search("dinner", tags=["vegan"])
    assert vegan["status"] == "ok" and vegan["applied"] == ["vegan"]
    assert all("vegan" in MEAL_DIETS[rid] for rid in ids(vegan))
    request = cast(dict[str, object], payload["request"])
    assert request["tags"] == ["high_protein", "vegetarian"]
    reordered = search("dinner", tags=["vegetarian", "high_protein"])
    assert reordered == payload
    assert cast(dict[str, object], search("dinner")["request"])["tags"] == []


def test_a_tag_joins_the_facets_found_in_the_query() -> None:
    payload = search("chickpea", tags=["gluten_free_ingredients"], diet="vegan")
    assert payload["applied"] == ["gluten_free_ingredients", "vegan"]
    assert search("high protein", tags=["high_protein"])["applied"] == ["high_protein"]


@pytest.mark.parametrize(
    "tags",
    [
        ["paleo"],
        ["vegan", "vegan"],
        ["omnivore"],
        [1],
        [None],
        ["vegan", 1],
        "vegan",
        None,
        ["High_Protein"],
        [*TAG_TYPES, "vegan"],
        ["chicken"],
        ["egg", "high_protein"],
        list(TAG_ORDER),
    ],
)
def test_invalid_tags_fail(tags: object) -> None:
    with pytest.raises(CatalogToolError, match="^arguments are invalid$"):
        execute_catalog_search({"query": "dinner", "tags": tags})


def test_every_tag_value_is_accepted_and_five_tags_fit() -> None:
    assert len(TAG_TYPES) == 5
    payload = search("dinner", tags=TAG_TYPES)
    request = cast(dict[str, object], payload["request"])
    assert request["tags"] == TAG_TYPES


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "dairy free dinner"},
        {"query": "paleo"},
        {"query": "nut-free lunch"},
        {"query": "keto"},
        {"query": "meat"},
        {"query": "dinner", "tags": ["vegetarian", "high_protein"]},
    ],
)
def test_answer_round_trips_from_the_request(arguments: dict[str, object]) -> None:
    payload = execute_catalog_search(arguments)
    assert execute_catalog_search(payload["request"]) == payload
    assert catalog_answer(payload) == catalog_answer(
        execute_catalog_search(payload["request"])
    )
    assert catalog_answer(payload) != DISCOVERY_ERROR


def test_forged_unsupported_cannot_render_choices() -> None:
    payload = search("paleo")
    payload["unsupported"] = []
    assert catalog_answer(payload) == DISCOVERY_ERROR
    payload = search("egg")
    payload["unsupported"] = ["paleo"]
    assert catalog_answer(payload) == DISCOVERY_ERROR


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
    assert all(has(rid, "chickpeas") for rid in ids(payload))


def test_every_text_word_must_match_the_returned_meals() -> None:
    payload = search("chickpea egg", limit=3)
    assert ids(payload)
    for rid in ids(payload):
        assert has(rid, "chickpeas") and has(rid, "eggs")


@pytest.mark.parametrize("query", ["a meal for me", "something", "123"])
def test_query_without_search_words_is_no_match(query: str) -> None:
    payload = search(query)
    assert payload["status"] == "no_match"
    assert ids(payload) == []


def test_word_after_without_or_no_is_not_a_search_word() -> None:
    plain = search("tacos")
    for query in ("tacos without chicken", "tacos with no chicken"):
        payload = search(query)
        assert ids(payload) == ids(plain)
        assert payload["unmatched"] == ["chicken"]
    assert search("without chicken")["status"] == "no_match"


def test_negation_ends_at_the_next_stopword() -> None:
    payload = search("no, i want chicken")
    assert payload["status"] == "ok"
    assert payload["unmatched"] == []
    assert ids(payload) == ids(search("chicken"))
    assert search("tacos without the chicken")["unmatched"] == ["chicken"]


@pytest.mark.parametrize(
    ("query", "tag", "note", "other"),
    [
        ("keto", "lower_carb", KETO_NOTE, CARNIVORE_NOTE),
        ("chicken", "chicken", CARNIVORE_NOTE, KETO_NOTE),
    ],
)
def test_a_tag_is_a_hard_filter_and_its_note_follows_it(
    monkeypatch: pytest.MonkeyPatch, query: str, tag: str, note: str, other: str
) -> None:
    keep = ids(search(query))[0]
    tags = {
        rid: found if rid == keep else tuple(t for t in found if t != tag)
        for rid, found in MEAL_TAGS.items()
    }
    monkeypatch.setattr(catalog_tool, "MEAL_TAGS", tags)
    payload = search(query)
    assert ids(payload) == [keep]
    answer = catalog_answer(payload)
    assert note in answer and other not in answer
    assert note not in catalog_answer(search("tacos"))


def test_note_shows_when_every_returned_meal_has_the_tag() -> None:
    payload = search("chicken", limit=1)
    assert "chicken" in MEAL_TAGS[ids(payload)[0]]
    assert CARNIVORE_NOTE in catalog_answer(payload)


@pytest.mark.parametrize("diet", ["vegetarian", "vegan"])
def test_diet_filters(diet: str) -> None:
    payload = search("chickpea", diet=diet)
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
    request = cast(dict[str, object], payload["request"])
    assert request["exclude"] == ["eggs"]
    assert "nightshades" not in json.dumps(request)
    assert "I could not match an ingredient to exclude" in catalog_answer(payload)
    assert "nightshades" not in catalog_answer(payload)


def test_min_protein_filters_on_computed_value() -> None:
    chicken = [
        protein_g(rid) for rid in SUPPORTED_RECIPE_IDS if "chicken" in MEAL_TAGS[rid]
    ]
    assert chicken
    for threshold in (0, min(chicken), max(chicken)):
        payload = search("chicken", min_protein_g=threshold, limit=3)
        assert ids(payload)
        for rid in ids(payload):
            assert protein_g(rid) >= threshold
    grams = [protein_g(r) for r in ids(search("egg", min_protein_g=1))]
    assert grams == sorted(grams, reverse=True)
    assert search("egg", min_protein_g=200)["status"] == "no_match"


def test_protein_rounds_half_up_at_the_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rid = ids(search("egg"))[0]
    values = {rid: 29_460}
    monkeypatch.setattr(catalog_tool, "_protein_mg", lambda r: values.get(r, 0))
    assert rid in ids(search("egg", min_protein_g=29))
    assert rid not in ids(search("egg", min_protein_g=30, limit=3))
    values[rid] = 29_500
    assert rid in ids(search("egg", min_protein_g=30, limit=3))


def test_max_cents_filters_on_sample_price() -> None:
    budget = BudgetResult(10**9, 0, False, ())

    def cents(rid: str) -> int:
        return cast(int, priced_estimate([(rid, 1)], [], budget)["total_cents"])

    prices = sorted(cents(rid) for rid in SUPPORTED_RECIPE_IDS if has(rid, "onion"))
    cap = prices[len(prices) // 2]
    payload = search("onion", max_cents_per_serving=cap)
    assert ids(payload)
    assert all(cents(rid) <= cap for rid in ids(payload))
    assert search("egg", max_cents_per_serving=1)["status"] == "no_match"


def test_incomplete_price_is_excluded_by_a_price_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ids(search("egg", max_cents_per_serving=10000))
    monkeypatch.setattr(catalog_tool, "_serving_cents", lambda rid: None)
    payload = search("egg", max_cents_per_serving=10000)
    assert payload["status"] == "no_match"
    assert ids(payload) == []


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
        {"offset": -1},
        {"offset": 40},
        {"offset": 1.0},
        {"offset": True},
        {"offset": None},
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
        "tags": [],
        "exclude": ["olive_oil"],
        "min_protein_g": None,
        "max_cents_per_serving": None,
        "limit": 3,
        "offset": 0,
    }
    assert execute_catalog_search(request) == payload


def test_offset_walks_the_full_ordered_set_with_a_stable_total() -> None:
    full = search("vegetarian", limit=3)
    total = cast(int, full["total_matches"])
    assert total > 3
    walked: list[str] = []
    for offset in range(0, total, 3):
        page = search("vegetarian", offset=offset)
        assert page["total_matches"] == total
        assert page["status"] == "ok"
        request = cast(dict[str, object], page["request"])
        assert request["offset"] == offset
        assert catalog_answer(page) == catalog_answer(execute_catalog_search(request))
        more = offset + len(ids(page)) < total
        assert ("Ask for more to see the next ones." in catalog_answer(page)) == more
        walked.extend(ids(page))
    assert len(walked) == total == len(set(walked))
    assert walked[:3] == ids(full)


def test_offset_past_the_end_is_ok_and_empty_or_no_match() -> None:
    total = cast(int, search("vegetarian")["total_matches"])
    past = search("vegetarian", offset=min(total, 39))
    if total <= 39:
        assert past["status"] == "ok" and ids(past) == []
        assert catalog_answer(past) == "There are no more matching meals."
    nothing = search("vegetarian", min_protein_g=200, offset=5)
    assert nothing["status"] == "no_match" and nothing["total_matches"] == 0


def test_next_search_arguments_walk_every_page_without_repeats() -> None:
    page = search("vegetarian")
    total = cast(int, page["total_matches"])
    assert total > 3
    walked = ids(page)
    while (arguments := next_search_arguments(page)) is not None:
        assert arguments["offset"] == len(walked)
        page = execute_catalog_search(arguments)
        assert page["status"] == "ok" and page["total_matches"] == total
        assert not set(walked) & set(ids(page))
        walked.extend(ids(page))
    assert len(walked) == total
    assert next_search_arguments(page) is None


def test_next_search_arguments_keep_the_request_and_catalog_words_only() -> None:
    page = search(
        "high protein meals please",
        diet="vegetarian",
        exclude=["egg"],
        min_protein_g=1,
        max_cents_per_serving=10000,
        limit=1,
    )
    arguments = next_search_arguments(page)
    if arguments is None:
        assert cast(int, page["total_matches"]) <= 1
        return
    assert arguments["offset"] == 1 and arguments["limit"] == 1
    assert arguments["min_protein_g"] == 1
    assert arguments["max_cents_per_serving"] == 10000
    assert arguments["diet"] == "vegetarian"
    assert arguments["exclude"] == page_request(page)["exclude"]
    assert execute_catalog_search(arguments)["applied"] == page["applied"]


def page_request(payload: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], payload["request"])


def test_next_search_arguments_drop_free_text_and_omit_none() -> None:
    page = search(f"vegetarian {SENTINEL}", limit=1)
    arguments = next_search_arguments(page)
    assert arguments is not None
    assert SENTINEL not in json.dumps(arguments)
    assert arguments["query"] == "meals" and arguments["tags"] == ["vegetarian"]
    assert "min_protein_g" not in arguments
    assert "max_cents_per_serving" not in arguments
    open_page = search("meals", tags=["lower_carb"], limit=1)
    open_arguments = next_search_arguments(open_page)
    if open_arguments is not None:
        assert open_arguments["query"] == "meals"


def test_next_search_arguments_need_a_valid_ok_payload_with_more_matches() -> None:
    page = search("vegetarian")
    forged = {**page, "recipe_ids": list(reversed(ids(page)))}
    assert next_search_arguments(forged) is None
    assert next_search_arguments({**page, "total_matches": 99}) is None
    assert next_search_arguments(search(SENTINEL)) is None
    total = cast(int, page["total_matches"])
    end = search("vegetarian", offset=(total - 1) // 3 * 3)
    assert next_search_arguments(end) is None


def test_page_arguments_accept_only_a_page_that_shows_meals() -> None:
    good: dict[str, object] = {"query": "vegetarian", "offset": 3}
    assert page_arguments(good) == good
    assert page_arguments({**good, "offset": 40}) is None
    total = cast(int, search("vegetarian")["total_matches"])
    assert page_arguments({**good, "offset": min(total, 39)}) is None or total >= 40
    assert page_arguments({**good, "tags": ["unknown"]}) is None
    assert page_arguments({"query": SENTINEL}) is None
    assert page_arguments("vegetarian") is None
    assert page_arguments(None) is None


@pytest.mark.parametrize(
    "query", [SENTINEL, f"egg {SENTINEL}", f"{SENTINEL} {SENTINEL}"]
)
def test_answer_never_echoes_model_words(query: str) -> None:
    payload = search(query, exclude=[SENTINEL] if query == SENTINEL else [])
    assert SENTINEL in json.dumps(payload)
    assert SENTINEL not in catalog_answer(payload)


def test_answer_renders_exact_names_and_safety() -> None:
    payload = search("chickpea high protein")
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


INGREDIENT_WORDS = sorted(
    {w for item in INGREDIENTS.values() for w in re.findall(r"[a-z]+", item.name)}
)


def has_facet(facet: str, rid: str) -> bool:
    return facet in MEAL_TAGS[rid] or facet in MEAL_DIETS[rid]


def gluten_ids(rid: str) -> set[str]:
    return GLUTEN_INGREDIENT_IDS & {item for item, _ in RECIPES[rid].ingredients}


@pytest.mark.parametrize("diet", ["omnivore", "vegetarian", "vegan"])
def test_every_returned_meal_has_every_applied_facet_and_text_word(diet: str) -> None:
    for tag in TAG_ORDER:
        for word in INGREDIENT_WORDS:
            payload = search(f"{tag} {word}", diet=diet)
            applied = cast(list[str], payload["applied"])
            dropped = cast(list[str], payload["dropped"])
            assert tag in applied
            assert (diet in applied) == (diet != "omnivore")
            kept = [] if catalog_tool._facet(word) or word in dropped else [word]
            for rid in ids(payload):
                assert all(has_facet(f, rid) for f in applied), (tag, word, rid)
                assert all(catalog_tool._has_word(w, rid) for w in kept), (tag, word)


@pytest.mark.parametrize("diet", ["omnivore", "vegetarian", "vegan"])
def test_every_returned_meal_has_every_tag_and_text_word(diet: str) -> None:
    facets = [*TAG_ORDER, "vegetarian", "vegan"]
    for size in (1, 2):
        for chosen in combinations(TAG_TYPES, size):
            for word in INGREDIENT_WORDS[::7]:
                payload = search(word, diet=diet, tags=list(chosen))
                applied = cast(list[str], payload["applied"])
                dropped = cast(list[str], payload["dropped"])
                assert set(chosen) <= set(applied), (chosen, word)
                assert applied == [f for f in facets if f in applied]
                request = cast(dict[str, object], payload["request"])
                assert request["tags"] == list(chosen)
                kept = [] if catalog_tool._facet(word) or word in dropped else [word]
                for rid in ids(payload):
                    assert all(has_facet(f, rid) for f in applied), (chosen, word)
                    assert all(catalog_tool._has_word(w, rid) for w in kept)
                assert catalog_answer(payload) == catalog_answer(
                    execute_catalog_search(request)
                )


def test_gluten_free_pasta_keeps_the_facet_and_drops_the_word() -> None:
    payload = search("gluten-free pasta")
    assert payload["status"] == "ok"
    assert payload["applied"] == ["gluten_free_ingredients"]
    assert payload["dropped"] == ["pasta"]
    assert ids(payload) and not any(gluten_ids(rid) for rid in ids(payload))
    answer = catalog_answer(payload)
    assert "No meal with those types also matched: pasta." in answer
    assert answer.index("also matched") < answer.index("Gluten-free ingredients")


def test_a_facet_is_never_dropped() -> None:
    payload = search("gluten-free pasta", diet="vegan")
    assert payload["applied"] == ["gluten_free_ingredients", "vegan"]
    assert payload["dropped"] == ["pasta"]
    assert ids(payload)
    for rid in ids(payload):
        assert not gluten_ids(rid) and "vegan" in MEAL_DIETS[rid]


def test_a_type_and_a_word_that_match_together_drop_nothing() -> None:
    payload = search("chickpea high protein")
    assert payload["status"] == "ok"
    assert payload["dropped"] == []
    assert ids(payload)
    for rid in ids(payload):
        assert "high_protein" in MEAL_TAGS[rid] and has(rid, "chickpeas")
    assert "also matched" not in catalog_answer(payload)


def test_a_diet_argument_alone_keeps_meals_and_drops_the_word() -> None:
    payload = search("eggs", diet="vegan")
    assert payload["status"] == "ok"
    assert payload["applied"] == ["vegan"]
    assert payload["dropped"] == ["eggs"]
    assert ids(payload)
    assert all("vegan" in MEAL_DIETS[rid] for rid in ids(payload))
    assert "No meal with those types also matched: eggs." in catalog_answer(payload)
    assert search("eggs")["dropped"] == []
    assert search("xyzzy", diet="omnivore")["status"] == "no_match"


def test_high_protein_vegetarian_needs_both() -> None:
    payload = search("high protein vegetarian")
    assert payload["applied"] == ["high_protein", "vegetarian"]
    for rid in ids(payload):
        assert "high_protein" in MEAL_TAGS[rid] and "vegetarian" in MEAL_DIETS[rid]
    assert search("high protein", diet="vegetarian")["applied"] == payload["applied"]


def test_lentil_soup_still_leads() -> None:
    assert ids(search("lentil soup"))[0] == "lentil_soup"


def test_diet_argument_is_a_facet_and_omnivore_is_not() -> None:
    assert search("rice", diet="vegan")["applied"] == ["vegan"]
    assert search("rice")["applied"] == []
    assert search("rice omnivore")["applied"] == []


def test_matches_keep_catalog_order() -> None:
    expected = [r for r in SUPPORTED_RECIPE_IDS if catalog_tool._has_word("rice", r)]
    assert ids(search("rice")) == expected[:3]


def test_text_words_alone_never_drop_to_every_meal() -> None:
    first, second = next(
        (a, b)
        for a, b in combinations(INGREDIENT_WORDS, 2)
        if not catalog_tool._facet(a)
        and not catalog_tool._facet(b)
        and not any(
            catalog_tool._has_word(a, r) and catalog_tool._has_word(b, r)
            for r in SUPPORTED_RECIPE_IDS
        )
    )
    payload = search(f"{first} {second}")
    assert payload["status"] == "no_match"
    assert payload["dropped"] == []


def test_reply_caveats_follow_the_applied_facets() -> None:
    sentences = (
        "High protein means",
        "Lower carb means",
        "Gluten-free ingredients describes",
    )
    queries: list[tuple[str, int | None]] = [
        ("tacos", None),
        ("high protein", 0),
        ("keto", 1),
        ("gluten free", 2),
    ]
    for query, index in queries:
        payload = search(query)
        answer = catalog_answer(payload)
        assert [s for s in sentences if s in answer] == (
            [] if index is None else [sentences[index]]
        )
        assert "I cannot claim gluten-free, celiac, allergy, or cross" in answer
        assert "No meal with those types" not in answer
    assert search("tacos")["applied"] == []


def test_forged_applied_or_dropped_cannot_render_choices() -> None:
    payload = search("high protein")
    payload["applied"] = []
    assert catalog_answer(payload) == DISCOVERY_ERROR
    payload = search("gluten-free pasta")
    payload["dropped"] = []
    assert catalog_answer(payload) == DISCOVERY_ERROR
