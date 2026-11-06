import math

import pytest

from app.agent import catalog_tool, meal_search_rank
from app.agent.catalog_tool import execute_catalog_search, search_result_ids
from app.agent.meal_search_rank import bm25_order, bm25_score
from app.domain.grocery import SUPPORTED_RECIPE_IDS


def test_bm25_score_matches_a_hand_computed_value() -> None:
    # idf = ln(1 + (4 - 1 + 0.5) / (1 + 0.5)) = ln(10 / 3)
    # length norm = 1 - 0.75 + 0.75 * 3 / 3 = 1
    # tf part = 2 * 2.2 / (2 + 1.2 * 1) = 1.375
    score = bm25_score(["a"], ["a", "a", "b"], {"a": 1}, 4, 3.0)
    assert math.isclose(score, math.log(10 / 3) * 1.375)


def test_bm25_score_is_zero_without_a_shared_term() -> None:
    assert bm25_score(["z"], ["a", "b"], {"a": 1, "b": 1}, 4, 2.0) == 0.0


def test_order_is_a_permutation_of_the_input() -> None:
    ids = list(SUPPORTED_RECIPE_IDS)
    ordered = bm25_order(["tacos", "chicken"], ids)
    assert sorted(ordered) == sorted(ids)
    assert len(ordered) == len(ids)


def test_ties_keep_the_input_order() -> None:
    ids = ["lentil_soup", "bean_tacos", "chicken_curry"]
    assert bm25_order(["zzzz"], ids) == ids
    assert bm25_order(["zzzz"], ids[::-1]) == ids[::-1]


def test_recipe_id_words_count_twice_in_a_document() -> None:
    docs, _, _ = meal_search_rank._corpus()
    document = docs["chicken_tacos"]
    assert document.count("taco") == 2  # id word only
    assert document.count("salsa") == 1  # ingredient-only word
    assert document.count("chicken") == 3  # id word twice plus the ingredient name


def test_a_doubled_word_outscores_a_single_word_in_equal_length_documents() -> None:
    frequencies = {"x": 1, "y": 1}
    doubled = bm25_score(["x"], ["x", "x", "z"], frequencies, 4, 3.0)
    single = bm25_score(["y"], ["y", "z", "z"], frequencies, 4, 3.0)
    assert doubled > single


def test_word_query_changes_order_not_membership_status_or_total() -> None:
    for query in ("chicken", "rice", "beans tacos", "egg", "lentil", "soup"):
        ranked = search_result_ids({"query": query})
        plain = search_result_ids({"query": query}, rank=False)
        assert sorted(ranked) == sorted(plain)
        found = execute_catalog_search({"query": query})
        assert found["total_matches"] == len(plain)
        assert found["status"] == ("ok" if plain else "no_match")
        assert found["recipe_ids"] == ranked[:3]


def test_search_applies_bm25_to_a_word_query() -> None:
    # Catalog order starts chicken_tacos, bean_tacos, egg_tacos; the shorter
    # egg and chickpea documents outrank them.
    found = execute_catalog_search({"query": "tacos"})
    assert found["recipe_ids"] == ["egg_tacos", "chickpea_tacos", "chicken_tacos"]
    assert search_result_ids({"query": "tacos"}, rank=False)[:3] == [
        "chicken_tacos",
        "bean_tacos",
        "egg_tacos",
    ]


def _reversed(words: list[str], recipe_ids: list[str]) -> list[str]:
    return recipe_ids[::-1]


def _raises(words: list[str], recipe_ids: list[str]) -> list[str]:
    raise AssertionError("bm25_order must not run without rank terms")


def test_ingredient_facet_query_ranks_on_its_tag() -> None:
    ranked = search_result_ids({"query": "chicken"})
    assert ranked == [
        "chicken_pasta",
        "chicken_tacos",
        "chicken_potato_bake",
        "chicken_chickpea_skillet",
        "chicken_curry",
        "chicken_vegetable_soup",
        "chicken_stir_fry",
        "chicken_lentil_stew",
        "chicken_fried_rice",
        "chicken_tortilla_soup",
        "chicken_and_rice_bowls",
        "chicken_burrito_bowls",
    ]
    assert ranked != search_result_ids({"query": "chicken"}, rank=False)


def test_egg_query_ranks_on_its_tag() -> None:
    assert search_result_ids({"query": "egg"}) == [
        "egg_tacos",
        "tomato_egg_pasta",
        "potato_hash_with_eggs",
        "chickpea_egg_scramble",
        "egg_rice_bowls",
        "egg_fried_rice",
        "vegetable_egg_stir_fry",
        "lentil_egg_skillet",
        "breakfast_burritos",
        "chicken_fried_rice",
    ]


def test_beans_tacos_ranks_on_both_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    original = catalog_tool.bm25_order

    def spy(words: list[str], recipe_ids: list[str]) -> list[str]:
        calls.append(list(words))
        return original(words, recipe_ids)

    monkeypatch.setattr(catalog_tool, "bm25_order", spy)
    ranked = search_result_ids({"query": "beans tacos"})
    assert ranked == ["bean_tacos"]
    assert calls == [["tacos", "beans"]]
    plain = search_result_ids({"query": "beans tacos"}, rank=False)
    assert bm25_order(["tacos", "beans"], plain) == ranked


def test_diet_only_query_never_calls_bm25(monkeypatch: pytest.MonkeyPatch) -> None:
    plain = search_result_ids({"query": "vegan"}, rank=False)
    assert len(plain) > 1
    monkeypatch.setattr(catalog_tool, "bm25_order", _raises)
    assert search_result_ids({"query": "vegan"}) == plain


def test_facet_only_query_never_calls_bm25(monkeypatch: pytest.MonkeyPatch) -> None:
    plain = search_result_ids({"query": "vegan"}, rank=False)
    assert len(plain) > 1
    monkeypatch.setattr(catalog_tool, "bm25_order", _reversed)
    assert search_result_ids({"query": "vegan"}) == plain
    assert search_result_ids({"query": "omnivore", "diet": "vegan"}) == plain


def test_facet_fallback_keeps_eligible_order(monkeypatch: pytest.MonkeyPatch) -> None:
    arguments = {"query": "gluten free pasta"}
    eligible = [
        r
        for r in SUPPORTED_RECIPE_IDS
        if catalog_tool._has_facet("gluten_free_ingredients", r)
    ]
    found = execute_catalog_search(arguments)
    assert found["dropped"] == ["pasta"]
    assert search_result_ids(arguments) == eligible
    assert found["recipe_ids"] == eligible[:3]
    monkeypatch.setattr(catalog_tool, "bm25_order", _reversed)
    assert search_result_ids(arguments) == eligible


def test_min_protein_keeps_its_sort() -> None:
    arguments = {"query": "rice", "min_protein_g": 1}
    ranked = search_result_ids(arguments)
    assert ranked == search_result_ids(arguments, rank=False)
    grams = [catalog_tool._protein_g(r) for r in ranked]
    assert grams == sorted(grams, reverse=True)


def test_paging_is_deterministic() -> None:
    first = execute_catalog_search({"query": "tacos", "limit": 2, "offset": 0})
    second = execute_catalog_search({"query": "tacos", "limit": 2, "offset": 2})
    again = execute_catalog_search({"query": "tacos", "limit": 2, "offset": 0})
    assert first == again
    assert not set(first["recipe_ids"]) & set(second["recipe_ids"])  # type: ignore[call-overload]
