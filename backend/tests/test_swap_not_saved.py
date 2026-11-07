from datetime import date
from typing import Any, cast

import pytest

from app.agent.chat_loop import run_chat
from app.agent.chat_answer import CLARIFICATION
from app.agent.chat_messages import last_what_if_recipe
from app.agent.ingredient_tool import resolve_food
from app.agent.price_tool import PRICE_TOOL, execute_price_lines
from app.agent.read_answers import meal_name, read_tool_answer
from app.agent.substitute_tool import (
    SUBSTITUTE_TOOL,
    SubstituteToolError,
    execute_substitute,
    substitute_tool_spec,
)
from app.agent.swap_not_saved import asks_to_save_what_if, swap_not_saved_reply
from app.domain.budget import BudgetResult
from app.domain.catalog import RECIPES
from app.domain.curated_foods import ALL_INGREDIENTS, ALL_NUTRITION
from app.domain.plan_revision import PlanRevisionInput
from app.domain.recipe_variant import ingredient_grams
from app.evaluate_conversation import GoldFollowingProvider
from app.evaluation_conversation import ConversationSelection, run_conversation_suite
from app.evaluation_conversation_corpus import load_conversation_corpus
from tests.test_chat_loop import FakeLLM, _reply, _text_block, _tool_block
from tests.test_evaluation_conversation import _CORPUS

BEANS = "baked_potatoes_with_beans"
CHICKEN = "chicken (ground, raw)"
CHICKEN_ID = "usda_171116"
LIMIT = (
    "I cannot save an ingredient change to your plan yet. That result was a what-if."
)
PERIOD = date(2026, 9, 1)
INVALID = "arguments are invalid"


def _budget() -> BudgetResult:
    return BudgetResult(10_000, 250, False, ())


def _plan() -> PlanRevisionInput:
    return PlanRevisionInput.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "snapshot": {
                "meals": [{"recipe_id": BEANS, "servings": 1}],
                "pantry_ingredient_ids": [],
            },
        }
    )


def _add(**extra: object) -> dict[str, object]:
    args: dict[str, object] = {"recipe_id": BEANS, "servings": 1, "add_food": CHICKEN}
    args.update(extra)
    return args


def _run(
    replies: list[dict[str, object] | BaseException],
    message: str,
    *,
    previous: str | None = None,
    plan: PlanRevisionInput | None = None,
) -> tuple[dict[str, object], FakeLLM]:
    provider = FakeLLM(replies)
    result = run_chat(
        provider,
        message,
        _budget(),
        PERIOD,
        plan_revision=plan,
        propose=None if plan is None else (lambda operations: "proposal-1"),
        model_prose=True,
        previous_what_if_recipe=previous,
    )
    return result, provider


