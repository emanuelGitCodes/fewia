from dataclasses import replace
from typing import cast

import pytest

from app.agent.chat_answer import _usd
from app.agent.plan_tools import (
    GET_MEAL_TOOL,
    GET_PLAN_TOOL,
    execute_get_meal,
    execute_get_plan,
)
from app.agent.price_tool import PRICE_TOOL, execute_price_lines
from app.agent.read_answers import read_tool_answer
from app.agent.substitute_tool import SUBSTITUTE_TOOL, execute_substitute
from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, GroceryRequest
from app.domain.plan_revision import PlanRevisionInput
from app.services.meal_nutrition import meal_nutrition

_NOTICE = SAMPLE_ESTIMATE_NOTICE
_INCOMPLETE = "The sample total is incomplete because a price is missing."


def _macros(kcal: int, protein: int, carbs: int, fat: int) -> dict[str, object]:
    return {
        "energy_kcal": kcal,
        "protein_mg": protein,
        "carbohydrate_mg": carbs,
        "fat_mg": fat,
    }


def _estimate(total: int | None, available: int, accepted: bool) -> dict[str, object]:
    return {
        "total_cents": total,
        "price_complete": total is not None,
        "available_cents": available,
        "accepted": accepted,
    }


def _line(ingredient_id: str, name: str) -> dict[str, object]:
    return {"ingredient_id": ingredient_id, "name": name, "quantity": 1, "unit": "g"}


def _side(
    per_serving: dict[str, object], names: list[tuple[str, str]]
) -> dict[str, object]:
    return {
        "ingredients": [_line(i, n) for i, n in names],
        "per_serving": per_serving,
    }


def _substitute(
    change: dict[str, object],
    price: dict[str, object],
    assumptions: list[str],
) -> dict[str, object]:
    before = _macros(500, 40_500, 30_499, 10_000)
    after = _macros(460, 28_500, 35_000, 9_400)
    return {
        "recipe_id": "chicken_tacos",
        "servings": 2,
        "change": change,
        "before": _side(before, [("chicken_breast", "chicken breast")]),
        "after": _side(after, [("chickpeas", "chickpeas")]),
        "delta": {"per_serving": _macros(-40, -12_000, 4_501, -600)},
        "assumptions": assumptions,
        "price": price,
    }


_SWAP = {"replace_ingredient_id": "chicken_breast", "with_ingredient_id": "chickpeas"}
_MACRO_CLAUSE = (
    "per serving 500 to 460 kcal (-40 kcal), protein 41 to 29 g (-12 g), "
    "carbs 30 to 35 g (+5 g), fat 10 to 9 g (-1 g)."
)


def test_empty_results_return_none() -> None:
    assert read_tool_answer([]) is None


def test_substitute_swap_with_prices() -> None:
    price = {
        "before": _estimate(806, 10_000, True),
        "after": _estimate(686, 10_000, True),
        "delta_cents": -120,
    }
    payload = _substitute(_SWAP, price, ["Same weight per serving: 150 g."])
    assert read_tool_answer([(SUBSTITUTE_TOOL, payload)]) == (
        "Chicken tacos for 2 servings with chickpeas instead of chicken breast: "
        f"{_MACRO_CLAUSE} Same weight per serving: 150 g. "
        f"Sample meal price: {_usd(806)} to {_usd(686)} (-USD $1.20). {_NOTICE}"
    )


def test_substitute_positive_delta_has_plus_sign() -> None:
    price = {
        "before": _estimate(686, 10_000, True),
        "after": _estimate(806, 10_000, True),
        "delta_cents": 120,
    }
    answer = read_tool_answer([(SUBSTITUTE_TOOL, _substitute(_SWAP, price, []))])
    assert answer is not None
    assert f"(+{_usd(120)})." in answer


