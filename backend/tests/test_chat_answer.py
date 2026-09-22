from __future__ import annotations

import json

from test_chat_loop import (
    _SECRET,
    PERIOD,
    FakeLLM,
    _error_trace,
    _reply,
    _success_trace,
    _text_block,
    _tool_block,
    budget,
    plan_args,
)

from app.agent.chat_answer import (
    CLARIFY_ANSWER,
    FALLBACK_ANSWER,
    INCOMPLETE_ANSWER,
    format_usd_cents,
    render_public_answer,
    safe_tool_error,
)
from app.agent.chat_loop import run_chat
from app.agent.planning_tool import TOOL_NAME, execute_plan
from app.domain.budget import STALE_SPENDING_WARNING
from app.domain.catalog import INGREDIENTS
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE, SUPPORTED_RECIPE_IDS

_MODEL_PROSE = (
    "Black beans cost $2.41 and remaining budget is spent. "
    "Remove eggs from the pantry. Nightshades include salsa. "
    f"{_SECRET}"
)
_FORBIDDEN = (
    "purchase",
    "buy",
    "remaining budget",
    "$2.41",
    "reasoningContent",
    "hidden plan",
    "nightshades",
    "mystery_spice",
    _SECRET,
)


def _candidate(
    *,
    total: int | None,
    available: int,
    accepted: bool,
    stale: bool = False,
    warnings: list[str] | None = None,
) -> dict[str, object]:
    return {
        "plan": {"total_cents": total, "accepted": accepted, "lines": []},
        "budget": {
            "available_cents": available,
            "stale": stale,
            "warnings": [] if warnings is None else warnings,
        },
    }


def _error_block(code: str, ingredient_id: str) -> dict[str, object]:
    return {
        "toolResult": {
            "toolUseId": "err-1",
            "content": [{"json": {"error": code, "ingredient_id": ingredient_id}}],
            "status": "error",
        }
    }


def _assert_grounded(answer: str) -> None:
    lowered = answer.lower()
    for token in _FORBIDDEN:
        assert token not in answer
        assert token.lower() not in lowered
    dumped = json.dumps({"answer": answer})
    assert _SECRET not in dumped


def test_accepted_plan_states_total_and_budget() -> None:
    candidate = _candidate(total=1703, available=10_000, accepted=True)
    answer = render_public_answer(
        candidate, {"error": "diet_conflict", "ingredient_id": "eggs"}
    )
    assert answer == (
        "The sample estimate total is USD $17.03 against a planning "
        f"budget of USD $100.00. {SAMPLE_ESTIMATE_NOTICE}"
    )
    assert "USD $17.03" in answer
    assert "USD $100.00" in answer
    assert "$1.29" not in answer
    assert "eggs" not in answer
    _assert_grounded(answer)


def test_overbudget_requests_revision_without_reduction() -> None:
    candidate = _candidate(total=3471, available=1, accepted=False)
    answer = render_public_answer(candidate)
    assert answer == (
        "The sample estimate total is USD $34.71. "
        "The available planning budget is USD $0.01. "
        "Revise the request. The estimate is not reduced. "
        f"{SAMPLE_ESTIMATE_NOTICE}"
    )
    assert "not reduced" in answer
    _assert_grounded(answer)


def test_incomplete_total_is_unaccepted() -> None:
    candidate = _candidate(total=None, available=10_000, accepted=False)
    answer = render_public_answer(candidate)
    assert answer == INCOMPLETE_ANSWER
    assert "incomplete" in answer
    assert "not accepted" in answer
    assert "USD $" not in answer
    _assert_grounded(answer)


def test_known_diet_conflict_names_ingredient() -> None:
    answer = render_public_answer(
        None, {"error": "diet_conflict", "ingredient_id": "eggs"}
    )
    assert "eggs" in answer
    assert "cannot omit" in answer
    assert "Choose another recipe or change the restriction." in answer
    assert "pantry" not in answer
    _assert_grounded(answer)


def test_known_exclusion_conflict_names_ingredient() -> None:
    answer = render_public_answer(
        None, {"error": "exclusion_conflict", "ingredient_id": "chicken_breast"}
    )
    assert "chicken breast" in answer
    assert "cannot omit" in answer
    assert "pantry" not in answer
    _assert_grounded(answer)


