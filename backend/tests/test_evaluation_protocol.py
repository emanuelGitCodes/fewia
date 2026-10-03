import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from app import evaluation_protocol as protocol
from app.agent import chat_loop
from app.agent.provider import LLMProvider, LLMUnavailable
from app.domain.budget import BudgetResult
from app.evaluation_fault_provider import (
    PROTOCOL_VARIANTS,
    UNAVAILABLE_VARIANTS,
    FaultProvider,
)


def _case(case_id: str) -> dict[str, object]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    corpus = cast(dict[str, object], json.loads(path.read_text()))
    cases = cast(list[dict[str, object]], corpus["scenarios"])
    return deepcopy(next(case for case in cases if case["id"] == case_id))


def _map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _replace(case: dict[str, object], path: tuple[str, ...], value: object) -> None:
    parent = case
    for key in path[:-1]:
        parent = _map(parent[key])
    parent[path[-1]] = value


def _assert_labels(report: dict[str, object]) -> None:
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert report["controlled_fault"] is True
    assert report["model_quality_applicable"] is False
    assert "requires_model" in cast(str, report["scope"])
    assert "Forced faults exclude model quality." in cast(str, report["scope"])
    assert "real_bedrock" not in json.dumps(report)


def _assert_unassessed(report: dict[str, object]) -> None:
    _assert_labels(report)
    assert report["status"] == "unassessed"
    assert report["reason"] == "invalid_case"
    assert report["checks"] == {}
    assert report["observed"] == {}


def test_approved_helper_is_the_only_provider_and_variant_source() -> None:
    assert protocol.FaultProvider is FaultProvider
    assert protocol.PROTOCOL_VARIANTS is PROTOCOL_VARIANTS
    assert protocol.UNAVAILABLE_VARIANTS is UNAVAILABLE_VARIANTS


