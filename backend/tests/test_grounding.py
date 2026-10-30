import re
from datetime import date
from decimal import Decimal

import pytest

from app.agent.budget_tool import budget_summary_answer, execute_budget_summary
from app.agent.catalog_tool import TOOL_NAME, catalog_answer, execute_catalog_search
from app.agent.chat_answer import CLARIFICATION, render_public_answer
from app.agent.grounding import (
    MAX_REPLY_CHARS,
    FactSet,
    Verdict,
    facts_from_payloads,
    validate,
    with_notice,
)
from app.agent.ingredient_tool import INGREDIENT_TOOL, execute_ingredient_facts
from app.agent.plan_tools import (
    GET_MEAL_TOOL,
    GET_PLAN_TOOL,
    execute_get_meal,
    execute_get_plan,
)
from app.agent.price_tool import PRICE_TOOL, execute_price_lines
from app.agent.read_answers import read_tool_answer
from app.agent.substitute_tool import SUBSTITUTE_TOOL, execute_substitute
from app.domain.budget import BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.plan_revision import PlanRevisionInput

_BUDGET = BudgetResult(10_000, 0, False, ())
_TACOS = {"recipe_id": "chicken_tacos", "servings": 2}
_REAL_SWAP = {
    **_TACOS,
    "replace_ingredient_id": "chicken_breast",
    "with_ingredient_id": "chickpeas",
}
_SCALE = {
    **_TACOS,
    "scale_ingredient_id": "chicken_breast",
    "scale_factor_percent": 50,
}


def _facts(**payload: object) -> FactSet:
    return facts_from_payloads([("tool", payload)])


def _revision(meals: list[dict[str, object]]) -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "snapshot": {
                "meals": meals,
                "pantry_ingredient_ids": [],
                "plan_cap_cents": 5_000,
            },
        }
    )


def _grounded(
    tool: str, payload: dict[str, object], *, stale: bool = False
) -> tuple[str, Verdict]:
    answer = read_tool_answer([(tool, payload)], stale=stale)
    assert answer is not None
    verdict = validate(answer, facts_from_payloads([(tool, payload)]))
    assert verdict.ok, (answer, verdict)
    return answer, verdict


def _macros(kcal: int, protein: int, carbs: int, fat: int) -> dict[str, object]:
    return {
        "energy_kcal": kcal,
        "protein_mg": protein,
        "carbohydrate_mg": carbs,
        "fat_mg": fat,
    }


# Self-consistency: every server template passes its own validator.


def test_substitute_swapped_with_prices_is_grounded() -> None:
    payload = execute_substitute(_REAL_SWAP, _BUDGET)
    answer, verdict = _grounded(SUBSTITUTE_TOOL, payload)
    assert "USD $23.73" in answer
    assert verdict.has_money


def test_substitute_scale_is_grounded() -> None:
    answer, _ = _grounded(SUBSTITUTE_TOOL, execute_substitute(_SCALE, _BUDGET))
    assert "Scaled to 50 percent." in answer


def test_substitute_gram_difference_of_rounded_values_is_grounded() -> None:
    def side(ingredient_id: str, protein_mg: int) -> dict[str, object]:
        line = {"ingredient_id": ingredient_id, "name": ingredient_id}
        return {
            "ingredients": [line],
            "per_serving": _macros(500, protein_mg, 30_000, 10_000),
        }

    payload: dict[str, object] = {
        "recipe_id": "chicken_tacos",
        "servings": 2,
        "change": {
            "replace_ingredient_id": "chicken_breast",
            "with_ingredient_id": "chickpeas",
        },
        "before": side("chicken_breast", 25_600),
        "after": side("chickpeas", 15_400),
        "delta": {"per_serving": _macros(0, -10_200, 0, 0)},
        "assumptions": [],
        "price": {"before": {}, "after": {}, "delta_cents": None},
    }
    answer, verdict = _grounded(SUBSTITUTE_TOOL, payload)
    assert "protein 26 to 15 g (-11 g)" in answer
    assert not verdict.has_money