def test_substitute_gram_delta_is_difference_of_shown_values() -> None:
    price = {
        "before": _estimate(806, 10_000, True),
        "after": _estimate(686, 10_000, True),
        "delta_cents": -120,
    }
    payload = _substitute(_SWAP, price, [])
    before = _macros(500, 25_600, 30_000, 10_000)
    after = _macros(460, 15_400, 30_000, 10_000)
    payload["before"] = _side(before, [("chicken_breast", "chicken breast")])
    payload["after"] = _side(after, [("chickpeas", "chickpeas")])
    answer = read_tool_answer([(SUBSTITUTE_TOOL, payload)])
    assert answer is not None
    assert "protein 26 to 15 g (-11 g)" in answer


def test_substitute_one_serving_is_singular() -> None:
    price = {
        "before": _estimate(None, 1, False),
        "after": _estimate(None, 1, False),
    }
    payload = _substitute(_SWAP, price, [])
    payload["servings"] = 1
    answer = read_tool_answer([(SUBSTITUTE_TOOL, payload)])
    assert answer is not None
    assert answer.startswith("Chicken tacos for 1 serving with chickpeas")


def test_substitute_money_delta_signs() -> None:
    def answer_for(delta: int) -> str:
        price = {
            "before": _estimate(806, 10_000, True),
            "after": _estimate(806 + delta, 10_000, True),
            "delta_cents": delta,
        }
        answer = read_tool_answer([(SUBSTITUTE_TOOL, _substitute(_SWAP, price, []))])
        assert answer is not None
        return answer

    assert "(+USD $1.20)." in answer_for(120)
    assert "(-USD $1.20)." in answer_for(-120)
    assert "(+USD $0.00)." in answer_for(0)


def test_get_plan_singular_serving() -> None:
    payload: dict[str, object] = {
        "meals": [{"recipe_id": "bean_tacos", "servings": 1}],
        "total": _macros(1, 0, 0, 0),
    }
    answer = read_tool_answer([(GET_PLAN_TOOL, payload)])
    assert answer is not None
    assert answer.startswith("Your plan: Bean tacos (1 serving).")


def test_substitute_scale_change() -> None:
    price = {
        "before": _estimate(806, 10_000, True),
        "after": _estimate(806, 10_000, True),
        "delta_cents": 0,
    }
    change = {"scale_ingredient_id": "chickpeas", "scale_factor_percent": 50}
    payload = _substitute(change, price, ["Scaled to 50 percent."])
    assert read_tool_answer([(SUBSTITUTE_TOOL, payload)]) == (
        "Chicken tacos for 2 servings with chickpeas changed: "
        f"{_MACRO_CLAUSE} Scaled to 50 percent. "
        f"Sample meal price: {_usd(806)} to {_usd(806)} (+{_usd(0)}). {_NOTICE}"
    )


def test_substitute_incomplete_price_has_no_notice() -> None:
    price = {
        "before": _estimate(None, 10_000, False),
        "after": _estimate(686, 10_000, True),
        "delta_cents": None,
    }
    payload = _substitute(_SWAP, price, ["Same weight per serving: 150 g."])
    assert read_tool_answer([(SUBSTITUTE_TOOL, payload)]) == (
        "Chicken tacos for 2 servings with chickpeas instead of chicken breast: "
        f"{_MACRO_CLAUSE} Same weight per serving: 150 g. "
        "The sample price is incomplete."
    )


def _lines_payload(estimate: dict[str, object]) -> dict[str, object]:
    return {
        "meals": [
            {"recipe_id": "chicken_tacos", "servings": 2},
            {"recipe_id": "bean_tacos", "servings": 1},
        ],
        "estimate": estimate,
    }


_PRICED = "Chicken tacos (2 servings), Bean tacos (1 serving)"


def test_price_lines_fits() -> None:
    payload = _lines_payload(_estimate(1_250, 10_000, True))
    assert read_tool_answer([(PRICE_TOOL, payload)]) == (
        f"Sample total for {_PRICED}: {_usd(1_250)}. "
        f"It fits the available {_usd(10_000)}. {_NOTICE}"
    )


def test_price_lines_exceeds() -> None:
    payload = _lines_payload(_estimate(1_250, 1_000, False))
    assert read_tool_answer([(PRICE_TOOL, payload)]) == (
        f"Sample total for {_PRICED}: {_usd(1_250)}. "
        f"It exceeds the available {_usd(1_000)}. {_NOTICE}"
    )