def test_p03_executes_unavailability_without_exporting_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "SYNTHETIC_EXCEPTION_ONLY_SENTINEL"
    attempts: list[str] = []

    def unavailable(
        self: FaultProvider,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls += 1
        attempts.append(self.variant)
        raise LLMUnavailable(sentinel)

    monkeypatch.setattr(FaultProvider, "converse", unavailable)
    case = _case("P03")
    original = deepcopy(case)
    report = protocol.evaluate_protocol_case(case)
    _assert_labels(report)
    assert report["case_id"] == "P03"
    assert report["status"] == "scored"
    assert report["checks"] == {"unavailable": True}
    assert _map(report["observed"])["unavailable"] == {
        "outcome": "chat_unavailable",
        "model_calls": 1,
        "rejected_results_observed": 0,
        "no_plan": True,
        "no_answer": True,
        "model_turns": None,
        "planner_revisions": None,
    }
    assert attempts == ["unavailable"]
    assert sentinel not in json.dumps(report)
    assert case == original


def test_p04_executes_every_variant_and_both_limits() -> None:
    case = _case("P04")
    original = deepcopy(case)
    report = protocol.evaluate_protocol_case(case)
    _assert_labels(report)
    assert report["status"] == "scored"
    checks, observed = _map(report["checks"]), _map(report["observed"])
    expected = {
        "unknown_tool": (8, 7, "limit", 8, 0),
        "invalid_planner": (4, 3, "limit", 4, 3),
        "malformed_input": (1, 0, "chat_protocol_error", None, None),
        "duplicate_id": (2, 1, "chat_protocol_error", None, None),
        "too_many_tools": (1, 0, "chat_protocol_error", None, None),
        "stop_mismatch": (1, 0, "chat_protocol_error", None, None),
    }
    assert set(checks) == set(observed) == set(expected) == set(PROTOCOL_VARIANTS)
    for variant, (calls, errors, outcome, turns, revisions) in expected.items():
        assert checks[variant] is True
        assert observed[variant] == {
            "outcome": outcome,
            "model_calls": calls,
            "rejected_results_observed": errors,
            "no_plan": True,
            "no_answer": True,
            "model_turns": turns,
            "planner_revisions": revisions,
        }
    assert case == original


@pytest.mark.parametrize("case_id", ["P03", "P04"])
def test_expected_and_evidence_poison_cannot_change_calls_or_observations(
    case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_converse = FaultProvider.converse
    attempts: list[tuple[str, int, dict[str, object] | None]] = []

    def record(
        self: FaultProvider,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        response: dict[str, object] | None = None
        try:
            response = original_converse(self, system_prompt, messages, tools)
            return response
        finally:
            attempts.append((self.variant, self.calls, deepcopy(response)))

    monkeypatch.setattr(FaultProvider, "converse", record)
    case = _case(case_id)
    baseline = protocol.evaluate_protocol_case(case)
    _assert_labels(baseline)
    baseline_attempts = deepcopy(attempts)
    for expected in ({"accepted": True, "max_model_turns": 10000}, None):
        attempts.clear()
        case["expected"] = expected
        case["evidence_class"] = "real_bedrock"
        case["evidence"] = {"controlled_fault": False, "answer": "POISON"}
        case["model_quality_applicable"] = True
        assert protocol.evaluate_protocol_case(case) == baseline
        assert attempts == baseline_attempts
    attempts.clear()
    case.pop("expected")
    assert protocol.evaluate_protocol_case(case) == baseline
    assert attempts == baseline_attempts


def test_messages_and_budget_inputs_reach_chat_loop_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_chat = chat_loop.run_chat
    captured: list[tuple[str, list[dict[str, str]] | None, date, int | None]] = []

    def record(
        provider: LLMProvider,
        message: str,
        budget: BudgetResult,
        period: date,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        captured.append((message, deepcopy(history), period, budget.available_cents))
        return run_chat(provider, message, budget, period, history=history)

    monkeypatch.setattr(chat_loop, "run_chat", record)
    case = _case("P03")
    case["messages"] = [
        {"role": "user", "content": "Earlier user message."},
        {"role": "assistant", "content": "Earlier assistant reply."},
        {"role": "user", "content": "Current message."},
    ]
    case["prompt"] = "This prompt MUST NOT replace the final message."
    inputs = _map(case["inputs"])
    inputs.update(monthly_limit_cents=12000, posted_cents=2000, pending_cents=1000)
    original = deepcopy(case)
    report = protocol.evaluate_protocol_case(case)
    assert report["status"] == "scored"
    assert captured == [
        (
            "Current message.",
            [
                {"role": "user", "text": "Earlier user message."},
                {"role": "assistant", "text": "Earlier assistant reply."},
            ],
            date(2026, 9, 1),
            10000,
        )
    ]
    assert case == original


@pytest.mark.parametrize(
    ("constant", "value", "variant", "attempts", "errors", "turns", "revisions"),
    [
        ("MAX_MODEL_TURNS", 7, "unknown_tool", 7, 6, 7, 0),
        ("MAX_MODEL_TURNS", 9, "unknown_tool", 9, 7, None, None),
        ("MAX_PLANNER_REVISIONS", 2, "invalid_planner", 3, 2, 3, 2),
        ("MAX_PLANNER_REVISIONS", 4, "invalid_planner", 5, 3, None, None),
        ("MAX_MODEL_TURNS", 10000, "unknown_tool", 9, 7, None, None),
        ("MAX_PLANNER_REVISIONS", 10000, "invalid_planner", 5, 3, None, None),
    ],
)
def test_changed_limits_fail_with_bounded_actual_attempts(
    constant: str,
    value: int,
    variant: str,
    attempts: int,
    errors: int,
    turns: int | None,
    revisions: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_loop, constant, value)
    report = protocol.evaluate_protocol_case(_case("P04"))
    _assert_labels(report)
    assert report["status"] == "failed"
    assert _map(report["checks"])[variant] is False
    assert _map(report["observed"])[variant] == {
        "outcome": "limit" if turns is not None else "chat_unavailable",
        "model_calls": attempts,
        "rejected_results_observed": errors,
        "no_plan": True,
        "no_answer": True,
        "model_turns": turns,
        "planner_revisions": revisions,
    }
    other = "invalid_planner" if variant == "unknown_tool" else "unknown_tool"
    assert _map(report["checks"])[other] is True
    assert "SYNTHETIC_PROTOCOL_SECRET_SENTINEL" not in json.dumps(report)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("id",), "P01"),
        (("id",), True),
        (("fixture_behavior",), None),
        (("fixture_behavior", "kind"), "bedrock_unavailable"),
        (("fixture_behavior", "kind"), 1),
        (("fixture_behavior", "provider"), "bedrock"),
        (("fixture_behavior", "provider"), True),
        (("requires_model",), False),
        (("requires_model",), 1),
        (("inputs",), None),
        (("inputs", "user_id"), True),
        (("inputs", "user_id"), 2),
        (("inputs", "monthly_limit_cents"), True),
        (("inputs", "posted_cents"), 0.0),
        (("inputs", "pending_cents"), "0"),
        (("inputs", "plan_cap_cents"), False),
        (("inputs", "budget_period"), "2026-09-02"),
        (("inputs", "budget_period"), 1),
        (("inputs", "spending_period"), "not-a-period"),
        (("inputs", "now"), "not-a-clock"),
        (("inputs", "spending_refreshed_at"), None),
        (("inputs", "max_model_turns"), True),
        (("inputs", "max_model_turns"), 9),
        (("inputs", "max_planner_revisions"), 3.0),
        (("messages",), []),
        (("messages",), [{"role": "user", "content": 1}]),
        (("messages",), [{"role": "system", "content": "Message."}]),
        (("messages",), [{"role": "assistant", "content": "Message."}]),
        (("messages",), [{"role": "user", "content": " "}]),
    ],
)
def test_invalid_fixtures_fail_before_provider_attempts(
    path: tuple[str, ...], value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case("P04")
    _replace(case, path, value)
    original = deepcopy(case)
    attempted: list[bool] = []

    def forbidden(
        self: FaultProvider,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        attempted.append(True)
        raise AssertionError("Unexpected provider attempt.")

    monkeypatch.setattr(FaultProvider, "converse", forbidden)
    _assert_unassessed(protocol.evaluate_protocol_case(case))
    assert attempted == []
    assert case == original


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("fixture_behavior", "kind"), "malformed_or_unknown_tool"),
        (("requires_model",), True),
    ],
)
def test_p03_wrong_kind_or_model_flag_is_unassessed(
    path: tuple[str, ...], value: object
) -> None:
    case = _case("P03")
    _replace(case, path, value)
    _assert_unassessed(protocol.evaluate_protocol_case(case))