def test_price_lines_are_grounded() -> None:
    args: dict[str, object] = {
        "meals": [_TACOS, {"recipe_id": "bean_tacos", "servings": 1}]
    }
    answer, verdict = _grounded(PRICE_TOOL, execute_price_lines(args, _BUDGET, None))
    assert "USD $25.02" in answer and "(1 serving)" in answer
    assert verdict.has_money
    swapped = execute_price_lines({"meals": [_REAL_SWAP]}, _BUDGET, 500)
    _grounded(PRICE_TOOL, swapped, stale=True)
    scaled = execute_price_lines({"meals": [_SCALE]}, _BUDGET, None)
    _grounded(PRICE_TOOL, scaled)
    bean: dict[str, object] = {"meals": [{"recipe_id": "bean_tacos"}]}
    _grounded(PRICE_TOOL, execute_price_lines(bean, _BUDGET, None))


def test_price_lines_incomplete_has_no_money() -> None:
    estimate = {"total_cents": None, "available_cents": 10_000, "accepted": False}
    payload: dict[str, object] = {"meals": [_TACOS], "estimate": estimate}
    _, verdict = _grounded(PRICE_TOOL, payload)
    assert not verdict.has_money


def test_get_plan_is_grounded() -> None:
    meals = [_TACOS, {"recipe_id": "bean_tacos", "servings": 1}]
    payload = execute_get_plan({}, _revision(meals), _BUDGET)
    answer, verdict = _grounded(GET_PLAN_TOOL, payload)
    assert "Total: 1060 kcal, 67 g protein" in answer
    assert verdict.has_money
    _grounded(GET_PLAN_TOOL, execute_get_plan({}, None, _BUDGET))


def test_get_meal_is_grounded() -> None:
    payload = execute_get_meal({"recipe_id": "chicken_tacos"})
    _, verdict = _grounded(GET_MEAL_TOOL, payload)
    assert not verdict.has_money


def test_ingredient_facts_found_ambiguous_and_unknown_are_grounded() -> None:
    answer, _ = _grounded(INGREDIENT_TOOL, execute_ingredient_facts({"name": "beef"}))
    assert "(80% lean) per 100 g" in answer
    answer, _ = _grounded(INGREDIENT_TOOL, execute_ingredient_facts({"name": "pork"}))
    assert answer.startswith("Which one do you mean")
    unknown: dict[str, object] = {"status": "unknown", "name": "x", "candidates": []}
    _grounded(INGREDIENT_TOOL, unknown)


def test_ingredient_facts_live_is_grounded() -> None:
    def live(name: str, fdc_id: int) -> dict[str, object]:
        return {
            "fdc_id": fdc_id,
            "name": name,
            "brand": None,
            "data_type": "Branded",
            "per_100g": _macros(321, 18_400, 3_000, 25_000),
        }

    payload: dict[str, object] = {
        "status": "live",
        "name": "paneer",
        "live": [live("paneer", 11), live("paneer cheese", 12)],
        "candidates": [],
    }
    answer, _ = _grounded(INGREDIENT_TOOL, payload)
    assert "321 kcal" in answer and "(USDA FDC 11)" in answer


@pytest.mark.parametrize("query", ["tacos", "low carb"])
def test_catalog_answer_is_grounded(query: str) -> None:
    payload = execute_catalog_search({"query": query})
    facts = facts_from_payloads([(TOOL_NAME, payload)])
    verdict = validate(catalog_answer(payload), facts)
    assert verdict.ok, verdict


def test_catalog_server_notes_only_ground_for_the_search_tool() -> None:
    payload = execute_catalog_search({"query": "tacos"})
    verdict = validate(catalog_answer(payload), facts_from_payloads([("t", payload)]))
    assert verdict.unmatched == ("30",)


def test_budget_summary_is_grounded() -> None:
    budget = BudgetResult(10_000, 250, True, ())
    payload = execute_budget_summary(
        {}, budget, date(2026, 9, 1), spending_source="manual"
    )
    answer = budget_summary_answer(budget, date(2026, 9, 1), spending_source="manual")
    verdict = validate(answer, facts_from_payloads([("get_budget_summary", payload)]))
    assert verdict.ok, verdict
    assert verdict.has_money