def _unrounded(ingredients: tuple[tuple[str, int], ...]) -> dict[str, int]:
    sums = dict.fromkeys(("energy_kcal", "protein_mg", "carbohydrate_mg", "fat_mg"), 0)
    for ingredient_id, quantity in ingredients:
        grams = ingredient_grams(ingredient_id, quantity)
        for key in sums:
            sums[key] += getattr(ALL_NUTRITION[ingredient_id], key) * grams
    return {key: (value + 50) // 100 for key, value in sums.items()}


def test_add_food_adds_chicken_on_top_of_every_listed_ingredient() -> None:
    result = execute_substitute(_add(), _budget())
    assert result["status"] == "added"
    assert result["change"] == {"add_ingredient_id": CHICKEN_ID}
    before = cast(dict[str, Any], result["before"])
    after = cast(dict[str, Any], result["after"])
    listed = RECIPES[BEANS].ingredients
    assert after["per_serving"] == _unrounded((*listed, (CHICKEN_ID, 100)))
    assert after["per_serving"]["energy_kcal"] == 499
    assert after["per_serving"]["protein_mg"] == 31466
    assert after["per_serving"]["carbohydrate_mg"] == 64895
    assert after["per_serving"]["fat_mg"] == 13878
    assert before["per_serving"] == _unrounded(listed)
    lines = cast(list[dict[str, object]], after["ingredients"])
    assert [line["ingredient_id"] for line in lines] == [
        *(item for item, _ in listed),
        CHICKEN_ID,
    ]
    assert result["assumptions"] == [
        "Added 100 g of chicken (ground, raw) per serving."
    ]


def test_add_food_uses_an_explicit_quantity() -> None:
    result = execute_substitute(_add(quantity_per_serving=50), _budget())
    after = cast(dict[str, object], result["after"])
    lines = cast(list[dict[str, object]], after["ingredients"])
    assert lines[-1]["quantity"] == 50
    assert result["assumptions"] == ["Added 50 g of chicken (ground, raw) per serving."]


def test_add_ingredient_id_defaults_an_each_food_to_one() -> None:
    assert "eggs" not in dict(RECIPES[BEANS].ingredients)
    result = execute_substitute(
        {"recipe_id": BEANS, "servings": 1, "add_ingredient_id": "eggs"}, _budget()
    )
    unit = ALL_INGREDIENTS["eggs"].unit
    assert unit != "g"
    assert result["status"] == "added"
    assert result["assumptions"] == [
        f"Added 1 {unit} of {ALL_INGREDIENTS['eggs'].name} per serving."
    ]


def test_other_forms_keep_the_swapped_status() -> None:
    result = execute_substitute(
        {"recipe_id": BEANS, "servings": 1, "with_food": CHICKEN}, _budget()
    )
    assert result["status"] == "swapped"
    after = cast(dict[str, dict[str, int]], result["after"])
    assert after["per_serving"]["energy_kcal"] == 367


@pytest.mark.parametrize(
    "extra",
    [
        {"with_food": "chickpeas"},
        {"replace_ingredient_id": "black_beans"},
        {"with_ingredient_id": "eggs"},
        {"scale_ingredient_id": "black_beans"},
        {"scale_factor_percent": 50},
        {"add_ingredient_id": "eggs"},
        {"quantity_per_serving": 0},
        {"quantity_per_serving": 1001},
        {"quantity_per_serving": "5"},
        {"quantity_per_serving": True},
    ],
)
def test_add_food_with_another_form_or_bad_quantity_is_a_static_error(
    extra: dict[str, object],
) -> None:
    with pytest.raises(SubstituteToolError) as error:
        execute_substitute(_add(**extra), _budget())
    assert str(error.value) == INVALID


@pytest.mark.parametrize(
    "extra",
    [
        {"add_ingredient_id": "eggs", "replace_ingredient_id": "black_beans"},
        {"add_ingredient_id": "eggs", "with_ingredient_id": "rice"},
        {"add_ingredient_id": "eggs", "scale_ingredient_id": "black_beans"},
        {"add_ingredient_id": "unicorn"},
    ],
)
def test_add_ingredient_id_mixed_or_unknown_is_a_static_error(
    extra: dict[str, object],
) -> None:
    with pytest.raises(SubstituteToolError) as error:
        execute_substitute({"recipe_id": BEANS, **extra}, _budget())
    assert str(error.value) == INVALID


def test_add_food_questions() -> None:
    ambiguous = execute_substitute(_add(add_food="chicken"), _budget())
    assert ambiguous["status"] == "needs_food_choice"
    unknown = execute_substitute(_add(add_food="zzzqxv"), _budget())
    assert unknown["status"] == "unknown_food"


def _food_in_meal() -> tuple[str, str]:
    for ingredient_id, _ in RECIPES[BEANS].ingredients:
        name = ALL_INGREDIENTS[ingredient_id].name
        found = resolve_food(name)
        if found.status == "found" and found.ids[0] == ingredient_id:
            return ingredient_id, name
    raise AssertionError("no listed ingredient resolves by name")


def test_a_food_already_in_the_meal_asks_for_a_percent() -> None:
    ingredient_id, name = _food_in_meal()
    by_name = execute_substitute(_add(add_food=name), _budget())
    by_id = execute_substitute(
        {"recipe_id": BEANS, "servings": 1, "add_ingredient_id": ingredient_id},
        _budget(),
    )
    for result in (by_name, by_id):
        assert result["status"] == "ingredient_already_in_meal"
        assert result["recipe_id"] == BEANS
        assert result["candidates"] == [{"ingredient_id": ingredient_id, "name": name}]
        assert read_tool_answer([(SUBSTITUTE_TOOL, result)]) == (
            f"{meal_name(BEANS)} already lists {name}. "
            "Give a percent to change its amount."
        )


def test_the_added_result_reads_with_the_food_added() -> None:
    result = execute_substitute(_add(), _budget())
    text = read_tool_answer([(SUBSTITUTE_TOOL, result)])
    assert text is not None
    assert text.startswith(
        "Baked potatoes with beans for 1 serving with chicken (ground, raw) added: "
        "per serving "
    )
    assert "Added 100 g of chicken (ground, raw) per serving." in text


def test_price_lines_prices_an_added_food() -> None:
    payload = execute_price_lines(
        {
            "meals": [
                {
                    "recipe_id": BEANS,
                    "servings": 1,
                    "add_ingredient_id": "chicken_breast",
                }
            ]
        },
        _budget(),
        None,
    )
    text = read_tool_answer([(PRICE_TOOL, payload)])
    assert text is not None
    assert "Baked potatoes with beans (1 serving) with" in text
    assert "added" in text
    assert "Sample total for" in text


def test_price_lines_reports_an_added_food_with_no_price() -> None:
    payload = execute_price_lines(
        {
            "meals": [
                {"recipe_id": BEANS, "servings": 1, "add_ingredient_id": CHICKEN_ID}
            ]
        },
        _budget(),
        None,
    )
    text = read_tool_answer([(PRICE_TOOL, payload)])
    assert text == "The sample total is incomplete because a price is missing."


@pytest.mark.parametrize(
    "extra", [{"scale_factor_percent": 50}, {"quantity_per_serving": 0}]
)
def test_an_added_food_already_in_the_meal_still_rejects_bad_arguments(
    extra: dict[str, object],
) -> None:
    with pytest.raises(SubstituteToolError):
        execute_substitute(
            {"recipe_id": BEANS, "add_ingredient_id": "black_beans", **extra},
            _budget(),
        )


def test_the_tool_spec_offers_the_add_form() -> None:
    spec = substitute_tool_spec()
    text = str(spec)
    assert "replaced, scaled, or added" in text
    assert (
        "To add a food and keep every listed ingredient, for example both foods "
        "or on top of, give add_food; quantity_per_serving is optional."
    ) in text
    assert "add_food" in text and "add_ingredient_id" in text


def test_the_trace_records_the_added_ingredient_and_the_turn_is_final() -> None:
    result, _ = _run(
        [
            _reply([_tool_block("call-1", SUBSTITUTE_TOOL, _add())], "tool_use"),
            _reply([_text_block("Here is the what-if.")], "end_turn"),
        ],
        "What if we have both the chicken and black beans at the same time?",
    )
    trace = cast(list[dict[str, object]], result["tool_trace"])
    inputs = cast(dict[str, object], trace[0]["inputs"])
    assert inputs["status"] == "added"
    assert inputs["add_ingredient_id"] == CHICKEN_ID
    assert inputs["recipe_id"] == BEANS
    check = cast(dict[str, object], result["reply_check"])
    assert check["gate"] != "not_final"
    assert last_what_if_recipe(result) == BEANS
    assert "proposal_id" not in result


def _entry(status: str | None, recipe: str = BEANS) -> dict[str, object]:
    inputs: dict[str, object] = {"recipe_id": recipe}
    if status is not None:
        inputs["status"] = status
    return {"tool": SUBSTITUTE_TOOL, "outcome": "success", "inputs": inputs}


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        ([_entry("swapped")], BEANS),
        ([_entry("added")], BEANS),
        ([_entry("swapped", "bean_tacos"), _entry("added")], BEANS),
        ([_entry("swapped"), _entry("needs_food_choice")], None),
        ([_entry("added"), {"tool": "get_meal", "inputs": {}}], BEANS),
        ([_entry(None)], None),
        ([{"tool": "get_meal", "inputs": {"recipe_id": BEANS}}], None),
        ([], None),
    ],
)
def test_last_what_if_recipe_reads_the_latest_what_if(
    trace: list[dict[str, object]], expected: str | None
) -> None:
    assert last_what_if_recipe({"tool_trace": trace}) == expected
    assert last_what_if_recipe({}) is None
    assert last_what_if_recipe({"tool_trace": "x"}) is None