@pytest.mark.parametrize(
    "path",
    [
        ("id",),
        ("fixture_behavior",),
        ("fixture_behavior", "kind"),
        ("fixture_behavior", "provider"),
        ("requires_model",),
        ("messages",),
        ("inputs",),
        ("inputs", "monthly_limit_cents"),
        ("inputs", "posted_cents"),
        ("inputs", "pending_cents"),
        ("inputs", "plan_cap_cents"),
        ("inputs", "budget_period"),
        ("inputs", "user_id"),
        ("inputs", "now"),
        ("inputs", "spending_refreshed_at"),
        ("inputs", "max_model_turns"),
        ("inputs", "max_planner_revisions"),
    ],
)
def test_missing_fixture_inputs_are_unassessed(path: tuple[str, ...]) -> None:
    case = _case("P04")
    parent = case
    for key in path[:-1]:
        parent = _map(parent[key])
    parent.pop(path[-1])
    _assert_unassessed(protocol.evaluate_protocol_case(case))


@pytest.mark.parametrize(
    "error_type",
    [RuntimeError, TypeError, ValueError, KeyError, LLMUnavailable, Exception],
)
def test_unexpected_exception_text_is_never_exported(
    error_type: type[Exception], monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "SYNTHETIC_UNEXPECTED_ERROR_SENTINEL"

    def broken(
        provider: LLMProvider,
        message: str,
        budget: BudgetResult,
        period: date,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        raise error_type(sentinel)

    monkeypatch.setattr(chat_loop, "run_chat", broken)
    report = protocol.evaluate_protocol_case(_case("P03"))
    _assert_labels(report)
    assert report["status"] == "failed"
    assert report["checks"] == {"unavailable": False}
    assert _map(_map(report["observed"])["unavailable"])["outcome"] == (
        "unexpected_error"
    )
    assert sentinel not in json.dumps(report)


def test_nonstatic_unavailable_exception_cannot_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(
        provider: LLMProvider,
        message: str,
        budget: BudgetResult,
        period: date,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        assert isinstance(provider, FaultProvider)
        provider.calls = 1
        raise chat_loop.ChatUnavailable("SYNTHETIC_SECRET")

    monkeypatch.setattr(chat_loop, "run_chat", broken)
    report = protocol.evaluate_protocol_case(_case("P03"))
    assert report["status"] == "failed"
    assert "SYNTHETIC_SECRET" not in json.dumps(report)


def test_reasoning_blocks_are_not_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    original_converse = FaultProvider.converse
    sentinel = "SYNTHETIC_REASONING_ONLY_SENTINEL"

    def with_reasoning(
        self: FaultProvider,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        response = original_converse(self, system_prompt, messages, tools)
        message = _map(_map(response["output"])["message"])
        blocks = cast(list[dict[str, object]], message["content"])
        blocks.append({"reasoningContent": {"text": sentinel}})
        return response

    monkeypatch.setattr(FaultProvider, "converse", with_reasoning)
    report = protocol.evaluate_protocol_case(_case("P04"))
    assert report["status"] == "scored"
    assert sentinel not in json.dumps(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("answer", "SYNTHETIC_FABRICATED_ANSWER"),
        ("answer", ""),
        ("plan", {"accepted": True, "secret": "SYNTHETIC_SECRET"}),
        ("model_turns", "SYNTHETIC_SECRET"),
        ("planner_revisions", "SYNTHETIC_SECRET"),
        ("model_turns", True),
        ("planner_revisions", True),
    ],
)
def test_limit_results_require_static_answer_no_plan_and_typed_counts(
    field: str, value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_chat = chat_loop.run_chat

    def corrupt(
        provider: LLMProvider,
        message: str,
        budget: BudgetResult,
        period: date,
        *,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, object]:
        result = run_chat(provider, message, budget, period, history=history)
        result[field] = value
        return result

    monkeypatch.setattr(chat_loop, "run_chat", corrupt)
    report = protocol.evaluate_protocol_case(_case("P04"))
    assert report["status"] == "failed"
    assert _map(report["checks"])["unknown_tool"] is False
    assert _map(report["checks"])["invalid_planner"] is False
    assert "SYNTHETIC_" not in json.dumps(report)


def test_p03_returned_answer_cannot_score_as_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "SYNTHETIC_FABRICATED_ANSWER_SENTINEL"

    def answer(
        self: FaultProvider,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls += 1
        message = {"role": "assistant", "content": [{"text": sentinel}]}
        return {"stopReason": "end_turn", "output": {"message": message}}

    monkeypatch.setattr(FaultProvider, "converse", answer)
    report = protocol.evaluate_protocol_case(_case("P03"))
    assert report["status"] == "failed"
    assert report["checks"] == {"unavailable": False}
    actual = _map(_map(report["observed"])["unavailable"])
    assert actual["outcome"] == "unexpected_result"
    assert actual["model_calls"] == 1
    assert actual["no_answer"] is False
    assert sentinel not in json.dumps(report)


def test_missing_rejected_tool_results_cannot_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_converse = FaultProvider.converse

    def hide_errors(
        self: FaultProvider,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        blocks = cast(list[dict[str, object]], messages[-1]["content"])
        for block in blocks:
            result = block.get("toolResult")
            if isinstance(result, dict):
                result["status"] = "success"
        return original_converse(self, system_prompt, messages, tools)

    monkeypatch.setattr(FaultProvider, "converse", hide_errors)
    report = protocol.evaluate_protocol_case(_case("P04"))
    assert report["status"] == "failed"
    for variant in ("unknown_tool", "invalid_planner"):
        assert _map(report["checks"])[variant] is False
        actual = _map(_map(report["observed"])[variant])
        assert actual["rejected_results_observed"] == 0