def test_price_lines_incomplete() -> None:
    payload = _lines_payload(_estimate(None, 10_000, False))
    assert read_tool_answer([(PRICE_TOOL, payload)]) == _INCOMPLETE


def test_get_meal() -> None:
    payload = {
        "recipe_id": "chicken_tacos",
        "ingredients": [_line("a", "chicken breast"), _line("b", "tortillas")],
        "per_serving": _macros(500, 40_500, 30_499, 10_000),
    }
    assert read_tool_answer([(GET_MEAL_TOOL, payload)]) == (
        "Chicken tacos per serving: 500 kcal, 41 g protein, 30 g carbs, "
        "10 g fat. Ingredients: chicken breast, tortillas."
    )


def test_get_plan_with_meals() -> None:
    payload = {
        "meals": [
            {"recipe_id": "chicken_tacos", "servings": 2},
            {"recipe_id": "bean_tacos", "servings": 3},
        ],
        "total": _macros(2_500, 100_000, 200_500, 50_000),
        "estimate": _estimate(1_250, 10_000, True),
    }
    assert read_tool_answer([(GET_PLAN_TOOL, payload)]) == (
        "Your plan: Chicken tacos (2 servings), Bean tacos (3 servings). "
        "Total: 2500 kcal, 100 g protein, 201 g carbs, 50 g fat. "
        f"Sample total for Chicken tacos, Bean tacos: {_usd(1_250)}. "
        f"It fits the available {_usd(10_000)}. {_NOTICE}"
    )


def test_get_plan_without_meals() -> None:
    payload: dict[str, object] = {"meals": [], "plan_revision_id": None}
    assert read_tool_answer([(GET_PLAN_TOOL, payload)]) == (
        "Your plan has no meals yet."
    )


def test_priority_prefers_substitute_then_price_then_meal_then_plan() -> None:
    plan: dict[str, object] = {"meals": []}
    lines = _lines_payload(_estimate(None, 10_000, False))
    meal = {
        "recipe_id": "bean_tacos",
        "ingredients": [_line("b", "beans")],
        "per_serving": _macros(1, 0, 0, 0),
    }
    swap = _substitute(
        _SWAP,
        {"before": _estimate(None, 1, False), "after": _estimate(None, 1, False)},
        [],
    )
    results = [
        (GET_PLAN_TOOL, plan),
        (GET_MEAL_TOOL, meal),
        (PRICE_TOOL, lines),
        (SUBSTITUTE_TOOL, swap),
    ]
    answer = read_tool_answer(results)
    assert answer is not None and answer.startswith("Chicken tacos for 2 servings")
    assert read_tool_answer(results[:3]) == _INCOMPLETE
    assert str(read_tool_answer(results[:2])).startswith("Bean tacos per serving")
    assert read_tool_answer(results[:1]) == "Your plan has no meals yet."


def test_malformed_payload_returns_none() -> None:
    assert read_tool_answer([(GET_MEAL_TOOL, {"recipe_id": "x"})]) is None


# Real tool payloads. Hand check (demo catalog, per serving of chicken_tacos:
# chicken 100 g, 2 tortillas = 48 g, salsa 40 g, onion 30 g, cumin 1 g,
# olive oil 10 g, salt 1 g):
#   kcal sum 34039 -> 340; protein 2635210 mg/100 -> 26352 mg; carbs 27328 mg;
#   fat 14309 mg. Chickpeas for 100 g chicken: 38439 kcal sum -> 384, protein
#   12712 mg, carbs 54748 mg, fat 14279 mg.
#   Price at 2 servings: chicken 799 + tortillas 299 + salsa 249 + onion 129
#   + cumin 199 + oil 599 + salt 99 = 2373; chickpeas 129 replace 799 -> 1703.
_BUDGET = BudgetResult(10_000, 0, False, ())
_TACOS = {"recipe_id": "chicken_tacos", "servings": 2}
_REAL_SWAP = {
    **_TACOS,
    "replace_ingredient_id": "chicken_breast",
    "with_ingredient_id": "chickpeas",
}
_SWAP_PREFIX = (
    "Chicken tacos for 2 servings with chickpeas instead of chicken breast: "
    "per serving 340 to 384 kcal (+44 kcal), protein 26 to 13 g (-13 g), "
    "carbs 27 to 55 g (+28 g), fat 14 to 14 g (+0 g). "
    "Same weight per serving: 100 g."
)