@pytest.mark.parametrize(
    ("plan", "budget"),
    [
        ({"total_cents": 1_250, "accepted": True}, {"stale": False}),
        (
            {"total_cents": 1_250, "accepted": False},
            {"available_cents": 1_000, "stale": True},
        ),
        ({"total_cents": None, "accepted": False}, {"stale": False}),
    ],
)
def test_planned_answer_is_grounded(
    plan: dict[str, object], budget: dict[str, object]
) -> None:
    candidate: dict[str, object] = {"plan": plan, "budget": budget}
    answer = render_public_answer(candidate)
    verdict = validate(answer, facts_from_payloads([("plan_groceries", candidate)]))
    assert verdict.ok, (answer, verdict)
    assert verdict.has_money == (plan["total_cents"] is not None)
    assert SAMPLE_ESTIMATE_NOTICE in answer


def test_static_clarification_is_grounded() -> None:
    assert validate(CLARIFICATION, FactSet()).ok


# Fact extraction.


def test_fact_kinds_are_split_by_key() -> None:
    facts = _facts(
        total_cents=-120,
        delta_cents=5,
        protein_mg=26_352,
        energy_kcal=474,
        scale_factor_percent=50,
        servings=2,
        fdc_id=174036,
        flag=True,
        nothing=None,
        nested=[{"carbohydrate_mg": 27_500}],
    )
    assert facts.money == {-120}
    assert facts.deltas == {("money", Decimal(5))}
    assert {Decimal(26), Decimal("26.4"), Decimal(28)} <= facts.mass
    assert facts.energy == {Decimal(474)}
    assert facts.percent == {Decimal(50)}
    assert facts.count == {Decimal(2), Decimal(174036)}
    assert Decimal(1) not in facts.count | facts.generic


def test_numbers_inside_strings_and_keys_are_generic_facts() -> None:
    facts = _facts(name='80% lean 93/7 1/8" fat', note="30 g or more", per_100g=1)
    assert {80, 93, 7, 1, 8, 30, 100} <= facts.generic
    assert facts.percent == {Decimal(80)}


# Accepted and rejected numbers.


def test_money_must_match_exactly() -> None:
    facts = _facts(total_cents=1234)
    assert validate("The total is $12.34.", facts).ok
    assert validate("The total is 12.34 dollars.", facts).ok
    wrong = validate("The total is $12.35.", facts)
    assert wrong.reasons == ("unmatched_number",)
    assert wrong.unmatched == ("$12.35",)
    assert wrong.has_money
    assert validate("About $12.", facts).unmatched == ("$12",)


def test_mass_matches_whole_or_one_decimal_grams() -> None:
    facts = _facts(protein_mg=26_352)
    assert validate("It has 26 g protein.", facts).ok
    assert validate("It has 26.4 grams of protein.", facts).ok
    assert validate("It has 26g protein.", facts).ok
    wrong = validate("It has 27 g protein.", facts)
    assert wrong.unmatched == ("27",)


def test_energy_about_allows_rounding_to_ten() -> None:
    facts = _facts(energy_kcal=474)
    assert validate("It has 474 kcal.", facts).ok
    assert validate("It has 474 calories.", facts).ok
    assert validate("It has about 480 kcal.", facts).ok
    assert validate("It has roughly 470 calories.", facts).ok
    assert not validate("It has about 500 kcal.", facts).ok
    assert not validate("It has 480 kcal.", facts).ok
    assert not validate("It has about 475 kcal.", facts).ok


def test_percent_needs_a_percent_fact() -> None:
    facts = _facts(name="ground beef (80% lean)", note="50 g")
    assert validate("The beef is 80% lean.", facts).ok
    assert validate("It is 80 percent lean.", facts).ok
    assert validate("The beef is 93/7.", _facts(name="beef 93/7")).ok
    assert validate("Use 50 g.", facts).ok
    assert validate("Use 50%.", facts).unmatched == ("50",)


