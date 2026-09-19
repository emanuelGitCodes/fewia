from datetime import date
from typing import cast

from app.agent.chat_loop import MAX_MODEL_TURNS, ChatUnavailable, run_chat
from app.agent.provider import LLMUnavailable
from app.evaluation_budget import EVIDENCE_CLASS, UNASSESSED
from app.evaluation_budget_inputs import fixture_budget

FAILURE_MARKER = "eval-fake-bedrock-unavailable"
STATIC_UNAVAILABLE = "The language model is unavailable."


class FakeUnavailableProvider:
    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        del system_prompt, messages, tools
        self.calls += 1
        raise LLMUnavailable(FAILURE_MARKER)


def _as_map(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _typed_equal(observed: object, gold: object) -> bool:
    return type(observed) is type(gold) and observed == gold


def _in_turn_limit(calls: object, limit: object) -> bool:
    return type(calls) is int and type(limit) is int and 1 <= calls <= limit


def _period(inputs: dict[str, object]) -> date:
    value = inputs.get("budget_period")
    if type(value) is not str:
        raise TypeError("budget_period is invalid")
    parsed: date | None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None:
        raise TypeError("budget_period is invalid")
    return parsed


def _observe(case: dict[str, object]) -> dict[str, object]:
    provider = FakeUnavailableProvider()
    try:
        inputs = _as_map(case.get("inputs"))
        period = _period(inputs)
        budget = fixture_budget(inputs)
    except Exception:
        return {"outcome": "unexpected_error"}
    raw_prompt = case.get("prompt")
    if type(raw_prompt) is str:
        prompt = raw_prompt
    else:
        return {"outcome": "unexpected_error"}
    try:
        result = run_chat(provider, prompt, budget, period)
    except ChatUnavailable as exc:
        sanitized = (
            str(exc) == STATIC_UNAVAILABLE
            and exc.__cause__ is None
            and exc.__context__ is None
        )
        observed: dict[str, object] = {
            "accepted": False,
            "fake_answer": False,
            "model_calls": provider.calls,
            "sanitized_failure": sanitized,
            "max_model_turns": MAX_MODEL_TURNS,
        }
        if sanitized and _in_turn_limit(provider.calls, MAX_MODEL_TURNS):
            observed["outcome"] = "bounded_failure"
        else:
            observed["outcome"] = "unexpected_error"
        return observed
    except Exception:
        return {
            "outcome": "unexpected_error",
            "model_calls": provider.calls,
            "max_model_turns": MAX_MODEL_TURNS,
        }
    observed = {
        "fake_answer": True,
        "model_calls": provider.calls,
        "max_model_turns": MAX_MODEL_TURNS,
    }
    if isinstance(result, dict):
        accepted = result.get("accepted")
        if type(accepted) is bool:
            observed["accepted"] = accepted
    return observed


def _score(
    observed: dict[str, object], gold: dict[str, object]
) -> tuple[dict[str, bool], dict[str, object]]:
    allowed = gold.get("allowed_outcomes")
    outcome_ok = False
    if isinstance(allowed, list):
        outcome_ok = any(
            _typed_equal(observed.get("outcome"), item) for item in allowed
        )
    constraints = _as_map(gold.get("constraint_results"))
    checks = {
        "accepted": _typed_equal(observed.get("accepted"), gold.get("accepted")),
        "outcome": outcome_ok,
        "fake_answer_forbidden": _typed_equal(
            observed.get("fake_answer") is False, gold.get("fake_answer_forbidden")
        ),
        "max_model_turns": (
            _typed_equal(
                observed.get("max_model_turns"), constraints.get("max_model_turns")
            )
            and _in_turn_limit(
                observed.get("model_calls"), constraints.get("max_model_turns")
            )
        ),
    }
    return checks, dict(observed)


def evaluate_provider_case(case: dict[str, object]) -> dict[str, object]:
    checks, observed = _score(_observe(case), _as_map(case.get("expected")))
    case_id = case.get("id")
    return {
        "case_id": case_id if type(case_id) is str else "invalid_case",
        "checks": checks,
        "observed": observed,
        "unassessed": list(UNASSESSED),
        "evidence_class": EVIDENCE_CLASS,
    }