def _at(value: object, *path: str | int) -> object:
    for key in path:
        value = cast("dict[str | int, object]", value)[key]
    return value


def test_real_substitute_swap() -> None:
    payload = execute_substitute(_REAL_SWAP, _BUDGET)
    assert _at(payload, "before", "per_serving") == {
        "energy_kcal": 340,
        "protein_mg": 26_352,
        "carbohydrate_mg": 27_328,
        "fat_mg": 14_309,
    }
    assert _at(payload, "after", "per_serving") == {
        "energy_kcal": 384,
        "protein_mg": 12_712,
        "carbohydrate_mg": 54_748,
        "fat_mg": 14_279,
    }
    assert _at(payload, "assumptions") == ["Same weight per serving: 100 g."]
    assert _at(payload, "price", "before", "total_cents") == 2_373
    assert _at(payload, "price", "after", "total_cents") == 1_703
    assert _at(payload, "price", "delta_cents") == -670
    assert read_tool_answer([(SUBSTITUTE_TOOL, payload)]) == (
        "Chicken tacos for 2 servings with chickpeas instead of chicken breast: "
        "per serving 340 to 384 kcal (+44 kcal), protein 26 to 13 g (-13 g), "
        "carbs 27 to 55 g (+28 g), fat 14 to 14 g (+0 g). "
        "Same weight per serving: 100 g. "
        "Sample meal price: USD $23.73 to USD $17.03 (-USD $6.70). "
        "Estimated from the demo price catalog. Instacart prices, availability, "
        "taxes, delivery fees, and tips are not verified."
    )


def test_real_substitute_scale() -> None:
    # Chicken at 50 percent = 50 g: kcal sum 28039 -> 280, protein 1510210 mg/100
    # -> 15102 mg, fat 1299870 mg/100 -> 12999 mg, carbs unchanged. One 454 g
    # package still covers 100 g, so the price does not move.
    args: dict[str, object] = {
        **_TACOS,
        "scale_ingredient_id": "chicken_breast",
        "scale_factor_percent": 50,
    }
    payload = execute_substitute(args, _BUDGET)
    assert _at(payload, "after", "per_serving") == {
        "energy_kcal": 280,
        "protein_mg": 15_102,
        "carbohydrate_mg": 27_328,
        "fat_mg": 12_999,
    }
    assert _at(payload, "price", "before", "total_cents") == 2_373
    assert _at(payload, "price", "after", "total_cents") == 2_373
    assert read_tool_answer([(SUBSTITUTE_TOOL, payload)]) == (
        "Chicken tacos for 2 servings with chicken breast changed: "
        "per serving 340 to 280 kcal (-60 kcal), protein 26 to 15 g (-11 g), "
        "carbs 27 to 27 g (+0 g), fat 14 to 13 g (-1 g). Scaled to 50 percent. "
        "Sample meal price: USD $23.73 to USD $23.73 (+USD $0.00). "
        f"{_NOTICE}"
    )


# Chicken tacos x2 plus bean tacos x1: chicken 200 g -> 1 package 799;
# tortillas 6 -> 299; salsa 120 g -> 249; onion 90 g -> 129; cumin 3 g -> 199;
# oil 30 g -> 599; salt 3 g -> 99; black beans 120 g -> 129. Sum 2502.
_LINES_ARGS = {
    "meals": [_TACOS, {"recipe_id": "bean_tacos", "servings": 1}],
    "pantry_ingredient_ids": [],
}


def test_real_price_lines_fits() -> None:
    payload = execute_price_lines(_LINES_ARGS, _BUDGET, None)
    assert _at(payload, "estimate", "total_cents") == 2_502
    assert _at(payload, "estimate", "accepted") is True
    assert read_tool_answer([(PRICE_TOOL, payload)]) == (
        f"Sample total for {_PRICED}: USD $25.02. "
        f"It fits the available USD $100.00. {_NOTICE}"
    )


