import math

from app.agent import catalog_tool
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


def test_a_recipe_id_word_outranks_an_ingredient_only_word() -> None:
    ordered = bm25_order(["tacos"], list(SUPPORTED_RECIPE_IDS))
    assert "tacos" in ordered[0]


def test_word_query_changes_order_not_membership_status_or_total() -> None:
    for query in ("chicken", "rice", "beans tacos", "egg", "lentil", "soup"):
        ranked = search_result_ids({"query": query})
        plain = search_result_ids({"query": query}, rank=False)
        assert sorted(ranked) == sorted(plain)
        found = execute_catalog_search({"query": query})
        assert found["total_matches"] == len(plain)
        assert found["status"] == ("ok" if plain else "no_match")
        assert found["recipe_ids"] == ranked[:3]


def test_facet_only_query_keeps_catalog_order() -> None:
    plain = search_result_ids({"query": "vegan"}, rank=False)
    assert plain
    assert search_result_ids({"query": "vegan"}) == plain


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
