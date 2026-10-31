import re
import unicodedata
from datetime import date
from decimal import Decimal

import pytest

from app.agent import catalog_tool, chat_answer, grounding
from app.agent.budget_tool import budget_summary_answer, execute_budget_summary
from app.agent.catalog_tool import TOOL_NAME, catalog_answer, execute_catalog_search
from app.agent.chat_answer import CLARIFICATION, render_public_answer
from app.agent.grounding import (
    MAX_REPLY_CHARS,
    FactSet,
    Verdict,
    _whole_grams,
    facts_from_payloads,
    normalize,
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
from app.agent.proposal_tool import PROPOSAL_TOOL, execute_propose
from app.agent.read_answers import read_tool_answer
from app.agent.substitute_tool import SUBSTITUTE_TOOL, execute_substitute
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.domain.catalog import INGREDIENTS, RECIPES
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.domain.meal_tags import CARNIVORE_NOTE, KETO_NOTE
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


def _without_warning(answer: str) -> str:
    # The server appends the warning after validation; a model reply never has it.
    return answer.replace(STALE_SPENDING_WARNING, "").strip()


def _grounded(
    tool: str, payload: dict[str, object], *, stale: bool = False
) -> tuple[str, Verdict]:
    answer = read_tool_answer([(tool, payload)], stale=stale)
    assert answer is not None
    answer = _without_warning(answer)
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


@pytest.mark.parametrize(
    "reply",
    [
        "Bake tofu for 20 minutes",
        "if you'd like tofu",
        "take tomatoes",
        "make tortillas",
    ],
)
def test_diet_check_ignores_letters_inside_other_words(reply: str) -> None:
    verdict = validate(reply, FactSet(generic={Decimal(20)}))
    assert "forbidden_claim" not in verdict.reasons


@pytest.mark.parametrize(
    "reply",
    [
        "These are vegan.",
        "a keto meal",
        "plant based",
        "dairy free",
        "Low-fat.",
        "Great for vegetarians.",
        "These suit vegans.",
        "A ketogenic dinner.",
        "It is keto_friendly.",
    ],
)
def test_diet_labels_fail_from_a_word_start(reply: str) -> None:
    assert "forbidden_claim" in validate(reply, FactSet()).reasons


def test_spaced_out_letters_pass_the_diet_check() -> None:
    # Known trade-off: only the safety claims keep the squashed-letter match.
    assert "forbidden_claim" not in validate("v e g a n", FactSet()).reasons


@pytest.mark.parametrize(
    "reply",
    [
        "Watch your Blood Sugar.",
        "Watch your blood **sugar**.",
        "Fine with blood _pressure_.",
        "Watch your blood_sugar.",
        "Watch your blood-sugar.",
        "Watch your bloodsugar.",
        "Fine with bloodpressure.",
        "It may affect insulin.",
        "Good for a diabetic diet.",
        "Fine with prediabetes.",
        "Helps with high blood\npressure.",
        "Lowers cholesterol and hypertension.",
        "Safe during pregnancy.",
        "Spikes glucose.",
        "Oats suit a _diabetic_ diet.",
        "Fine with _high blood pressure_.",
        "Helps prevent hyperglycemia",
        "a hypoglycemic snack",
        "antidiabetic",
    ],
)
def test_medical_conditions_fail_anywhere_in_the_text(reply: str) -> None:
    assert "medical_claim" in validate(reply, FactSet(generic={Decimal(2)})).reasons


def test_the_c09_sentence_fails_only_the_medical_check() -> None:
    reply = "Overnight oats are a good low-glycemic-index choice for type 2 diabetes."
    verdict = validate(reply, FactSet(generic={Decimal(2)}))
    assert verdict.reasons == ("medical_claim",), verdict


def test_a_repeated_user_condition_fails_only_the_medical_check() -> None:
    reply = "You asked about diabetes. The plan has 43 g of carbs per serving."
    verdict = validate(reply, _facts(carbohydrate_mg=43_000))
    assert verdict.reasons == ("medical_claim",), verdict


@pytest.mark.parametrize("reply", ["Kidney beans add fiber.", "A hearty ragout."])
def test_kidney_heart_and_gout_words_pass_the_medical_check(reply: str) -> None:
    assert "medical_claim" not in validate(reply, FactSet()).reasons


def test_an_exempt_server_sentence_skips_the_medical_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentence = "Glucose is not a plan fact."
    monkeypatch.setattr(
        grounding,
        "_SERVER_SENTENCE",
        re.compile(r"(?:\A\s*|(?<=[.!?])\s+)(?:" + re.escape(sentence) + r")"),
    )
    assert "medical_claim" not in validate(sentence, FactSet()).reasons
    other = "Oats are fine. " + sentence
    assert "medical_claim" not in validate(other, FactSet()).reasons
    assert "medical_claim" in validate("It spikes glucose.", FactSet()).reasons
    assert "medical_claim" in validate("Oats " + sentence, FactSet()).reasons


def test_spaced_out_letters_pass_the_medical_check() -> None:
    assert "medical_claim" not in validate("d i a b e t e s", FactSet()).reasons


def test_a_server_sentence_alone_still_passes_the_medical_check() -> None:
    sentence = re.split(r"(?<=\.) ", catalog_tool._SAFETY)[0]
    verdict = validate(sentence, facts_from_payloads([(TOOL_NAME, {})]))
    assert verdict.ok, verdict


@pytest.mark.parametrize(
    "reply",
    [
        "Servings from your plan: 2.",
        "Protein is 14 g. Servings from your plan: 2.",
        "- Servings from your plan: 2.",
        "Protein is 14 g\n- Servings from your plan: 2.",
    ],
)
def test_servings_sentence_is_exempt_where_allowed(reply: str) -> None:
    facts = _facts(servings=2, protein_mg=14_000)
    assert validate(reply, facts).ok


def test_servings_sentence_is_not_exempt_mid_sentence() -> None:
    reply = "Plan Servings from your plan: 2."
    verdict = validate(reply, FactSet(generic={Decimal(2)}))
    assert not verdict.ok
    assert "forbidden_claim" in verdict.reasons


@pytest.mark.parametrize(
    "reply",
    [
        "Servings from your plan: 999.",
        "Protein is 14 g. Servings from your plan: 999.",
        "- Servings from your plan: 999.",
        "Protein is 14 g\n- Servings from your plan: 999.",
    ],
)
def test_exempt_servings_still_require_a_count_fact(reply: str) -> None:
    facts = _facts(servings=2, protein_mg=14_000, note="Option 999")
    verdict = validate(reply, facts)
    assert verdict.reasons == ("unmatched_number",)
    assert verdict.unmatched == ("999",)


def test_exempt_servings_cannot_use_only_a_generic_number() -> None:
    verdict = validate("Servings from your plan: 2.", _facts(note="Option 2"))
    assert verdict.reasons == ("unmatched_number",)
    assert verdict.unmatched == ("2",)


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
    unstripped = read_tool_answer([(PRICE_TOOL, swapped)], stale=True)
    assert unstripped is not None and STALE_SPENDING_WARNING in unstripped
    facts = facts_from_payloads([(PRICE_TOOL, swapped)])
    assert not validate(unstripped, facts).ok
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


@pytest.mark.parametrize(
    ("query", "note"),
    [
        ("tacos", None),
        ("low carb", KETO_NOTE),
        ("keto", KETO_NOTE),
        ("chicken", CARNIVORE_NOTE),
    ],
)
def test_catalog_answer_is_grounded(query: str, note: str | None) -> None:
    payload = execute_catalog_search({"query": query, "limit": 1})
    answer = catalog_answer(payload)
    if note is not None:
        assert note in answer
    verdict = validate(answer, facts_from_payloads([(TOOL_NAME, payload)]))
    assert verdict.ok, (answer, verdict)


def test_catalog_server_notes_only_ground_for_the_search_tool() -> None:
    payload = execute_catalog_search({"query": "tacos"})
    verdict = validate(catalog_answer(payload), facts_from_payloads([("t", payload)]))
    assert verdict.unmatched == ("30",)


def test_budget_summary_is_grounded() -> None:
    budget = BudgetResult(10_000, 250, True, ())
    payload = execute_budget_summary(
        {}, budget, date(2026, 9, 1), spending_source="manual"
    )
    raw = budget_summary_answer(budget, date(2026, 9, 1), spending_source="manual")
    facts = facts_from_payloads([("get_budget_summary", payload)])
    if STALE_SPENDING_WARNING in raw:
        assert not validate(raw, facts).ok
    verdict = validate(_without_warning(raw), facts)
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
    raw = render_public_answer(candidate)
    facts = facts_from_payloads([("plan_groceries", candidate)])
    if STALE_SPENDING_WARNING in raw:
        assert not validate(raw, facts).ok
    answer = _without_warning(raw)
    verdict = validate(answer, facts)
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
    assert facts.mass == set()
    assert {
        ("protein", "mass", False, Decimal(26)),
        ("protein", "mass", False, Decimal("26.4")),
        ("carbohydrate", "mass", False, Decimal(28)),
    } <= facts.nutrition
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


def _changes(*deltas: tuple[str, int]) -> FactSet:
    return FactSet(deltas={(kind, Decimal(value)) for kind, value in deltas})


def test_direction_word_binds_an_unsigned_change_to_a_signed_delta() -> None:
    facts = _facts(delta={"fat_mg": 2_500, "energy_kcal": 38})
    reply = "About 2.5 g more fat and 38 kcal more energy."
    assert validate(reply.lower(), facts).ok
    assert validate("about 2.5 g more fat and 38 kcal more energy", facts).ok
    assert validate("**2.5 g more fat**", facts).ok
    assert validate("2.5 g Higher fat, 38 kcal EXTRA.", facts).ok


def test_bound_change_takes_the_sign_of_its_direction_word() -> None:
    facts = _facts(delta={"fat_mg": 2_500})
    verdict = validate("2.5 g less fat", facts)
    assert verdict.reasons == ("unmatched_number",)
    assert verdict.unmatched == ("-2.5",)
    assert validate("2.5 g more fat", facts).ok
    carbs = _facts(delta={"carbohydrate_mg": -5_000})
    assert validate("5 g fewer carbs", carbs).ok
    assert not validate("5 g more carbs", carbs).ok
    assert validate("9% lower", _changes(("percent", -9))).ok


def test_bound_change_never_matches_the_absolute_pool() -> None:
    facts = _facts(fat_mg=2_500, note="2.5")
    assert validate("2.5 g of fat", facts).ok
    assert not validate("2.5 g more fat", facts).ok
    assert not validate("2.5 g less fat", facts).ok
    assert not validate("about 40 kcal more", FactSet(energy={Decimal(38)})).ok


def test_bound_decrease_may_match_a_negative_pool_value() -> None:
    assert validate("5 g less", FactSet(mass={Decimal(-5)})).ok


def test_direction_word_binds_only_a_unit_number_directly_before_it() -> None:
    facts = FactSet(mass={Decimal(5)}, count={Decimal(2)}, money={Decimal(200)})
    assert validate("Add 5 g, and more fat later.", facts).ok
    assert validate("Make 2 servings more often.", facts).ok
    assert validate("It costs $2 more.", facts).ok
    assert validate("That is up from 5 g.", facts).ok
    assert not validate("That is 3 g more.", facts).ok
    assert validate("Look for more options.", facts).ok


def test_a_bare_count_before_a_direction_word_stays_unbound() -> None:
    assert validate("Add 2 more", FactSet(count={Decimal(2)})).ok
    assert not validate("Add 2 more", _changes(("count", 2))).ok


def test_a_range_before_a_direction_word_stays_unbound() -> None:
    facts = FactSet(mass={Decimal(2), Decimal(3)})
    assert validate("2 to 3 g more", facts).ok
    assert not validate("2 to 3 g more", _changes(("mass", 2), ("mass", 3))).ok


def test_direction_verb_binds_the_number_after_it_and_carries_over_a_list() -> None:
    swing = _facts(
        delta={"fat_mg": 2_500, "carbohydrate_mg": -4_500, "energy_kcal": 38}
    )
    reply = (
        "each serving gains about 2.5 g fat and 38 kcal while losing about 4.5 g carbs"
    )
    assert validate(reply, swing).ok
    absolute = _facts(fat_mg=2_500, carbohydrate_mg=4_500, energy_kcal=38)
    assert not validate(reply, absolute).ok
    swap = _facts(delta={"energy_kcal": 38, "fat_mg": 2_500})
    assert validate("The swap adds about 38 kcal and 2.5 g of fat per serving", swap).ok
    assert validate("It ADDED 38 kcal, 2.5 g fat", swap).ok


def test_direction_verb_before_a_number_takes_the_verb_sign() -> None:
    drop = _facts(**_swap(31_200, 28_400))
    reply = "Protein drops by **2.8 g** (from 31.2 g to 28.4 g)"
    assert validate(reply, drop).ok
    rise = _facts(**_swap(28_400, 31_200))
    verdict = validate(reply, rise)
    assert verdict.unmatched == ("-2.8",)
    energy = FactSet(
        deltas={("energy", Decimal(28))}, energy={Decimal(559), Decimal(587)}
    )
    assert validate("Energy rises by 28 kcal (from 559 kcal to 587 kcal)", energy).ok


def test_direction_verb_never_matches_the_absolute_pool() -> None:
    assert not validate(
        "Fat increases by about 69 g total", FactSet(mass={Decimal(69)})
    ).ok
    assert not validate("It gains 38 kcal", FactSet(energy={Decimal(38)})).ok
    assert validate("It loses 5 g", FactSet(mass={Decimal(-5)})).ok


def test_direction_verb_run_ends_at_but_and_never_binds_counts() -> None:
    facts = _facts(delta={"fat_mg": 2_500}, energy_kcal=38, servings=2)
    assert validate("gains 2.5 g fat but 38 kcal", facts).ok
    assert not validate(
        "gains 2.5 g fat but 38 kcal", FactSet(nutrition=facts.nutrition)
    ).ok
    assert validate("It adds flavor and 2 servings", FactSet(count={Decimal(2)})).ok
    assert validate("Add 5 g, and more fat later.", FactSet(mass={Decimal(5)})).ok


def test_a_run_ends_at_a_run_end_word_inside_the_gap() -> None:
    facts = _facts(delta={"fat_mg": 2_500}, energy_kcal=38)
    reply = "gains 2.5 g fat while protein and 38 kcal"
    assert validate(reply, facts).ok
    assert not validate(reply, FactSet(nutrition=facts.nutrition)).ok


def test_a_count_after_a_direction_verb_is_not_bound() -> None:
    assert validate("The swap adds 2 servings", FactSet(count={Decimal(2)})).ok


def test_a_range_after_a_direction_verb_is_not_bound() -> None:
    facts = FactSet(energy={Decimal(559), Decimal(587)})
    assert validate("Energy rises by 559 to 587 kcal", facts).ok


def test_trailing_direction_word_wins_over_a_leading_verb() -> None:
    facts = _changes(("mass", 5))
    assert validate("It drops 5 g more", facts).ok
    assert not validate("It adds 5 g less", facts).ok


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


def test_delta_key_holds_signed_facts_only() -> None:
    payload = {
        "status": "swapped",
        "servings": 2,
        "delta": {
            "per_serving": _macros(0, 11_000, 0, 0),
            "total": _macros(0, 22_000, 0, 0),
        },
        "delta_percent": {"protein_mg": 43},
    }
    facts = _facts(**payload)
    assert facts.mass == set()
    assert facts.percent == set()
    assert validate("Protein changes by +11 g.", facts).ok
    assert validate("Protein changes by +22 g.", facts).ok
    assert not validate("The total changes by +22 g.", facts).ok
    assert validate("Protein changes by +43%.", facts).ok
    assert not validate("Protein changes by -11 g.", facts).ok
    wrong = validate("This meal has 11 g of protein.", facts)
    assert wrong.reasons == ("unmatched_number",)
    assert wrong.unmatched == ("11",)
    assert not validate("This meal has 43% protein.", facts).ok


def test_real_substitute_delta_is_a_signed_fact() -> None:
    payload = execute_substitute(_REAL_SWAP, _BUDGET)
    delta = payload["delta"]
    assert isinstance(delta, dict)
    per_serving = delta["per_serving"]
    assert isinstance(per_serving, dict)
    protein_mg = per_serving["protein_mg"]
    assert isinstance(protein_mg, int) and protein_mg != 0
    facts = facts_from_payloads([(SUBSTITUTE_TOOL, payload)])
    grams = _whole_grams(protein_mg)
    assert ("protein", "mass", True, grams) in facts.nutrition
    sign = "+" if grams > 0 else "-"
    assert validate(f"Protein changes by {sign}{abs(grams)} g.", facts).ok


def test_delta_subtree_adds_no_strings_floats_or_key_names() -> None:
    facts = _facts(
        delta={
            "note 7 g": "30 g or more",
            "ratio": 2.5,
            "per_serving": {"protein_mg": 11_000, "label 9": "80% lean"},
        },
        delta_note="45 g",
    )
    assert facts.generic == set()
    assert facts.percent == set()
    assert facts.deltas == set()
    assert facts.nutrition == {
        ("protein", "mass", True, Decimal(11)),
        ("protein", "mass", True, Decimal("11.0")),
        ("protein", "milli", True, Decimal(11_000)),
    }
    assert validate("Protein changes by +11 g.", facts).ok
    for reply in ("Use 30 g.", "Use 2.5 servings.", "Use 7 g.", "Use 45 g."):
        assert not validate(reply, facts).ok, reply


def test_changes_skip_id_keys() -> None:
    facts = _facts(
        before={"recipe_id": 10, "per_serving": {"protein_mg": 26_000}},
        after={"recipe_id": 3, "per_serving": {"protein_mg": 15_000}},
    )
    assert ("count", Decimal(-7)) not in facts.deltas
    assert not validate("Changes by -7 servings.", facts).ok
    assert validate("Protein changes by -11 g.", facts).ok


def test_ids_embedded_in_longer_strings_ground_no_numbers() -> None:
    facts = _facts(
        note="Revision 3f2a9c41-0000-4000-8000-000000000041 for 2 servings",
        when="Planned on 2026-09-01 for 3 meals",
        digest="sha 0123456789abcdef0123 done",
    )
    assert facts.generic == {2, 3}
    assert not validate("It has 41 g.", facts).ok
    assert not validate("It has 2026 g.", facts).ok
    assert validate("That is 2 servings.", facts).ok


def test_unicode_dashes_and_spaces_are_normalized() -> None:
    nbsp, thin = " ", " "
    for reply in (
        "These are gluten‑free.",
        "It is celiac‑safe.",
        f"It is allergy{nbsp}free.",
        f"It is safe{nbsp}for you.",
        f"It is safe{thin}for you.",
        "It is gluten–free.",
        "It is gluten−free.",
        "It is allergen‐free.",
    ):
        assert validate(reply, FactSet()).reasons == ("forbidden_claim",), reply
    money = validate("It costs ＄12.", _facts(price_cents=1_200))
    assert money.ok and money.has_money
    assert validate("It costs ＄12.", FactSet()).unmatched == ("$12",)
    assert validate(f"It has 26{nbsp}g protein.", _facts(protein_mg=26_000)).ok


def test_only_the_exact_server_safety_sentence_is_exempt() -> None:
    reply = "I cannot claim gluten-free status, but these tacos are gluten-free."
    assert validate(reply, FactSet()).reasons == ("forbidden_claim",)
    sentence = "I cannot claim gluten-free, celiac, allergy, or cross-contact safety."
    assert validate(sentence, FactSet()).ok
    assert not validate(f"{sentence} These tacos are gluten-free.", FactSet()).ok
    assert not validate(sentence.replace("celiac", "coeliac"), FactSet()).ok


def test_minus_sign_and_en_dash_are_signs() -> None:
    facts = _facts(**_swap(26_000, 15_000), delta_cents=-250)
    for sign in ("-", "−", "–"):
        assert validate(f"Protein changes by {sign}11 g.", facts).ok, sign
        assert validate(f"That is {sign}$2.50 less.", facts).ok, sign
        assert not validate(f"Protein changes by {sign}12 g.", facts).ok, sign
    assert not validate("Protein changes by +11 g.", facts).ok
    assert not validate("Protein changes by – 11 g.", facts).ok


def test_ranges_share_the_unit() -> None:
    facts = _facts(a_kcal=474, b_kcal=489)
    assert validate("From 474 to 489 kcal.", facts).ok
    assert not validate("From 474 to 490 kcal.", facts).ok


def test_which_one_is_not_a_number_but_one_serving_is() -> None:
    assert validate("Which one do you mean?", FactSet()).ok
    assert validate("Pick one of them.", FactSet()).ok
    assert validate("Add one serving.", FactSet()).unmatched == ("1",)


def test_one_with_a_unit_is_checked_like_a_digit() -> None:
    cases = {
        "Use one gram of flour.": (_facts(quantity_mg=1_000), "1"),
        "That is a one percent change.": (_facts(scale_factor_percent=1), "1"),
        "Add one kcal.": (_facts(energy_kcal=1), "1"),
        "It costs one dollar.": (_facts(price_cents=100), "$1"),
    }
    for reply, (facts, token) in cases.items():
        assert validate(reply, facts).ok, reply
        empty = validate(reply, FactSet())
        assert empty.reasons == ("unmatched_number",), reply
        assert empty.unmatched == (token,), reply


def test_number_words_before_money_units_are_money() -> None:
    facts = _facts(a_cents=500, b_cents=3, c_cents=1_200)
    for reply in ("five dollars", "three cents", "twelve USD", "twelve dollars"):
        verdict = validate(f"It costs {reply}.", facts)
        assert verdict.ok and verdict.has_money, reply
    for reply in ("six dollars", "four cents", "eleven USD"):
        verdict = validate(f"It costs {reply}.", facts)
        assert verdict.reasons == ("unmatched_number",), reply
        assert verdict.has_money, reply
    assert validate("It costs six dollars.", facts).unmatched == ("$6",)
    assert validate("It costs four cents.", facts).unmatched == ("4",)


def test_usd_without_a_space_is_money() -> None:
    facts = _facts(price_cents=1_200)
    for reply in ("USD12", "12USD", "USD 12", "usd12"):
        verdict = validate(f"It costs {reply}.", facts)
        assert verdict.ok and verdict.has_money, reply
    for reply in ("USD13", "13USD"):
        verdict = validate(f"It costs {reply}.", facts)
        assert verdict.unmatched == ("$13",), reply
        assert verdict.has_money, reply


@pytest.mark.parametrize("fraction", ["½", "¼", "¾", "⅓", "⅞"])
def test_vulgar_fractions_fail_as_number_words(fraction: str) -> None:
    assert validate(f"Add {fraction} cup.", FactSet()).reasons == ("number_word",)
    mixed = validate(f"Add 1{fraction} cups.", _facts(servings=1))
    assert mixed.reasons == ("number_word",)


@pytest.mark.parametrize(
    "word",
    [
        "hundreds",
        "dozens",
        "thousands",
        "halves",
        "millions",
        "tens",
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
        "third",
        "thirds",
        "few",
        "several",
        "fifth",
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


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ("These are safe  for you.", "forbidden_claim"),
        ("These are gluten- free.", "forbidden_claim"),
        ("These are gluten -free.", "forbidden_claim"),
        ("These are gluten-\nfree.", "forbidden_claim"),
        ("It is allergy  free.", "forbidden_claim"),
        ("Gluten-free ingredients, and gluten-free tacos.", "forbidden_claim"),
        ("Kro ger sells it.", "store_price"),
        ("K-r-o-g-e-r sells it.", "store_price"),
    ],
)
def test_claims_match_on_squashed_letters(reply: str, reason: str) -> None:
    assert validate(reply, FactSet()).reasons == (reason,)


@pytest.mark.parametrize(
    "reply",
    [
        "These are gluten-​free.",
        "It is allergen⁠free.",
        "It is celiac­safe.",
        "Kr​oger sells it.",
        "It has 2​6 g of protein.",
        "It is safe‍for you.",
        "​",
    ],
)
def test_format_characters_fail_as_unsupported(reply: str) -> None:
    verdict = validate(reply, _facts(protein_mg=26_000))
    assert verdict.reasons == ("unsupported_character",)
    assert verdict.unmatched == () and not verdict.has_money


def test_too_long_measures_the_raw_reply() -> None:
    padded = "a" * MAX_REPLY_CHARS + "́"
    assert normalize(padded) == "a" * MAX_REPLY_CHARS
    assert validate(padded, FactSet()).reasons == ("too_long",)


def test_cent_symbol_is_money() -> None:
    facts = _facts(price_cents=50)
    for reply in ("It costs 50¢.", "It costs 50 ¢.", "It costs 50￠."):
        verdict = validate(reply, facts)
        assert verdict.ok and verdict.has_money, reply
    verdict = validate("It costs 60¢.", facts)
    assert verdict.unmatched == ("60",) and verdict.has_money


def test_server_safety_note_passes_but_the_ingredient_phrase_does_not() -> None:
    facts = facts_from_payloads([(TOOL_NAME, {})])
    assert validate(catalog_tool._SAFETY, facts).ok
    for sentence in re.split(r"(?<=\.) ", catalog_tool._SAFETY):
        assert validate(sentence, facts).ok, sentence
    for reply in (
        "These are made with gluten-free ingredients.",
        "Made with gluten free ingredients.",
    ):
        assert validate(reply, FactSet()).reasons == ("forbidden_claim",), reply


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


@pytest.mark.parametrize(
    "reply",
    [
        "These tacos are gluten-free. Ingredients: corn.",
        "This meal is gluten free (ingredients vary).",
        "These tacos are gluten-free; ingredients: corn.",
        "Chicken tacos are gluten-free\nIngredients: chicken, corn.",
        "Chicken tacos are gluten-free\n\nIngredients: chicken, corn.",
        "made with gluten-free ingredients",
    ],
)
def test_no_phrase_near_gluten_free_is_exempt(reply: str) -> None:
    assert validate(reply, FactSet()).reasons == ("forbidden_claim",)


def test_accents_are_folded_before_claims() -> None:
    for reply in ("These are gluten-frée.", "It is sàfe for you.", "Kröger sells it"):
        assert not validate(reply, FactSet()).ok, reply
    assert validate("Kröger sells it", FactSet()).reasons == ("store_price",)
    assert validate("Add jalapeño slices.", FactSet()).ok


@pytest.mark.parametrize(
    "reply",
    [
        "Add smørrebrød.",
        "These are ɡluten free.",
        "Celiıac safe.",
        "Krøger sells it.",
        "Kʀoger sells it.",
        "ᴋʀᴏɢᴇʀ sells it.",
        "These are glutеn-free.",
        "Это просто текст.",
        "Tasty \U0001f32e tacos.",
        "Tasty ❤️ tacos.",
        "Use a ٣ g portion.",
        "Use x = 3.",
    ],
)
def test_characters_outside_the_allowed_set_fail(reply: str) -> None:
    assert validate(reply, FactSet()).reasons == ("unsupported_character",)


def test_accented_latin_folds_to_ascii_and_passes() -> None:
    assert validate("Add jalapeño slices and crème.", FactSet()).ok
    assert validate("Add jalapeño slices.", FactSet()).ok
    assert normalize("jalapeño") == "jalapeno"
    assert normalize("a b c‑d−e\n") == "a b c-d-e\n"


def test_every_bmp_letter_that_does_not_fold_to_ascii_fails() -> None:
    def folded(char: str) -> str:
        parts = unicodedata.normalize("NFKD", "x" + char)
        return "".join(c for c in parts if unicodedata.category(c) != "Mn")

    checked = 0
    for code in range(0x10000):
        char = chr(code)
        if not unicodedata.category(char).startswith("L"):
            continue
        residue = "".join(folded(char).split())
        if residue and re.search(r"[^A-Za-z]", residue):
            checked += 1
            assert not validate("x" + char, FactSet()).ok, f"U+{code:04X}"
    assert checked > 10_000


@pytest.mark.parametrize(
    "word",
    [
        "fourth",
        "fourths",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
        "pair",
        "couple",
    ],
)
def test_ordinal_and_group_words_fail(word: str) -> None:
    assert validate(f"Use a {word} of it.", FactSet()).reasons == ("number_word",)


def test_dollar_words_and_spaced_dollar_sign_are_money() -> None:
    verdict = validate("It costs a dollar.", FactSet())
    assert verdict.reasons == ("number_word",) and verdict.has_money
    bucks = validate("It costs 5 bucks.", _facts(price_cents=500))
    assert bucks.ok and bucks.has_money
    wrong = validate("It costs 6 bucks.", _facts(price_cents=500))
    assert wrong.unmatched == ("$6",) and wrong.has_money
    assert validate("It costs bucks.", FactSet()).has_money
    for reply in ("It costs $   12.", "It costs $ 12."):
        verdict = validate(reply, _facts(price_cents=1_200))
        assert verdict.ok and verdict.has_money, reply
        assert validate(reply, FactSet()).unmatched == ("$12",), reply


def test_usd_with_a_sign_is_a_signed_money_token() -> None:
    facts = _facts(price_cents=1_200)
    verdict = validate("The change is USD -12.", facts)
    assert verdict.unmatched == ("-$12",) and verdict.has_money
    delta = {"delta": {"total": {"price_cents": -1_200}}}
    assert validate("The change is USD -12.", facts_from_payloads([("t", delta)])).ok


def test_one_with_a_hyphenated_unit_is_checked_like_a_digit() -> None:
    reply = "Buy a one-pound package."
    assert validate(reply, FactSet()).unmatched == ("1",)
    assert validate(reply, _facts(servings=1)).ok
    assert validate("Buy a one pound package.", FactSet()).unmatched == ("1",)
    assert validate("Which one do you want?", FactSet()).ok


def test_dot_amounts_and_trailing_dollar_sign_are_money() -> None:
    facts = _facts(price_cents=50, other_cents=1_200)
    for reply in ("It costs $.50.", "It costs $ .50.", "It costs 12 $.", "It is 12 $"):
        verdict = validate(reply, facts)
        assert verdict.ok and verdict.has_money, reply
    wrong = validate("It costs $.51.", facts)
    assert wrong.unmatched == ("$.51",) and wrong.has_money
    wrong = validate("It costs 13 $.", facts)
    assert wrong.unmatched == ("$13",) and wrong.has_money
    # "12 $5" is a count then an amount, not "12 $" followed by 5.
    assert validate("It costs 12 $5.", facts).unmatched == ("12", "$5")


def test_dollar_sign_before_a_number_word_is_money_and_a_number_word() -> None:
    for reply in ("It costs $ twelve.", "It costs $twelve.", "It costs $ twenty."):
        verdict = validate(reply, _facts(price_cents=1_200, servings=12))
        assert verdict.reasons == ("number_word",), reply
        assert verdict.has_money, reply


def test_one_before_a_noun_after_a_determiner_is_checked_like_a_digit() -> None:
    for reply in ("Use the one onion.", "Add a one egg omelet.", "Add the one egg."):
        assert validate(reply, FactSet()).unmatched == ("1",), reply
        assert validate(reply, _facts(servings=1)).ok, reply
    for reply in (
        "Which one do you mean?",
        "Which one should I plan?",
        "This one works.",
        "Is it the one?",
        "That one, please.",
        "Pick one of them.",
        "The one that fits.",
    ):
        assert validate(reply, FactSet()).ok, reply


def test_leading_dot_numbers_are_numbers_everywhere() -> None:
    wrong = validate("It has .5 g protein.", _facts(protein_mg=5_000))
    assert wrong.unmatched == (".5",)
    assert validate("It has .5 g protein.", _facts(protein_mg=500)).ok
    assert validate("Add .5 servings.", FactSet()).unmatched == (".5",)
    usd = validate("It costs USD .50.", _facts(price_cents=50))
    assert usd.ok and usd.has_money
    assert validate("It costs USD .50.", FactSet()).unmatched == ("$.50",)
    assert _facts(note="about .5 g").generic == {Decimal("0.5")}


def test_every_number_in_a_money_range_is_money() -> None:
    facts = _facts(a_cents=1_000, b_cents=1_200)
    ranges = ("$10-12", "$10 to 12", "$10-$12", "10-12 dollars", "USD 10-12")
    for reply in (*ranges, "10 to 12 USD"):
        verdict = validate(f"It costs {reply}.", facts)
        assert verdict.ok and verdict.has_money, reply
    wrong = validate("It costs $10-13.", facts)
    assert wrong.unmatched == ("$13",) and wrong.has_money
    only_first = validate("It costs $10 to 12.", _facts(a_cents=1_000))
    assert only_first.unmatched == ("$12",)
    cents = validate("It costs 50-60 cents.", _facts(a_cents=50, b_cents=60))
    assert cents.ok and cents.has_money
    partial = validate("It costs 50-61 cents.", _facts(a_cents=50))
    assert partial.unmatched == ("61",)


@pytest.mark.parametrize(
    "reply",
    [
        "It costs an extra dollar.",
        "It costs a single dollar.",
        "Just a cent more.",
        "A few bucks more.",
        "The price is shown in USD.",
        "It costs two more cents.",
    ],
)
def test_money_units_without_a_number_fail_as_number_words(reply: str) -> None:
    verdict = validate(reply, FactSet())
    assert "number_word" in verdict.reasons
    assert verdict.has_money


@pytest.mark.parametrize("space", [" ", " ", "\u0085", "\x1c", "\x0b", "\x0c", "\r"])
def test_line_separators_and_controls_fail_as_unsupported(space: str) -> None:
    verdict = validate(f"Gluten{space}free tacos.", FactSet())
    assert verdict.reasons == ("unsupported_character",)


def test_only_space_newline_and_tab_are_allowed_whitespace() -> None:
    assert validate("Tacos\tand\nrice  here.", FactSet()).ok
    assert validate("Tacos and rice.", FactSet()).ok


def test_curly_quotes_fold_to_ascii_but_degree_sign_is_rejected() -> None:
    assert normalize("It’s “fine” and ‘ok’") == "It's \"fine\" and 'ok'"
    assert validate("It’s “fine”.", FactSet()).ok
    assert validate("It’s gluten‑free.", FactSet()).reasons == ("forbidden_claim",)
    degrees = validate("Bake at 5° heat.", FactSet())
    assert degrees.reasons == ("unsupported_character",)


def _assert_template_grounded(text: str, payload: dict[str, object]) -> None:
    verdict = validate(text, facts_from_payloads([("tool", payload)]))
    assert verdict.ok, (text, verdict)


def test_chat_answer_error_templates_are_grounded() -> None:
    checked = 0
    for recipe_id, recipe in RECIPES.items():
        for item_id, _quantity in recipe.ingredients:
            error: dict[str, object] = {
                "error_code": "exclusion_reject",
                "recipe_id": recipe_id,
                "ingredient_id": item_id,
            }
            answer = chat_answer._exclusion_answer(error)
            assert answer is not None
            _assert_template_grounded(answer, error)
            ingredient = INGREDIENTS[item_id]
            for diet in ("vegetarian", "vegan"):
                conflict = {**error, "error_code": "diet_conflict", "diet": diet}
                reply = chat_answer._diet_conflict_answer(conflict)
                if getattr(ingredient, diet):
                    assert reply is None
                    continue
                assert reply is not None
                _assert_template_grounded(reply, conflict)
                checked += 1
    assert checked > 0
    unsupported: dict[str, object] = {"error_code": "unsupported_recipe"}
    answer = chat_answer._unsupported_answer(unsupported)
    assert answer is not None
    _assert_template_grounded(answer, unsupported)


def test_chat_answer_static_templates_are_grounded() -> None:
    for text in (chat_answer._DIET, chat_answer._UNKNOWN_RESTRICTION):
        _assert_template_grounded(text, {})
    for code, field in (
        ("unsupported_diet", "diet"),
        ("unsupported_ingredient", "pantry_ingredients"),
        ("unsupported_ingredient", "ingredient_exclusions"),
    ):
        error: dict[str, object] = {"error_code": code, "field": field}
        answer = render_public_answer(None, error)
        assert answer != CLARIFICATION
        _assert_template_grounded(answer, error)


def test_catalog_static_templates_are_grounded() -> None:
    for text in (
        catalog_tool.DISCOVERY_ERROR,
        catalog_tool._NO_MATCH,
        catalog_tool._UNKNOWN_EXCLUSION,
    ):
        _assert_template_grounded(text, {})
    payload = execute_catalog_search({"query": "gluten free"})
    facts = facts_from_payloads([(TOOL_NAME, payload)])
    verdict = validate(catalog_answer(payload), facts)
    assert verdict.ok, verdict


def test_number_glued_to_other_letters_fails() -> None:
    facts = _facts(price_cents=1_200, energy_kcal=2, servings=2, a=3, b=1)
    for reply in (
        "$12k",
        "Your groceries cost $12k.",
        "2k kcal",
        "2x the protein",
        "3K",
        "1M",
        "It is 2nd.",
    ):
        verdict = validate(reply, facts)
        assert verdict.reasons == ("unmatched_number",), reply
        assert verdict.unmatched and all(t.isdigit() for t in verdict.unmatched)
    assert validate("Your groceries cost $12k.", facts).unmatched == ("12",)
    assert validate("Your groceries cost $12k.", facts).has_money


def test_number_followed_by_a_recognized_unit_or_punctuation_passes() -> None:
    facts = _facts(
        flour_mg=26_000, price_cents=1_200, energy_kcal=474, servings=2, p_percent=50
    )
    for reply in (
        "26g",
        "26G.",
        "474kcal",
        "50%",
        "50percent",
        "12USD",
        "12dollars",
        "2servings",
        "Ends with 2.",
        "(2), [2]; 2: 2!",
    ):
        assert validate(reply, facts).ok, reply


def test_server_sentences_are_exempt_only_at_a_sentence_start() -> None:
    note = "Gluten-free ingredients describes the ingredients only."
    inline = validate(f"These tacos are {note}", FactSet())
    assert inline.reasons == ("forbidden_claim",)
    assert validate(f"Tacos are here. {note}", FactSet()).ok
    assert validate(f"Which one? {note}", FactSet()).ok
    no_gap = validate(f"Tacos are here.{note}", FactSet())
    assert no_gap.reasons == ("forbidden_claim",)
    claim = "I cannot claim gluten-free, celiac, allergy, or cross-contact safety."
    assert validate(f"Hello, {claim}", FactSet()).reasons == ("forbidden_claim",)
    assert validate(f"Tacos! {claim}", FactSet()).ok


def test_mg_must_match_a_milligram_fact_and_kg_is_grams_times_1000() -> None:
    protein = _facts(protein_mg=2_300)
    assert ("protein", "milli", False, Decimal(2_300)) in protein.nutrition
    assert validate("It has 2300 mg protein.", protein).ok
    assert validate("It has 2300mg protein.", protein).ok
    assert validate("It has 2.3 g protein.", protein).ok
    wrong = validate("It has 2 mg protein.", protein)
    assert wrong.reasons == ("unmatched_number",) and wrong.unmatched == ("2",)
    # A gram fact with one decimal is not a milligram fact.
    assert not validate("It has 2 mg protein.", _facts(protein_mg=2_000)).ok
    assert not validate("It has 2000 mg protein.", _facts(protein_mg=2_001)).ok
    assert validate("It has 2 mg of flour.", _facts(flour_mg=2)).ok
    flour = _facts(flour_mg=1_500_000)
    assert validate("Buy 1.5 kg of flour.", flour).ok
    assert validate("Buy 1500 g of flour.", flour).ok
    assert validate("Buy 2 kg of flour.", flour).unmatched == ("2",)
    assert not validate("Buy 1.5 kg of flour.", _facts(flour_mg=1_500)).ok


def test_signed_milligram_change_must_match_a_real_delta() -> None:
    facts = _facts(
        before={"protein_mg": 2_000},
        after={"protein_mg": 1_500},
    )
    assert validate("Protein changes by -500 mg.", facts).ok
    assert not validate("Protein changes by +500 mg.", facts).ok


def test_substitute_missing_choice_and_unknown_food_are_grounded() -> None:
    names = [{"name": "ground beef"}, {"name": "beef chuck"}, {"name": "beef steak"}]
    for status in ("needs_food_choice", "unknown_food"):
        payload: dict[str, object] = {"status": status, "candidates": names}
        answer, _ = _grounded(SUBSTITUTE_TOOL, payload)
        assert answer.startswith("Which one" if "choice" in status else "I cannot")
    empty: dict[str, object] = {"status": "unknown_food", "candidates": []}
    _grounded(SUBSTITUTE_TOOL, empty)
    ingredient: dict[str, object] = {
        "status": "needs_ingredient_choice",
        "recipe_id": "chicken_tacos",
        "candidates": names,
    }
    answer, _ = _grounded(SUBSTITUTE_TOOL, ingredient)
    assert answer.startswith("Which ingredient in")


def test_substitute_incomplete_sample_price_is_grounded() -> None:
    real = execute_substitute(_REAL_SWAP, _BUDGET)
    payload = {**real, "price": {"before": {}, "after": {}, "delta_cents": None}}
    answer, verdict = _grounded(SUBSTITUTE_TOOL, payload)
    assert answer.endswith("The sample price is incomplete.")
    assert not verdict.has_money


def test_get_meal_with_several_meals_is_grounded() -> None:
    results: list[tuple[str, dict[str, object]]] = [
        (GET_MEAL_TOOL, execute_get_meal({"recipe_id": recipe_id}))
        for recipe_id in ("chicken_tacos", "bean_tacos")
    ]
    answer = read_tool_answer(results)
    assert answer is not None and answer.count("per serving") == 2
    verdict = validate(answer, facts_from_payloads(results))
    assert verdict.ok, (answer, verdict)


@pytest.mark.parametrize(
    "reply",
    [
        "I placed your order.",
        "I placed an order for you.",
        "I've placed the order for you.",
        "Your order has been placed.",
        "Your order was placed.",
        "I checked out for you.",
        "I purchased the chicken.",
        "I bought it for you.",
        "I bought the chicken.",
        "I added to your cart the rice.",
        "I added it to your cart.",
        "I added the rice to your cart.",
        "I P.l.a.c.e.d your order.",
    ],
)
def test_purchase_claims_are_forbidden(reply: str) -> None:
    assert validate(reply, FactSet()).reasons == ("forbidden_claim",)


@pytest.mark.parametrize(
    "reply", ["Check out the bean tacos.", "Order the beans first.", "Go to checkout."]
)
def test_harmless_order_and_check_out_text_passes(reply: str) -> None:
    assert validate(reply, FactSet()).ok


@pytest.mark.parametrize(
    "reply",
    [
        "The total is $12 K.",
        "The total is $12 k.",
        "The total is $12 M.",
        "The total is $12 B.",
        "The total is $12 mil.",
        "The total is $12 bn.",
        "The total is $12 grand.",
        "The total is $12 thousand.",
        "The total is $12 million.",
        "The total is $12 billion.",
        "The total is $12 trillion.",
        "The total is $12 MM.",
        "The total is $12 mn.",
        "The total is $12 bln.",
        "The total is $12 tn.",
        "It has 2 x the protein.",
        "It has 2\tx the protein.",
    ],
)
def test_number_then_scale_word_is_unmatched(reply: str) -> None:
    facts = _facts(total_cents=1_200, servings=2)
    verdict = validate(reply, facts)
    assert "unmatched_number" in verdict.reasons
    assert not verdict.ok


def test_scale_check_leaves_units_and_plain_words_alone() -> None:
    facts = _facts(total_cents=1_200, servings=2, kcal=300)
    assert validate("The total is $12 for 2 meals.", facts).ok
    assert validate("It has 300 kcal and 2 servings.", facts).ok
    assert validate("It has 2 xylitol packets.", facts).unmatched == ()


@pytest.mark.parametrize(
    "reply",
    [
        "These tacos are... Gluten-free ingredients describes the ingredients only.",
        "These tacos are… Gluten-free ingredients describes the ingredients only.",
        "See e.g. Gluten-free ingredients describes the ingredients only.",
        "That is, i.e. Gluten-free ingredients describes the ingredients only.",
        "Tacos . . . Gluten-free ingredients describes the ingredients only.",
        "Ask Dr. Gluten-free ingredients describes the ingredients only.",
        "See No. Gluten-free ingredients describes the ingredients only.",
        "In the U.S. Gluten-free ingredients describes the ingredients only.",
        "At 5 a.m. Gluten-free ingredients describes the ingredients only.",
        "Tacos.. Gluten-free ingredients describes the ingredients only.",
    ],
)
def test_ellipsis_and_abbreviations_are_not_sentence_ends(reply: str) -> None:
    assert "forbidden_claim" in validate(reply, FactSet()).reasons


@pytest.mark.parametrize(
    "reply",
    [
        "Your order is placed.",
        "Your order got placed.",
        "Your order is now placed.",
        "O.r.d.e.r is p.l.a.c.e.d.",
        "I paid for it.",
        "It is paid.",
        "P a i d in full.",
    ],
)
def test_more_purchase_claims_are_forbidden(reply: str) -> None:
    assert validate(reply, FactSet()).reasons == ("forbidden_claim",)


@pytest.mark.parametrize(
    "reply",
    [
        "It has 3 times the protein.",
        "It has 3 Times the protein.",
        "It has 3-fold the protein.",
        "It has 3 - fold the protein.",
        "It has two x the protein.",
        "It has two times the protein.",
        "It has two-fold the protein.",
    ],
)
def test_more_multipliers_are_unmatched(reply: str) -> None:
    verdict = validate(reply, _facts(servings=2, portions=3))
    assert "unmatched_number" in verdict.reasons
    assert not verdict.ok


@pytest.mark.parametrize(
    "reply",
    [
        "I added Vegetable pasta to your plan.",
        "I removed Bean tacos from your plan.",
        "I updated your plan.",
        "I changed your plan.",
        "Your plan now has Vegetable pasta.",
        "Your plan is now updated.",
        "I added it.",
        "I removed it.",
        "Y.o.u.r p.l.a.n i.s n.o.w done.",
        "I A.D.D.E.D i.t for you.",
    ],
)
def test_claims_that_the_plan_already_changed_are_forbidden(reply: str) -> None:
    verdict = validate(reply, FactSet())
    assert "forbidden_claim" in verdict.reasons
    assert not verdict.ok


@pytest.mark.parametrize(
    "reply",
    [
        "Apply it in the plan panel.",
        "Proposed: add Vegetable pasta. Apply it in the plan panel.",
    ],
)
def test_the_apply_it_prompt_is_not_a_changed_claim(reply: str) -> None:
    assert validate(reply, FactSet()).ok


def test_servings_from_your_plan_is_not_a_changed_claim() -> None:
    verdict = validate("Servings from your plan: 2.", _facts(servings=2))
    assert verdict.ok, verdict


@pytest.mark.parametrize(
    "reply",
    [
        "The tofu version also becomes vegan-friendly, while the original bean "
        "version is vegetarian.",
        "These are vegan.",
        "It is Plant-Based.",
        "It is dairy free and nut-free.",
        "It is lactose free, egg free, and soy free.",
        "A keto or paleo meal.",
        "It is halal and kosher.",
        "It is low sodium, sugar free, low fat, and high fiber.",
        "These are vegetar-\nian.",
        "Bean tacos are not vegan.",
    ],
)
def test_diet_claims_in_model_prose_fail(reply: str) -> None:
    verdict = validate(reply, FactSet())
    assert verdict.reasons == ("forbidden_claim",), reply


def test_the_server_diet_sentences_still_pass() -> None:
    conflict = "Chicken tacos are not vegan. Change the recipe or the restriction."
    assert (
        chat_answer._diet_conflict_answer(
            {
                "error_code": "diet_conflict",
                "recipe_id": "chicken_tacos",
                "ingredient_id": "chicken_breast",
                "diet": "vegan",
            }
        )
        == conflict
    )
    for reply in (conflict, chat_answer._DIET, KETO_NOTE):
        verdict = validate(reply, facts_from_payloads([(TOOL_NAME, {})]))
        assert verdict.ok, (reply, verdict)
    # The exemption is the whole sentence at a sentence start, nothing near it.
    assert not validate(
        "These are keto. No meal in this catalog is keto.", FactSet()
    ).ok
    assert not validate(
        "Choose no preference, vegetarian, or vegan food.", FactSet()
    ).ok


def test_the_exact_keto_policy_does_not_ground_other_nutrient_claims() -> None:
    facts = facts_from_payloads([(TOOL_NAME, {})])
    assert validate(KETO_NOTE, facts).ok
    assert not validate(KETO_NOTE, FactSet()).ok
    altered = KETO_NOTE.replace("30 g", "31 g")
    assert altered != KETO_NOTE
    assert not validate(altered, facts).ok
    for reply in ("Protein: 30 g", "Carbohydrate: 30 g", "Fat: 30 g"):
        verdict = validate(reply, facts)
        assert verdict.reasons == ("unmatched_number",), (reply, verdict)


def test_whole_grams_match_a_milligram_fact() -> None:
    facts = _facts(protein_mg=14_484)
    assert validate("Protein is 14 g.", facts).ok
    assert not validate("Protein is 15 g.", facts).ok


def test_list_lines_pass_and_a_claim_split_across_lines_still_fails() -> None:
    facts = _facts(protein_mg=14_484)
    listed = "Protein:\n- 14 g\n- Easy swap."
    assert validate(listed, facts).ok
    assert validate("These are gluten-\nfree.", facts).reasons == ("forbidden_claim",)
    assert validate("These are gluten\n-\nfree.", facts).reasons == ("forbidden_claim",)


def test_a_model_copy_of_the_stale_warning_is_a_forbidden_claim() -> None:
    facts = _facts(total_cents=1_200)
    plain = validate("The sample total is $12.00.", facts)
    assert plain.ok
    for copy in (
        STALE_SPENDING_WARNING,
        STALE_SPENDING_WARNING.upper(),
        STALE_SPENDING_WARNING.replace(" ", "  "),
    ):
        verdict = validate(f"The sample total is $12.00. {copy}", facts)
        assert verdict.reasons == ("forbidden_claim",)


def _propose(*ops: dict[str, object]) -> dict[str, object]:
    plan = _revision(
        [
            {"recipe_id": "chicken_tacos", "servings": 2},
            {"recipe_id": "bean_tacos", "servings": 2},
        ]
    )
    return execute_propose({"operations": list(ops)}, _BUDGET, plan, lambda _: "p-1")


_PROPOSAL_OPS: list[dict[str, object]] = [
    {"op": "add", "recipe_id": "vegetable_pasta", "servings": 3},
    {"op": "remove", "recipe_id": "bean_tacos"},
    {"op": "set_servings", "recipe_id": "chicken_tacos", "servings": 4},
    {"op": "set_pantry", "ingredient_id": next(iter(INGREDIENTS)), "owned": True},
]


def test_proposal_template_is_grounded() -> None:
    answer, verdict = _grounded(PROPOSAL_TOOL, _propose(*_PROPOSAL_OPS))
    assert answer.startswith(
        "Proposed: add Vegetable pasta (3 servings), remove Bean tacos, "
        "set Chicken tacos to 4 servings, mark "
    )
    assert " as owned. Sample meal price: " in answer
    assert answer.endswith(f"Apply it in the plan panel. {SAMPLE_ESTIMATE_NOTICE}")
    assert verdict.has_money


def test_proposal_template_with_a_not_owned_pantry_item_and_a_price_drop() -> None:
    ingredient = next(iter(INGREDIENTS))
    payload = _propose(
        {"op": "remove", "recipe_id": "bean_tacos"},
        {"op": "set_pantry", "ingredient_id": ingredient, "owned": False},
    )
    answer, _ = _grounded(PROPOSAL_TOOL, payload)
    assert "Proposed: remove Bean tacos, mark " in answer
    assert " as not owned. " in answer
    assert "(-USD $" in answer


def test_proposal_template_with_an_incomplete_price_has_no_money() -> None:
    payload = _propose(*_PROPOSAL_OPS)
    after = payload["after"]
    assert isinstance(after, dict)
    after["estimate"] = {**after["estimate"], "total_cents": None}
    answer, verdict = _grounded(PROPOSAL_TOOL, payload)
    assert answer.endswith(
        "The sample price is incomplete. Apply it in the plan panel."
    )
    assert SAMPLE_ESTIMATE_NOTICE not in answer
    assert not verdict.has_money


def test_server_sentence_exempt_at_the_start_or_after_a_word_sentence_end() -> None:
    note = "Gluten-free ingredients describes the ingredients only."
    assert validate(note, FactSet()).ok
    assert validate(f"Tacos are here. {note}", FactSet()).ok
    assert validate(f"Tacos are here!\n{note}", FactSet()).ok
    assert validate(f"Which one? {note}", FactSet()).ok
    assert validate(f"Pick 3 meals. {note}", _facts(servings=3)).ok


@pytest.mark.parametrize(
    "reply",
    ["10³ kcal", "①", "H₂O", "１２ g", "Use ٣ g", "Add ⑫ eggs", "Add ❶ egg"],
)
def test_non_ascii_digits_fail_before_folding(reply: str) -> None:
    verdict = validate(reply, _facts(kcal=10, servings=1, count=12))
    assert verdict.reasons == ("unsupported_character",)
    assert verdict.unmatched == ()


@pytest.mark.parametrize("reply", ["Add Ⅻ eggs.", "Ⅲ servings", "Use ⅷ eggs."])
def test_letter_number_characters_fail(reply: str) -> None:
    assert validate(reply, FactSet()).reasons == ("unsupported_character",)


def test_with_notice_appends_once() -> None:
    once = with_notice("The total is $5.")
    assert once == f"The total is $5. {SAMPLE_ESTIMATE_NOTICE}"
    assert with_notice(once) == once