def test_real_price_lines_exceeds_plan_cap() -> None:
    payload = execute_price_lines(_LINES_ARGS, _BUDGET, 2_000)
    assert _at(payload, "estimate", "total_cents") == 2_502
    assert _at(payload, "estimate", "available_cents") == 2_000
    assert _at(payload, "estimate", "accepted") is False
    assert read_tool_answer([(PRICE_TOOL, payload)]) == (
        f"Sample total for {_PRICED}: USD $25.02. "
        f"It exceeds the available USD $20.00. {_NOTICE}"
    )


def test_real_price_lines_names_swap_and_scale() -> None:
    swap = execute_price_lines({"meals": [_REAL_SWAP]}, _BUDGET, None)
    assert _at(swap, "estimate", "total_cents") == 1_703
    assert read_tool_answer([(PRICE_TOOL, swap)]) == (
        "Sample total for Chicken tacos (2 servings) with chickpeas instead of "
        f"chicken breast: USD $17.03. It fits the available USD $100.00. {_NOTICE}"
    )
    scale: dict[str, object] = {
        **_TACOS,
        "scale_ingredient_id": "chicken_breast",
        "scale_factor_percent": 50,
    }
    scaled = execute_price_lines({"meals": [scale]}, _BUDGET, None)
    assert _at(scaled, "estimate", "total_cents") == 2_373
    assert read_tool_answer([(PRICE_TOOL, scaled)]) == (
        "Sample total for Chicken tacos (2 servings) with chicken breast changed: "
        f"USD $23.73. It fits the available USD $100.00. {_NOTICE}"
    )


def test_stale_warning_precedes_notice_when_total_is_stated() -> None:
    cases = ((None, "fits", "USD $100.00"), (500, "exceeds", "USD $5.00"))
    for cap, verdict, available in cases:
        payload = execute_price_lines({"meals": [_REAL_SWAP]}, _BUDGET, cap)
        expected = (
            "Sample total for Chicken tacos (2 servings) with chickpeas instead of "
            f"chicken breast: USD $17.03. It {verdict} the available {available}. "
            f"{STALE_SPENDING_WARNING} {_NOTICE}"
        )
        assert read_tool_answer([(PRICE_TOOL, payload)], stale=True) == expected
        assert STALE_SPENDING_WARNING not in cast(
            str, read_tool_answer([(PRICE_TOOL, payload)])
        )


def test_stale_warning_skips_replies_without_a_fit_statement() -> None:
    meal = execute_get_meal({"recipe_id": "chicken_tacos"})
    assert STALE_SPENDING_WARNING not in cast(
        str, read_tool_answer([(GET_MEAL_TOOL, meal)], stale=True)
    )
    swap = execute_substitute(_REAL_SWAP, _BUDGET)
    assert STALE_SPENDING_WARNING not in cast(
        str, read_tool_answer([(SUBSTITUTE_TOOL, swap)], stale=True)
    )


def test_failed_flag_appends_failure_sentence() -> None:
    meal = execute_get_meal({"recipe_id": "chicken_tacos"})
    plain = cast(str, read_tool_answer([(GET_MEAL_TOOL, meal)]))
    assert read_tool_answer([(GET_MEAL_TOOL, meal)], failed=True) == (
        f"{plain} A tool call failed. Check the request."
    )


def test_real_incomplete_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        INGREDIENTS, "chickpeas", replace(INGREDIENTS["chickpeas"], price_cents=None)
    )
    swap = execute_substitute(_REAL_SWAP, _BUDGET)
    assert _at(swap, "price", "before", "total_cents") == 2_373
    assert _at(swap, "price", "after", "total_cents") is None
    assert _at(swap, "price", "delta_cents") is None
    assert read_tool_answer([(SUBSTITUTE_TOOL, swap)]) == (
        f"{_SWAP_PREFIX} The sample price is incomplete."
    )
    lines = execute_price_lines({"meals": [_REAL_SWAP]}, _BUDGET, None)
    assert _at(lines, "estimate", "total_cents") is None
    assert read_tool_answer([(PRICE_TOOL, lines)]) == _INCOMPLETE