def test_counts_need_a_count_fact() -> None:
    facts = _facts(servings=2)
    assert validate("That is 2 servings.", facts).ok
    assert validate("That is two servings.", facts).ok
    missing = validate("Make 3 tacos.", facts)
    assert missing.reasons == ("unmatched_number",)
    assert missing.unmatched == ("3",)
    assert validate("Make three tacos.", facts).unmatched == ("3",)


def test_floats_are_generic_facts_not_counts() -> None:
    facts = _facts(ratio=2.5)
    assert facts.count == set()
    assert validate("That is 2.5 servings.", facts).ok
    assert not validate("That is 2 servings.", facts).ok


def _swap(before_mg: int, after_mg: int) -> dict[str, object]:
    return {
        "before": {"per_serving": {"protein_mg": before_mg, "energy_kcal": 500}},
        "after": {"per_serving": {"protein_mg": after_mg, "energy_kcal": 480}},
    }


def test_signed_change_must_match_a_real_before_after_delta() -> None:
    facts = _facts(**_swap(26_000, 15_000))
    assert validate("Protein 26 to 15 g (-11 g).", facts).ok
    assert validate("Energy changes by -20 kcal.", facts).ok
    wrong_sign = validate("Protein changes by +11 g.", facts)
    assert wrong_sign.reasons == ("unmatched_number",)
    assert wrong_sign.unmatched == ("+11",)
    assert not validate("Energy changes by +20 kcal.", facts).ok
    assert not validate("Protein changes by -13 g.", facts).ok
    assert not validate("Protein is 11 g.", facts).ok


def test_signed_change_is_not_a_difference_of_unrelated_facts() -> None:
    facts = facts_from_payloads(
        [("a", {"protein_mg": 26_000}), ("b", {"protein_mg": 15_000})]
    )
    assert validate("Protein is 26 g or 15 g.", facts).ok
    assert not validate("Protein changes by +11 g.", facts).ok
    assert not validate("Protein changes by -11 g.", facts).ok
    pair = _facts(a_mg=26_000, b_mg=15_000)
    assert not validate("Protein changes by -11 g.", pair).ok


def test_explicit_delta_keys_are_signed_facts_only() -> None:
    facts = _facts(delta_cents=-250, delta_percent={"energy_kcal": -4}, price_cents=99)
    assert validate("That is -$2.50 less.", facts).ok
    assert validate("That is -USD $2.50 less.", facts).ok
    assert validate("Energy is -4%.", facts).ok
    assert not validate("That is +$2.50.", facts).ok
    assert not validate("That costs $2.50.", facts).ok
    assert not validate("Energy is 4%.", facts).ok


def test_negative_plain_fact_matches_only_a_minus_sign() -> None:
    facts = _facts(remaining_cents=-120)
    assert validate("Remaining: USD -$1.20.", facts).ok
    assert not validate("Remaining: $1.20.", facts).ok
    assert not validate("Remaining: +$1.20.", facts).ok


def test_ids_dates_and_hashes_ground_no_numbers() -> None:
    uuid = "3f2a9c41-8b7e-4d21-9a6c-5e1f0b2d7a43"
    facts = _facts(
        plan_id=uuid,
        id="77",
        recipe_ids=[88],
        copy=uuid,
        digest="0123456789abcdef",
        day="2026-09-01",
        stamp="2026-09-01T10:30:00Z",
        fdc_id=5,
    )
    assert facts.count == {Decimal(5)}
    assert facts.generic == set()
    for reply in ("It has 41 g.", "Make 77 tacos.", "Make 88 tacos.", "In 2026."):
        assert not validate(reply, facts).ok
    assert validate("USDA FDC 5.", facts).ok


def test_money_words_set_has_money_and_match_cents() -> None:
    facts = _facts(a_cents=50, b_cents=1_200)
    for reply in ("50 cents", "USD 12", "12 USD", "12 dollars", "USD $12.00"):
        verdict = validate(f"It costs {reply}.", facts)
        assert verdict.ok and verdict.has_money, reply
    for reply in ("51 cents", "USD 13", "13 USD"):
        verdict = validate(f"It costs {reply}.", facts)
        assert verdict.unmatched and verdict.has_money, reply