@pytest.mark.parametrize(
    "message",
    [
        "can you add it to the list",
        "add it",
        "Save that to my plan.",
        "put this in my plan please",
        "  Could you SAVE   this meal to the shopping list?  ",
    ],
)
def test_asks_to_save_accepts_a_save_request(message: str) -> None:
    assert asks_to_save_what_if(message)


@pytest.mark.parametrize(
    "message",
    [
        "add chicken to it",
        "thanks",
        "add bean tacos to my plan",
        "what if we add it",
        "add it to the salad",
        "",
    ],
)
def test_asks_to_save_rejects_other_messages(message: str) -> None:
    assert not asks_to_save_what_if(message)


def test_the_two_replies_by_exact_string() -> None:
    meal = "Baked potatoes with beans"
    assert swap_not_saved_reply(BEANS, _plan()) == (
        f"{LIMIT} {meal} is already in your plan as listed."
    )
    assert swap_not_saved_reply(BEANS, None) == (
        f"{LIMIT} To add the listed meal, say: add {meal} to my plan."
    )
    other = PlanRevisionInput.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000002",
            "snapshot": {
                "meals": [{"recipe_id": "bean_tacos", "servings": 1}],
                "pantry_ingredient_ids": [],
            },
        }
    )
    assert swap_not_saved_reply(BEANS, other) == swap_not_saved_reply(BEANS, None)


