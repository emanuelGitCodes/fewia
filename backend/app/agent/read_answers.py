from collections.abc import Sequence

from app.agent.chat_answer import _usd
from app.agent.plan_tools import GET_MEAL_TOOL, GET_PLAN_TOOL
from app.agent.price_tool import PRICE_TOOL, meal_name as _meal
from app.agent.substitute_tool import SUBSTITUTE_TOOL
from app.domain.budget import STALE_SPENDING_WARNING
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE

TOOL_FAILED = "A tool call failed. Check the request."
_PRIORITY = (SUBSTITUTE_TOOL, PRICE_TOOL, GET_MEAL_TOOL, GET_PLAN_TOOL)
_INCOMPLETE_TOTAL = "The sample total is incomplete because a price is missing."


def _d(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("payload is invalid")
    return value


def _int(value: object) -> int:
    if type(value) is not int:
        raise TypeError("payload is invalid")
    return value


def _grams(mg: object) -> int:
    return (abs(_int(mg)) * 2 + 1000) // 2000 * (-1 if _int(mg) < 0 else 1)


def _signed(value: int) -> str:
    return f"{value:+d}"


def _macro_line(macros: dict[str, object]) -> str:
    return (
        f"{_int(macros['energy_kcal'])} kcal, "
        f"{_grams(macros['protein_mg'])} g protein, "
        f"{_grams(macros['carbohydrate_mg'])} g carbs, "
        f"{_grams(macros['fat_mg'])} g fat"
    )


def _signed_usd(cents: int) -> str:
    sign = "-" if cents < 0 else "+"
    return f"{sign}{_usd(abs(cents))}"


def _servings(count: int) -> str:
    return f"{count} serving" if count == 1 else f"{count} servings"


def _change_clause(before: dict[str, object], after: dict[str, object]) -> str:
    e0, e1 = _int(before["energy_kcal"]), _int(after["energy_kcal"])
    parts = [f"per serving {e0} to {e1} kcal ({_signed(e1 - e0)} kcal)"]
    for label, key in (
        ("protein", "protein_mg"),
        ("carbs", "carbohydrate_mg"),
        ("fat", "fat_mg"),
    ):
        g0, g1 = _grams(before[key]), _grams(after[key])
        parts.append(f"{label} {g0} to {g1} g ({_signed(g1 - g0)} g)")
    return ", ".join(parts)


def _names(payload: dict[str, object]) -> dict[str, str]:
    names: dict[str, str] = {}
    for side in ("before", "after"):
        lines = _d(payload[side])["ingredients"]
        if not isinstance(lines, list):
            raise TypeError("payload is invalid")
        for line in lines:
            item = _d(line)
            names[str(item["ingredient_id"])] = str(item["name"])
    return names


def _total_sentence(
    meals: str, estimate: dict[str, object], stale: bool
) -> tuple[str, bool]:
    total = estimate.get("total_cents")
    if type(total) is not int:
        return _INCOMPLETE_TOTAL, False
    available = _usd(_int(estimate["available_cents"]))
    verdict = "fits" if estimate.get("accepted") is True else "exceeds"
    text = (
        f"Sample total for {meals}: {_usd(total)}. "
        f"It {verdict} the available {available}."
    )
    if stale:
        text += f" {STALE_SPENDING_WARNING}"
    return text, True


def _priced_meal(item: dict[str, object]) -> str:
    name = _meal(item["recipe_id"])
    change = item.get("change")
    if not isinstance(change, dict):
        return name
    if "scale_ingredient_id" in change:
        return f"{name} with {_catalog_name(change['scale_ingredient_id'])} changed"
    new = _catalog_name(change["with_ingredient_id"])
    old = _catalog_name(change["replace_ingredient_id"])
    return f"{name} with {new} instead of {old}"


def _catalog_name(ingredient_id: object) -> str:
    return INGREDIENTS[str(ingredient_id)].name


def _with_notice(text: str, shown: bool) -> str:
    return f"{text} {SAMPLE_ESTIMATE_NOTICE}" if shown else text


def _substitute(payload: dict[str, object]) -> str:
    names = _names(payload)
    change = _d(payload["change"])
    if "scale_ingredient_id" in change:
        swap = f"{names[str(change['scale_ingredient_id'])]} changed"
    else:
        new = names[str(change["with_ingredient_id"])]
        old = names[str(change["replace_ingredient_id"])]
        swap = f"{new} instead of {old}"
    clause = _change_clause(
        _d(_d(payload["before"])["per_serving"]),
        _d(_d(payload["after"])["per_serving"]),
    )
    assumptions = " ".join(str(item) for item in _d_list(payload["assumptions"]))
    text = (
        f"{_meal(payload['recipe_id'])} for {_servings(_int(payload['servings']))} "
        f"with {swap}: {clause}. {assumptions}"
    ).rstrip()
    price = _d(payload["price"])
    before = _d(price["before"]).get("total_cents")
    after = _d(price["after"]).get("total_cents")
    delta = price.get("delta_cents")
    if type(before) is int and type(after) is int and type(delta) is int:
        text += (
            f" Sample meal price: {_usd(before)} to {_usd(after)} "
            f"({_signed_usd(delta)})."
        )
        return _with_notice(text, True)
    return f"{text} The sample price is incomplete."


def _d_list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("payload is invalid")
    return value


def _price_lines(payload: dict[str, object], stale: bool) -> str:
    items = _d_list(payload["meals"])
    meals = ", ".join(_priced_meal(_d(item)) for item in items)
    text, shown = _total_sentence(meals, _d(payload["estimate"]), stale)
    return _with_notice(text, shown)


def _get_meal(payload: dict[str, object]) -> str:
    lines = _d_list(payload["ingredients"])
    names = ", ".join(str(_d(line)["name"]) for line in lines)
    return (
        f"{_meal(payload['recipe_id'])} per serving: "
        f"{_macro_line(_d(payload['per_serving']))}. Ingredients: {names}."
    )


def _get_plan(payload: dict[str, object], stale: bool) -> str:
    meals = _d_list(payload["meals"])
    if not meals:
        return "Your plan has no meals yet."
    items = [_d(item) for item in meals]
    listed = ", ".join(
        f"{_meal(item['recipe_id'])} ({_servings(_int(item['servings']))})"
        for item in items
    )
    text = f"Your plan: {listed}."
    if payload.get("total") is not None:
        text += f" Total: {_macro_line(_d(payload['total']))}."
    if payload.get("estimate") is None:
        return text
    names = ", ".join(_meal(item["recipe_id"]) for item in items)
    sentence, shown = _total_sentence(names, _d(payload["estimate"]), stale)
    return _with_notice(f"{text} {sentence}", shown)


def _render(name: str, payload: dict[str, object], stale: bool) -> str:
    if name == SUBSTITUTE_TOOL:
        return _substitute(payload)
    if name == PRICE_TOOL:
        return _price_lines(payload, stale)
    if name == GET_MEAL_TOOL:
        return _get_meal(payload)
    return _get_plan(payload, stale)


def read_tool_answer(
    results: Sequence[tuple[str, dict[str, object]]],
    *,
    stale: bool = False,
    failed: bool = False,
) -> str | None:
    for name in _PRIORITY:
        for tool, payload in reversed(results):
            if tool == name:
                try:
                    text = _render(name, payload, stale)
                except (KeyError, TypeError, ValueError):
                    return None
                return f"{text} {TOOL_FAILED}" if failed else text
    return None