def test_ranges_share_the_unit() -> None:
    facts = _facts(a_kcal=474, b_kcal=489)
    assert validate("From 474 to 489 kcal.", facts).ok
    assert not validate("From 474 to 490 kcal.", facts).ok


def test_which_one_is_not_a_number_but_one_serving_is() -> None:
    assert validate("Which one do you mean?", FactSet()).ok
    assert validate("Pick one of them.", FactSet()).ok
    assert validate("Add one serving.", FactSet()).unmatched == ("1",)


@pytest.mark.parametrize(
    "word",
    [
        "twenty",
        "hundred",
        "dozen",
        "half",
        "thirteen",
        "zero",
        "twice",
        "double",
        "triple",
        "quadruple",
        "quarter",
        "billion",
        "once",
    ],
)
def test_other_number_words_fail(word: str) -> None:
    verdict = validate(f"Use {word} grams.", FactSet())
    assert verdict.reasons == ("number_word",)
    assert verdict.unmatched == ()


def test_dates_and_times_are_not_exempt() -> None:
    verdict = validate("Order by 2026-09-01 at 10:30.", FactSet())
    assert verdict.reasons == ("unmatched_number",)
    assert {"2026", "09", "01", "10", "30"} <= set(verdict.unmatched)
    assert validate("Order by 10:30.", _facts(a=10, b=30)).ok


# Other checks.


def test_kroger_fails_with_store_price() -> None:
    verdict = validate("Kroger sells it for $2.50.", _facts(price_cents=250))
    assert verdict.reasons == ("store_price",)
    assert not validate("at kroger", FactSet()).ok


@pytest.mark.parametrize(
    "reply",
    [
        "This meal is gluten-free.",
        "The tacos are also gluten free.",
        "A gluten-free dish for you.",
        "It's gluten-free.",
        "Chicken tacos: gluten-free.",
        "These gluten-free tacos",
        "They are naturally and fully gluten free",
        "It is safe for a nut allergy.",
        "That is allergy-free.",
        "This is allergen free.",
        "It is celiac-safe.",
        "That is a medical choice.",
        "It cures colds.",
        "Beans treat nothing, but this treats cravings.",
        "It prevents spikes.",
        "A diagnosis follows.",
    ],
)
def test_forbidden_claims_fail(reply: str) -> None:
    assert validate(reply, FactSet()).reasons == ("forbidden_claim",)


def test_gluten_free_ingredient_note_is_allowed() -> None:
    assert validate("These are made with gluten-free ingredients.", FactSet()).ok
    assert validate("Made with gluten free ingredients.", FactSet()).ok
    reply = (
        "Gluten-free ingredients describes the ingredients only. "
        "I cannot claim gluten-free, celiac, allergy, or cross-contact safety."
    )
    assert validate(reply, FactSet()).ok


def test_length_and_empty_checks() -> None:
    assert validate("a" * MAX_REPLY_CHARS, FactSet()).ok
    assert validate("a" * (MAX_REPLY_CHARS + 1), FactSet()).reasons == ("too_long",)
    assert validate("  ", FactSet()).reasons == ("empty",)


def test_verdict_names_only_numeric_tokens() -> None:
    reply = "SENTINELWORD costs $9.99 and has 77 g, 5 percent, 31 kcal, and 4."
    verdict = validate(reply, FactSet())
    assert verdict.unmatched == ("$9.99", "77", "5", "31", "4")
    assert all(re.fullmatch(r"\$?[\d.,]+", token) for token in verdict.unmatched)
    assert "SENTINELWORD" not in repr(verdict)
    assert verdict.reasons == ("unmatched_number",)


def test_has_money_flags_dollar_tokens_only() -> None:
    facts = _facts(a_cents=500, servings=5)
    assert validate("It costs $5.", facts).has_money
    assert validate("It costs 5 dollars.", facts).has_money
    assert not validate("That is 5 servings.", facts).has_money


def test_with_notice_appends_once() -> None:
    once = with_notice("The total is $5.")
    assert once == f"The total is $5. {SAMPLE_ESTIMATE_NOTICE}"
    assert with_notice(once) == once
