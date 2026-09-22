from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from app import evaluation_protocol_observer as observer
from app.agent import chat_loop
from app.domain.budget import BudgetResult
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_protocol_fixture import as_map, period

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _protocol_case() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "P04":
            return row
    raise AssertionError("P04 is missing")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def _context(case: dict[str, object]) -> tuple[str, BudgetResult, date]:
    prompt = case.get("prompt")
    assert type(prompt) is str
    inputs = as_map(case.get("inputs"))
    return prompt, fixture_budget(inputs), period(inputs)


def test_three_baseline_variants() -> None:
    case = _protocol_case()
    prompt, budget, clock = _context(case)
    unknown = observer.observe_variant(case, "unknown", prompt, budget, clock)
    malformed = observer.observe_variant(case, "malformed", prompt, budget, clock)
    planner = observer.observe_variant(case, "planner", prompt, budget, clock)
    assert unknown["outcome"] == "unknown_tool_reject"
    assert unknown["accepted"] is False
    assert unknown["unknown_tool_rejected"] is True
    assert unknown["model_calls"] == 8
    assert unknown["unsupported_results"] == 7
    assert unknown["trace_tools"] == ["unsupported"] * 8
    assert malformed["outcome"] == "malformed_tool_reject"
    assert malformed["accepted"] is False
    assert malformed["protocol_static"] is True
    assert malformed["model_calls"] == 1
    assert planner["outcome"] == "planner_limit"
    assert planner["accepted"] is False
    assert planner["planner_revisions"] == 3
    assert planner["model_calls"] == 4
    assert planner["trace_tools"] == ["plan_groceries"] * 3


def test_changed_model_bound_detects_actual_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _protocol_case()
    prompt, budget, clock = _context(case)
    unknown = observer.observe_variant(case, "unknown", prompt, budget, clock)
    assert unknown["model_calls"] == 8
    monkeypatch.setattr(chat_loop, "MAX_MODEL_TURNS", 5)
    changed = observer.observe_variant(case, "unknown", prompt, budget, clock)
    assert changed["model_calls"] == 5
    assert changed["unsupported_results"] == 4
    assert changed["trace_tools"] == ["unsupported"] * 5
    assert changed["unknown_tool_rejected"] is True
    planner = observer.observe_variant(case, "planner", prompt, budget, clock)
    assert planner["planner_revisions"] == 3
    monkeypatch.setattr(chat_loop, "MAX_PLANNER_REVISIONS", 1)
    limited = observer.observe_variant(case, "planner", prompt, budget, clock)
    assert limited["planner_revisions"] == 1
    assert limited["model_calls"] == 2
    assert limited["trace_tools"] == ["plan_groceries"] * 1
    assert limited["outcome"] == "planner_limit"


def test_unexpected_accepted_result_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = observer.run_chat

    def mutated(
        provider: object,
        prompt: str,
        budget: BudgetResult,
        clock: date,
        **kwargs: object,
    ) -> dict[str, object]:
        del kwargs
        result = real(provider, prompt, budget, clock)
        result["plan"] = {"accepted": True}
        return result

    monkeypatch.setattr(observer, "run_chat", mutated)
    case = _protocol_case()
    prompt, budget, clock = _context(case)
    row = observer.observe_variant(case, "planner", prompt, budget, clock)
    assert row["accepted"] is True
    assert row["outcome"] == "unexpected_error"
    assert "trace_tools" not in row
    assert "planner_revisions" not in row


def test_input_gold_is_unused() -> None:
    case = copy.deepcopy(_protocol_case())
    prompt, budget, clock = _context(case)
    baseline = observer.observe_variant(case, "unknown", prompt, budget, clock)
    gold = _mapping(case.setdefault("expected", {}), "expected")
    gold["accepted"] = True
    gold["allowed_outcomes"] = ["secret_outcome"]
    gold["max_model_turns"] = 1
    observed = observer.observe_variant(case, "unknown", prompt, budget, clock)
    assert observed == baseline
    assert observed["outcome"] == "unknown_tool_reject"
    assert observed["model_calls"] == 8


def test_invalid_fixture_unknown_name_rejects_without_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = copy.deepcopy(_protocol_case())
    behavior = _mapping(case["fixture_behavior"], "fixture_behavior")
    behavior["unknown_tool_name"] = "other_tool"
    calls: list[int] = []

    def blocked(
        provider: object,
        prompt: str,
        budget: BudgetResult,
        clock: date,
        **kwargs: object,
    ) -> dict[str, object]:
        del provider, prompt, budget, clock, kwargs
        calls.append(1)
        raise AssertionError("run_chat")

    monkeypatch.setattr(observer, "run_chat", blocked)
    prompt, budget, clock = _context(_protocol_case())
    row = observer.observe_variant(case, "unknown", prompt, budget, clock)
    assert calls == []
    assert row == {"outcome": "unexpected_error", "accepted": False}
    behavior["unknown_tool_name"] = "not_a_registered_tool"
    behavior["kind"] = "other_kind"
    other = observer.observe_variant(case, "unknown", prompt, budget, clock)
    assert calls == []
    assert other == {"outcome": "unexpected_error", "accepted": False}


def test_secret_marker_does_not_leak() -> None:
    case = copy.deepcopy(_protocol_case())
    _, budget, clock = _context(case)
    marker = f"{SECRET_MARKER}-access_token"
    case["prompt"] = marker
    case["messages"] = marker
    case["metadata"] = marker
    case["expected"] = {marker: marker, "accepted": True}
    inputs = _mapping(case["inputs"], "inputs")
    inputs["credentials"] = marker
    behavior = _mapping(case["fixture_behavior"], "fixture_behavior")
    behavior["secret"] = marker
    behavior["note"] = marker
    malformed = observer.observe_variant(case, "malformed", marker, budget, clock)
    blob = _blob(malformed)
    assert marker not in blob
    assert SECRET_MARKER not in blob
    assert "access_token" not in blob
    assert malformed["outcome"] == "malformed_tool_reject"
    assert malformed["protocol_static"] is True
    behavior["unknown_tool_name"] = marker
    unknown = observer.observe_variant(case, "unknown", marker, budget, clock)
    unknown_blob = _blob(unknown)
    assert marker not in unknown_blob
    assert SECRET_MARKER not in unknown_blob
    assert unknown == {"outcome": "unexpected_error", "accepted": False}