def test_an_earlier_question_survives_a_later_failed_call() -> None:
    swap = {"recipe_id": BEANS, "with_food": "chicken"}
    result, _ = _run(
        [
            _reply([_tool_block("call-1", SUBSTITUTE_TOOL, swap)], "tool_use"),
            _reply(
                [
                    _tool_block(
                        "call-2", SUBSTITUTE_TOOL, {**swap, "add_food": "chicken"}
                    )
                ],
                "tool_use",
            ),
            _reply([_text_block("Done.")], "end_turn"),
        ],
        "What if we use chicken instead?",
    )
    answer = cast(str, result["answer"])
    assert answer.startswith("Which one do you mean:")
    assert answer.endswith("A tool call failed. Check the request.")
    assert "Examples:" not in answer
    assert last_what_if_recipe(result) is None


def test_an_earlier_swap_is_not_the_reply_to_a_later_failed_call() -> None:
    swap = {"recipe_id": BEANS, "with_food": "chicken"}
    swapped, _ = _run(
        [
            _reply([_tool_block("call-1", SUBSTITUTE_TOOL, swap)], "tool_use"),
            _reply([_text_block("Done.")], "end_turn"),
        ],
        "What if we use chicken instead?",
    )
    swap_clause = cast(str, swapped["answer"])
    result, _ = _run(
        [
            _reply([_tool_block("call-1", SUBSTITUTE_TOOL, swap)], "tool_use"),
            _reply(
                [_tool_block("call-2", SUBSTITUTE_TOOL, {"recipe_id": "nope"})],
                "tool_use",
            ),
            _reply([_text_block("Done.")], "end_turn"),
        ],
        "What if we use chicken instead?",
    )
    answer = cast(str, result["answer"])
    assert swap_clause not in answer
    assert answer == CLARIFICATION


@pytest.mark.parametrize(
    "arguments",
    [
        {"add_ingredient_id": "eggs", "with_ingredient_id": "rice"},
        {"with_ingredient_id": 5},
    ],
)
@pytest.mark.parametrize("recipe_id", ["vegetable_pasta", "chicken_lentil_stew"])
def test_the_protein_default_applies_only_to_the_plain_substitute_form(
    recipe_id: str, arguments: dict[str, object]
) -> None:
    with pytest.raises(SubstituteToolError):
        execute_substitute({"recipe_id": recipe_id, **arguments}, _budget())


def test_the_route_answers_without_a_provider_call_or_a_proposal() -> None:
    message = "can you add it to the list"
    result, provider = _run([], message, previous=BEANS, plan=_plan())
    assert provider.requests == []
    assert result["status"] == "clarification"
    assert result["reply_source"] == "template"
    assert result["reply_check"] == {"gate": "swap_not_saved"}
    assert result["answer"] == swap_not_saved_reply(BEANS, _plan())
    assert result["tool_trace"] == []
    assert result["model_turns"] == 0
    assert "proposal_id" not in result


def test_the_route_needs_a_previous_what_if() -> None:
    result, provider = _run(
        [_reply([_text_block("Say which meal to add.")], "end_turn")],
        "can you add it to the list",
        plan=_plan(),
    )
    assert len(provider.requests) == 1
    assert result["model_turns"] == 1
    check = cast(dict[str, object] | None, result["reply_check"])
    assert check is None or check.get("gate") != "swap_not_saved"


def test_a_non_matching_message_reaches_the_provider() -> None:
    result, provider = _run(
        [_reply([_text_block("Chicken is 31 g protein.")], "end_turn")],
        "add chicken to it",
        previous=BEANS,
    )
    assert len(provider.requests) == 1
    assert result["model_turns"] == 1


def test_c25_records_the_swap_not_saved_gate_on_turn_two() -> None:
    corpus = load_conversation_corpus(_CORPUS)
    selection = ConversationSelection.model_validate(
        {"scenarios": [{"scenario_id": "C25", "repeats": [1]}]}
    )
    records = list(
        run_conversation_suite(
            corpus,
            "fixture",
            lambda scenario, repeat, index: GoldFollowingProvider(
                scenario.turns[index - 1]
            ),
            selection=selection,
        )
    )
    assert [r["turn"] for r in records] == [1, 2]
    assert records[1]["gate"] == "swap_not_saved"
    assert records[1]["provider_requests"] == 0
    assert records[1]["proposal"] is False
    assert records[1]["tools"] == []
