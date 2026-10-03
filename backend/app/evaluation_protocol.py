from datetime import date
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from app.agent import chat_loop
from app.agent.chat_messages import ChatProtocolError
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_fault_provider import (
    PROTOCOL_VARIANTS,
    UNAVAILABLE_VARIANTS,
    FaultProvider,
)


class _Inputs(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: int
    monthly_limit_cents: int
    posted_cents: int
    pending_cents: int
    plan_cap_cents: int | None
    budget_period: str
    now: str
    spending_refreshed_at: str
    spending_period: str | None = None
    max_model_turns: int | None = None
    max_planner_revisions: int | None = None


class _Case(BaseModel):
    model_config = ConfigDict(strict=True)
    id: Literal["P03", "P04"]
    requires_model: bool
    fixture_behavior: dict[str, str]
    inputs: _Inputs
    messages: list[dict[str, str]]


def evaluate_protocol_case(case: dict[str, object]) -> dict[str, object]:
    report: dict[str, object] = {
        "case_id": "invalid_case",
        "status": "unassessed",
        "reason": "invalid_case",
        "checks": {},
        "observed": {},
        "evidence_class": "deterministic_fake_provider",
        "controlled_fault": True,
        "model_quality_applicable": False,
        "scope": "P04 requires_model is true. Forced faults exclude model quality.",
    }
    try:
        data = _Case.model_validate(case)
        report["case_id"] = data.id
        inputs = data.inputs.model_dump(exclude_unset=True)
        fixture, messages = data.fixture_behavior, data.messages
        kind = "bedrock_unavailable"
        fixed = {"user_id": 1}
        if data.id == "P04":
            kind = "malformed_or_unknown_tool"
            fixed.update(
                max_model_turns=PROTOCOL_VARIANTS["unknown_tool"][0],
                max_planner_revisions=PROTOCOL_VARIANTS["invalid_planner"][1],
            )
        valid = (
            fixture.get("kind") == kind
            and fixture.get("provider") == "fake"
            and data.requires_model == (data.id == "P04")
            and bool(messages)
            and messages[-1].get("role") == "user"
            and all(m.get("role") in {"user", "assistant"} for m in messages)
            and all(m.get("content", "").strip() for m in messages)
            and all(type(inputs[k]) is int and inputs[k] == v for k, v in fixed.items())
        )
        if not valid:
            return report
        budget = fixture_budget(inputs)
        period = date.fromisoformat(cast(str, inputs["budget_period"]))
        if period.day != 1:
            return report
    except (KeyError, TypeError, ValueError):
        return report
    history = [{"role": m["role"], "text": m["content"]} for m in messages[:-1]]
    variants = PROTOCOL_VARIANTS if data.id == "P04" else UNAVAILABLE_VARIANTS
    observed: dict[str, object] = {}
    checks: dict[str, bool] = {}
    for variant, (calls, revisions, outcome) in variants.items():
        provider = FaultProvider(variant, calls)
        result: dict[str, object] = {}
        code = "unexpected_error"
        try:
            result = chat_loop.run_chat(
                provider, messages[-1]["content"], budget, period, history=history
            )
        except chat_loop.ChatUnavailable as exc:
            if exc.args == ("The language model is unavailable.",):
                code = "chat_unavailable"
        except ChatProtocolError:
            code = "chat_protocol_error"
        except Exception:  # noqa: BLE001
            pass
        else:
            code = "limit" if result.get("status") == "limit" else "unexpected_result"
        turns, changes = result.get("model_turns"), result.get("planner_revisions")
        no_answer = (
            result.get("answer") == "The job reached a processing limit."
            if code == "limit"
            else not bool(result.get("answer"))
        )
        actual = {
            "outcome": code,
            "model_calls": provider.calls,
            "rejected_results_observed": provider.errors,
            "no_plan": result.get("plan") is None,
            "no_answer": no_answer,
            "model_turns": turns if type(turns) is int else None,
            "planner_revisions": changes if type(changes) is int else None,
        }
        observed[variant] = actual
        checks[variant] = (
            code == outcome
            and actual["no_plan"] is True
            and no_answer
            and provider.calls == calls
            and provider.errors == (0 if variant == "unavailable" else calls - 1)
        )
        if outcome == "limit":
            checks[variant] &= (
                type(turns) is int
                and type(changes) is int
                and (turns, changes) == (calls, revisions)
            )
    report.update(reason="controlled_fault_guards", checks=checks, observed=observed)
    report["status"] = "scored" if checks and all(checks.values()) else "failed"
    return report