def test_real_get_meal() -> None:
    payload = execute_get_meal({"recipe_id": "chicken_tacos"})
    assert _at(payload, "per_serving") == {
        "energy_kcal": 340,
        "protein_mg": 26_352,
        "carbohydrate_mg": 27_328,
        "fat_mg": 14_309,
    }
    assert read_tool_answer([(GET_MEAL_TOOL, payload)]) == (
        "Chicken tacos per serving: 340 kcal, 26 g protein, 27 g carbs, "
        "14 g fat. Ingredients: chicken breast, corn tortillas, salsa, onion, "
        "ground cumin, olive oil, salt."
    )


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


def test_real_get_plan_with_meals() -> None:
    # Plan totals: kcal sums 2 x 34039 + 37879 (bean tacos) = 105957 -> 1060;
    # protein 6718830 mg/100 -> 67188 mg; carbs 11043480/100 -> 110435 mg;
    # fat 4095410/100 -> 40954 mg. Cap 5000 lowers the 10000 budget.
    meals = [_TACOS, {"recipe_id": "bean_tacos", "servings": 1}]
    payload = execute_get_plan({}, _revision(meals), _BUDGET)
    request = GroceryRequest.model_validate(
        {"meals": meals, "budget_period": "2026-01-01"}
    )
    expected = meal_nutrition(request).total
    assert expected is not None
    assert _at(payload, "total") == {
        "energy_kcal": expected.energy_kcal,
        "protein_mg": expected.protein_mg,
        "carbohydrate_mg": expected.carbohydrate_mg,
        "fat_mg": expected.fat_mg,
    }
    assert expected.protein_mg == 67_188
    assert _at(payload, "estimate", "total_cents") == 2_502
    assert _at(payload, "estimate", "available_cents") == 5_000
    assert read_tool_answer([(GET_PLAN_TOOL, payload)]) == (
        "Your plan: Chicken tacos (2 servings), Bean tacos (1 serving). "
        "Total: 1060 kcal, 67 g protein, 110 g carbs, 41 g fat. "
        "Sample total for Chicken tacos, Bean tacos: USD $25.02. "
        f"It fits the available USD $50.00. {_NOTICE}"
    )


def test_real_swap_reply_shows_resolved_servings_and_plural_rules() -> None:
    args: dict[str, object] = {
        "recipe_id": "chicken_tacos",
        "replace_ingredient_id": "chicken_breast",
        "with_ingredient_id": "chickpeas",
    }
    planned = execute_substitute(args, _BUDGET, _revision([_TACOS]))
    default = execute_substitute(args, _BUDGET)
    plan_text = read_tool_answer([(SUBSTITUTE_TOOL, planned)])
    default_text = read_tool_answer([(SUBSTITUTE_TOOL, default)])
    assert "Chicken tacos for 2 servings with" in plan_text
    assert "Servings from your plan: 2." in plan_text
    assert "Chicken tacos for 1 serving with" in default_text
    assert "Servings not given; used 1." in default_text


def test_real_price_lines_reply_shows_servings_and_assumptions() -> None:
    args: dict[str, object] = {"meals": [{"recipe_id": "bean_tacos"}]}
    payload = execute_price_lines(args, _BUDGET, None)
    assert _at(payload, "assumptions") == ["Bean tacos: Servings not given; used 1."]
    total = _at(payload, "estimate", "total_cents")
    assert read_tool_answer([(PRICE_TOOL, payload)]) == (
        f"Sample total for Bean tacos (1 serving): {_usd(cast(int, total))}. "
        "It fits the available USD $100.00. "
        f"Bean tacos: Servings not given; used 1. {_NOTICE}"
    )


def test_real_get_plan_without_meals() -> None:
    for plan in (None, _revision([])):
        payload = execute_get_plan({}, plan, _BUDGET)
        assert _at(payload, "meals") == []
        assert read_tool_answer([(GET_PLAN_TOOL, payload)]) == (
            "Your plan has no meals yet."
        )
