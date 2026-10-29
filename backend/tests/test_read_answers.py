from app.agent.chat_answer import _usd
from app.agent.plan_tools import GET_MEAL_TOOL, GET_PLAN_TOOL
from app.agent.price_tool import PRICE_TOOL
from app.agent.read_answers import read_tool_answer
from app.agent.substitute_tool import SUBSTITUTE_TOOL
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE

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


def test_price_lines_fits() -> None:
    payload = _lines_payload(_estimate(1_250, 10_000, True))
    assert read_tool_answer([(PRICE_TOOL, payload)]) == (
        f"Sample total for Chicken tacos, Bean tacos: {_usd(1_250)}. "
        f"It fits the available {_usd(10_000)}. {_NOTICE}"
    )


def test_price_lines_exceeds() -> None:
    payload = _lines_payload(_estimate(1_250, 1_000, False))
    assert read_tool_answer([(PRICE_TOOL, payload)]) == (
        f"Sample total for Chicken tacos, Bean tacos: {_usd(1_250)}. "
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