def test_unknown_metadata_stays_generic() -> None:
    unknown = render_public_answer(
        None, {"error": "diet_conflict", "ingredient_id": "nightshades"}
    )
    invalid = render_public_answer(None, {"error": "leak", "ingredient_id": "eggs"})
    missing = render_public_answer(None, None)
    for answer in (unknown, invalid, missing):
        assert answer == CLARIFY_ANSWER
        assert "nightshades" not in answer
        assert "leak" not in answer
        assert "exact catalog IDs" not in answer
        for recipe_id in SUPPORTED_RECIPE_IDS:
            readable = recipe_id.replace("_", " ")
            assert readable in answer
            if "_" in recipe_id:
                assert recipe_id not in answer
        for ingredient in INGREDIENTS.values():
            assert ingredient.name in answer
            if "_" in ingredient.id:
                assert ingredient.id not in answer
        _assert_grounded(answer)


def test_large_int_cents_format() -> None:
    cents = 123456789
    candidate = _candidate(total=cents, available=10**18, accepted=True)
    answer = render_public_answer(candidate)
    assert format_usd_cents(cents) == "USD $1234567.89"
    assert format_usd_cents(10**18) == "USD $10000000000000000.00"
    assert "USD $1234567.89" in answer
    assert "USD $10000000000000000.00" in answer
    _assert_grounded(answer)


def test_malformed_candidate_uses_fallback() -> None:
    cases: list[dict[str, object]] = [
        {},
        {
            "plan": {"total_cents": True, "accepted": True},
            "budget": {"available_cents": 1},
        },
        {"plan": "bad", "budget": {"available_cents": 1, "stale": False}},
        {
            "plan": {"total_cents": 1, "accepted": True},
            "budget": {"available_cents": True},
        },
    ]
    for candidate in cases:
        answer = render_public_answer(candidate)
        assert answer == FALLBACK_ANSWER
        assert "Traceback" not in answer
        _assert_grounded(answer)


def test_stale_budget_preserves_warning() -> None:
    candidate = _candidate(
        total=1703,
        available=5_000,
        accepted=True,
        stale=True,
        warnings=[STALE_SPENDING_WARNING],
    )
    answer = render_public_answer(candidate)
    assert STALE_SPENDING_WARNING in answer
    assert "USD $17.03" in answer
    _assert_grounded(answer)


def test_stale_without_warning_list_uses_known_warning() -> None:
    candidate = _candidate(
        total=None,
        available=5_000,
        accepted=False,
        stale=True,
        warnings=[_SECRET],
    )
    answer = render_public_answer(candidate)
    assert STALE_SPENDING_WARNING in answer
    assert _SECRET not in answer
    assert answer.startswith(INCOMPLETE_ANSWER)
    _assert_grounded(answer)


def test_valid_plan_supersedes_error() -> None:
    candidate = _candidate(total=1703, available=10_000, accepted=True)
    answer = render_public_answer(
        candidate, {"error": "diet_conflict", "ingredient_id": "eggs"}
    )
    assert "eggs" not in answer
    assert "USD $17.03" in answer
    assert "USD $100.00" in answer
    _assert_grounded(answer)


def test_safe_tool_error_allowlist() -> None:
    known = safe_tool_error(_error_block("diet_conflict", "eggs"))
    assert known == {"error": "diet_conflict", "ingredient_id": "eggs"}
    unknown = safe_tool_error(_error_block("diet_conflict", "nightshades"))
    assert unknown is None
    generic = safe_tool_error(
        {
            "toolResult": {
                "toolUseId": "bad",
                "content": [{"json": {"error": "arguments are invalid"}}],
                "status": "error",
            }
        }
    )
    assert generic is None
    assert safe_tool_error({"text": _SECRET}) is None


