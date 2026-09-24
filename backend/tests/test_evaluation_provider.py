from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from app.agent.chat_loop import MAX_MODEL_TURNS, ChatUnavailable
from app.agent.provider import LLMUnavailable
from app.evaluation_provider import (
    FAILURE_MARKER,
    STATIC_UNAVAILABLE,
    FakeUnavailableProvider,
    evaluate_provider_case,
)

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
SECRET_MARKER = "FIXTURE_SECRET_MARKER"
FABRICATED_ANSWER = "fabricated-plan-ok"


def _p03() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "P03":
            return row
    raise AssertionError("P03 missing")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def test_converse_raises_marker_and_does_not_retain_payloads() -> None:
    provider = FakeUnavailableProvider()
    prompt = f"{SECRET_MARKER}-prompt"
    payload = [{"role": "user", "content": prompt}]
    with pytest.raises(LLMUnavailable) as caught:
        provider.converse(prompt, payload, [{"name": "t"}])
    assert str(caught.value) == FAILURE_MARKER
    assert provider.calls == 1
    assert prompt not in json.dumps(provider.calls)
    assert not hasattr(provider, "messages")
    assert not hasattr(provider, "system_prompt")
    assert not hasattr(provider, "tools")
    assert list(provider.__slots__) == ["calls"]


def test_p03_bounded_failure_matches_gold() -> None:
    report = evaluate_provider_case(_p03())
    assert report["case_id"] == "P03"
    assert report["evidence_class"] == "deterministic_fake_provider"
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert checks
    assert checks == {
        "accepted": True,
        "outcome": True,
        "fake_answer_forbidden": True,
        "max_model_turns": True,
    }
    assert observed["accepted"] is False
    assert observed["fake_answer"] is False
    assert observed["outcome"] == "bounded_failure"
    assert observed["model_calls"] == 1
    assert observed["sanitized_failure"] is True
    assert observed["max_model_turns"] == 8
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    assert "model_quality" in unassessed
    assert "real_bedrock" in unassessed
    assert "cost" in unassessed
    assert "latency" in unassessed
    assert FAILURE_MARKER not in _blob(report)
    prompt = _p03()["prompt"]
    assert isinstance(prompt, str)
    assert prompt not in _blob(report)


def test_fabricated_run_chat_answer_cannot_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fabricated(
        provider: object,
        message: str,
        budget: object,
        period: object,
        **kwargs: object,
    ) -> dict[str, object]:
        del provider, message, budget, period, kwargs
        return {"answer": FABRICATED_ANSWER, "accepted": False}

    monkeypatch.setattr("app.evaluation_provider.run_chat", _fabricated)
    report = evaluate_provider_case(_p03())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["fake_answer"] is True
    assert observed.get("outcome") != "bounded_failure"
    assert checks["fake_answer_forbidden"] is False
    assert checks["outcome"] is False
    assert not all(value is True for value in checks.values())
    blob = _blob(report)
    assert FABRICATED_ANSWER not in blob
    assert FAILURE_MARKER not in blob


def test_wrong_gold_fails_checks() -> None:
    case = copy.deepcopy(_p03())
    expected = _mapping(case["expected"], "expected")
    expected["accepted"] = True
    expected["allowed_outcomes"] = ["accept_plan"]
    expected["fake_answer_forbidden"] = False
    constraints = _mapping(expected["constraint_results"], "constraint_results")
    constraints["max_model_turns"] = 7
    expected["constraint_results"] = constraints
    case["expected"] = expected
    report = evaluate_provider_case(case)
    checks = _mapping(report["checks"], "checks")
    assert checks["accepted"] is False
    assert checks["outcome"] is False
    assert checks["fake_answer_forbidden"] is False
    assert checks["max_model_turns"] is False


def test_malformed_inputs_do_not_pass_or_leak() -> None:
    case = copy.deepcopy(_p03())
    marker = f"{SECRET_MARKER}-not-a-period"
    inputs = dict(_mapping(case["inputs"], "inputs"))
    inputs["budget_period"] = marker
    inputs["now"] = marker
    case["inputs"] = inputs
    case["prompt"] = {marker: marker}
    report = evaluate_provider_case(case)
    observed = _mapping(report["observed"], "observed")
    checks = _mapping(report["checks"], "checks")
    blob = _blob(report)
    assert observed["outcome"] == "unexpected_error"
    assert checks["outcome"] is False
    assert checks["accepted"] is False
    assert not all(value is True for value in checks.values())
    assert marker not in blob
    assert SECRET_MARKER not in blob
    assert FAILURE_MARKER not in blob
    assert STATIC_UNAVAILABLE not in blob


def test_chained_unavailable_is_not_bounded_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _chained(
        provider: object,
        message: str,
        budget: object,
        period: object,
        **kwargs: object,
    ) -> dict[str, object]:
        del provider, message, budget, period, kwargs
        error = ChatUnavailable(STATIC_UNAVAILABLE)
        error.__cause__ = RuntimeError(FAILURE_MARKER)
        error.__context__ = RuntimeError(SECRET_MARKER)
        raise error

    monkeypatch.setattr("app.evaluation_provider.run_chat", _chained)
    report = evaluate_provider_case(_p03())
    observed = _mapping(report["observed"], "observed")
    checks = _mapping(report["checks"], "checks")
    blob = _blob(report)
    assert observed["outcome"] == "unexpected_error"
    assert observed["sanitized_failure"] is False
    assert observed["accepted"] is False
    assert observed["fake_answer"] is False
    assert checks["outcome"] is False
    assert FAILURE_MARKER not in blob
    assert SECRET_MARKER not in blob
    assert STATIC_UNAVAILABLE not in blob


def test_zero_calls_sanitized_unavailable_is_not_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _zero(
        provider: object,
        message: str,
        budget: object,
        period: object,
        **kwargs: object,
    ) -> dict[str, object]:
        del provider, message, budget, period, kwargs
        raise ChatUnavailable(STATIC_UNAVAILABLE)

    monkeypatch.setattr("app.evaluation_provider.run_chat", _zero)
    report = evaluate_provider_case(_p03())
    observed = _mapping(report["observed"], "observed")
    checks = _mapping(report["checks"], "checks")
    assert observed["model_calls"] == 0
    assert observed["sanitized_failure"] is True
    assert observed["outcome"] != "bounded_failure"
    assert checks["outcome"] is False
    assert checks["max_model_turns"] is False
    assert not all(value is True for value in checks.values())


def test_over_limit_sanitized_unavailable_is_not_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _over(
        provider: object,
        message: str,
        budget: object,
        period: object,
        **kwargs: object,
    ) -> dict[str, object]:
        del message, budget, period, kwargs
        fake = cast(FakeUnavailableProvider, provider)
        fake.calls = MAX_MODEL_TURNS + 1
        raise ChatUnavailable(STATIC_UNAVAILABLE)

    monkeypatch.setattr("app.evaluation_provider.run_chat", _over)
    report = evaluate_provider_case(_p03())
    observed = _mapping(report["observed"], "observed")
    checks = _mapping(report["checks"], "checks")
    assert observed["model_calls"] == MAX_MODEL_TURNS + 1
    assert observed["sanitized_failure"] is True
    assert observed["outcome"] != "bounded_failure"
    assert checks["outcome"] is False
    assert checks["max_model_turns"] is False
    assert not all(value is True for value in checks.values())


def test_report_omits_aggregates() -> None:
    report = evaluate_provider_case(_p03())
    assert "success_score" not in report
    assert "pass_rate" not in report
    assert "metrics_status" not in report
    assert "cost" not in report
    assert "latency" not in report