def test_run_chat_uses_rendered_answer_and_preserves_result() -> None:
    expected = execute_plan(plan_args(), budget(), PERIOD)
    hidden = {"text": "hidden plan"}
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("call-1")], "tool_use"),
        _reply([_text_block(_MODEL_PROSE, reasoning=hidden)], "end_turn"),
    ]
    provider = FakeLLM(replies)
    result = run_chat(provider, "plan chicken tacos", budget(), PERIOD)
    answer = render_public_answer(expected)
    assert result["answer"] == answer
    assert result["answer"] != _MODEL_PROSE
    assert result["status"] == "planned"
    assert result["plan"] == expected["plan"]
    assert result["request"] == expected["request"]
    assert result["budget"] == expected["budget"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    assert result["tool_trace"] == [_success_trace("call-1", expected["evidence_id"])]
    dumped = json.dumps(result)
    assert _MODEL_PROSE not in dumped
    assert "reasoningContent" not in dumped
    _assert_grounded(str(result["answer"]))


def test_run_chat_conflict_uses_allowlisted_error() -> None:
    payload = plan_args(
        meals=[{"recipe_id": "breakfast_burritos", "servings": 1}],
        diet="vegan",
    )
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("vegan-1", payload=payload)], "tool_use"),
        _reply(
            [_text_block("Remove eggs or drop the vegan diet from the pantry.")],
            "end_turn",
        ),
    ]
    provider = FakeLLM(replies)
    result = run_chat(provider, "plan breakfast burritos vegan", budget(), PERIOD)
    expected = render_public_answer(
        None, {"error": "diet_conflict", "ingredient_id": "eggs"}
    )
    assert result["answer"] == expected
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["request"] is None
    assert result["usage"] == {"inputTokens": 2, "outputTokens": 2}
    assert result["tool_trace"] == [_error_trace(TOOL_NAME, "vegan-1")]
    assert "pantry" not in str(result["answer"])
    assert "Remove eggs" not in str(result["answer"])
    _assert_grounded(str(result["answer"]))


def test_run_chat_later_plan_clears_prior_conflict() -> None:
    vegan = plan_args(
        meals=[{"recipe_id": "breakfast_burritos", "servings": 1}],
        diet="vegan",
    )
    good = plan_args()
    replies: list[dict[str, object] | BaseException] = [
        _reply([_tool_block("vegan-1", payload=vegan)], "tool_use"),
        _reply([_tool_block("ok", payload=good)], "tool_use"),
        _reply([_text_block("done")], "end_turn"),
    ]
    provider = FakeLLM(replies)
    result = run_chat(provider, "plan chicken tacos", budget(), PERIOD)
    expected = execute_plan(good, budget(), PERIOD)
    assert result["status"] == "planned"
    assert result["answer"] == render_public_answer(expected)
    assert result["plan"] == expected["plan"]
    assert result["usage"] == {"inputTokens": 3, "outputTokens": 3}
    assert "eggs" not in str(result["answer"])
    _assert_grounded(str(result["answer"]))


def test_run_chat_latest_conflict_replaces_prior_plan() -> None:
    vegan = plan_args(
        meals=[{"recipe_id": "breakfast_burritos", "servings": 1}],
        diet="vegan",
    )
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_tool_block("ok"), _tool_block("vegan-1", payload=vegan)],
            "tool_use",
        ),
        _reply([_text_block("Remove eggs from the pantry.")], "end_turn"),
    ]
    provider = FakeLLM(replies)
    result = run_chat(provider, "plan meals", budget(), PERIOD)
    expected = render_public_answer(
        None, {"error": "diet_conflict", "ingredient_id": "eggs"}
    )
    assert result["status"] == "clarification"
    assert result["answer"] == expected
    assert result["plan"] is None
    assert "pantry" not in str(result["answer"])
    _assert_grounded(str(result["answer"]))


def test_run_chat_unknown_restriction_does_not_echo_guess() -> None:
    replies: list[dict[str, object] | BaseException] = [
        _reply(
            [_text_block("Nightshades include salsa, tomato, and potato.")],
            "end_turn",
        )
    ]
    provider = FakeLLM(replies)
    result = run_chat(
        provider,
        "Plan bean tacos without nightshades",
        budget(),
        PERIOD,
    )
    assert result["answer"] == CLARIFY_ANSWER
    assert result["answer"] != "Nightshades include salsa, tomato, and potato."
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["usage"] == {"inputTokens": 1, "outputTokens": 1}
    dumped = json.dumps(result)
    assert "nightshades" not in dumped
    assert "Nightshades" not in dumped
    _assert_grounded(str(result["answer"]))
