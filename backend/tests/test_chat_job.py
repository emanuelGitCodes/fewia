import copy
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.agent.chat_answer import render_public_answer
from app.agent.chat_loop import ChatUnavailable
from app.agent.planning_tool import TOOL_NAME, execute_plan
from app.domain.budget import (
    STALE_SPENDING_ERROR,
    SpendingSnapshot,
    StaleSpendingError,
    calculate_budget,
)
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.services import chat_job as chat_job_module
from app.services.evidence_contract import EvidenceInputs
from app.services.plan_job import SpendingInput

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
PERIOD = date(2026, 9, 1)
_REV = "a" * 64
FACTORY: sessionmaker[Session] = sessionmaker()


def spending(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "period": PERIOD,
        "posted_cents": 2_500,
        "pending_cents": 400,
        "refreshed_at": NOW - timedelta(hours=1),
    }
    values.update(overrides)
    return values


def chat_payload(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "operation": "chat",
        "message": "plan chicken tacos",
        "monthly_limit_cents": 10_000,
        "spending": spending(),
        "spending_source": "fixture",
    }
    result.update(overrides)
    return result


def plan_args() -> dict[str, object]:
    return {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
        "budget_period": PERIOD.isoformat(),
    }


def expected_planning() -> dict[str, object]:
    budget = calculate_budget(
        10_000,
        SpendingSnapshot(PERIOD, 2_500, 400, NOW - timedelta(hours=1)),
        now=NOW,
    )
    return execute_plan(
        plan_args(), budget, PERIOD, user_id=1, spending_source="fixture"
    )


class FakeLLM:
    def __init__(
        self,
        replies: list[dict[str, object] | BaseException],
        before_next: Callable[[], None] | None = None,
    ) -> None:
        self._replies = list(replies)
        self.requests: list[dict[str, object]] = []
        self._before_next = before_next

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        if self.requests and self._before_next is not None:
            self._before_next()
        self.requests.append(
            {
                "system": system_prompt,
                "messages": copy.deepcopy(messages),
                "tools": copy.deepcopy(tools),
            }
        )
        if not self._replies:
            raise AssertionError("unexpected provider call")
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


class FailLLM:
    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        del system_prompt, messages, tools
        raise AssertionError("provider must not run")


def _reply(content: list[dict[str, object]], stop: str) -> dict[str, object]:
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
        "usage": {"inputTokens": 1, "outputTokens": 1},
    }


def _planner_then_final() -> list[dict[str, object] | BaseException]:
    return [
        _reply(
            [
                {
                    "toolUse": {
                        "toolUseId": "call-1",
                        "name": TOOL_NAME,
                        "input": plan_args(),
                    }
                }
            ],
            "tool_use",
        ),
        _reply([{"text": "Here is a labeled estimate."}], "end_turn"),
    ]


def _patch_save(
    monkeypatch: pytest.MonkeyPatch, saved: list[dict[str, object]]
) -> None:
    def fake_save(
        factory: sessionmaker[Session],
        user_id: int,
        planning: dict[str, object],
        inputs: EvidenceInputs,
    ) -> str:
        assert factory is FACTORY
        assert user_id == 1
        saved.append({"planning": dict(planning), "inputs": inputs})
        return _REV

    monkeypatch.setattr(chat_job_module, "save_plan_evidence", fake_save)


def test_chat_job_plan_then_final_and_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)
    saved: list[dict[str, object]] = []
    _patch_save(monkeypatch, saved)
    expected = expected_planning()
    provider = FakeLLM(_planner_then_final())

    result = chat_job_module.chat_job(
        chat_payload(), lambda: None, provider=provider, factory=FACTORY
    )
    public_answer = render_public_answer(expected)

    assert result["status"] == "planned"
    assert result["answer"] == public_answer
    assert "USD $23.73" in str(result["answer"])
    assert "USD $75.00" in str(result["answer"])
    assert SAMPLE_ESTIMATE_NOTICE in str(result["answer"])
    assert "Here is a labeled estimate." not in str(result["answer"])
    assert result["plan"] == expected["plan"]
    assert result["request"] == expected["request"]
    assert result["evidence_id"] == expected["evidence_id"]
    assert result["evidence_revision_id"] == _REV
    assert result["plan"] is not None
    assert saved[0]["planning"] == expected
    inputs = saved[0]["inputs"]
    assert isinstance(inputs, EvidenceInputs)
    assert inputs.calculated_at == NOW
    assert inputs.spending == SpendingInput.model_validate(spending())

    follow_provider = FakeLLM(_planner_then_final())
    follow = chat_job_module.chat_job(
        chat_payload(
            message="use the same meals",
            previous_request={
                "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
                "budget_period": PERIOD,
            },
            history=[
                {"role": "user", "text": "plan chicken tacos"},
                {"role": "assistant", "text": str(result["answer"])},
            ],
        ),
        lambda: None,
        provider=follow_provider,
        factory=FACTORY,
    )
    assert follow["status"] == "planned"
    first_messages = follow_provider.requests[0]["messages"]
    assert isinstance(first_messages, list)
    assert first_messages[0]["role"] == "user"
    assert first_messages[1]["role"] == "assistant"


def test_chat_job_stores_snapshot_before_next_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)
    saved: list[dict[str, object]] = []
    _patch_save(monkeypatch, saved)

    def require_store() -> None:
        assert saved

    provider = FakeLLM(_planner_then_final(), before_next=require_store)
    result = chat_job_module.chat_job(
        chat_payload(), lambda: None, provider=provider, factory=FACTORY
    )
    assert result["status"] == "planned"
    assert len(provider.requests) == 2
    assert len(saved) == 1


def test_chat_job_clarification_has_no_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)

    def boom_save(
        factory: sessionmaker[Session],
        user_id: int,
        planning: dict[str, object],
        inputs: EvidenceInputs,
    ) -> str:
        del factory, user_id, planning, inputs
        raise AssertionError("store must not run")

    monkeypatch.setattr(chat_job_module, "save_plan_evidence", boom_save)
    provider = FakeLLM([_reply([{"text": "How many servings?"}], "end_turn")])
    result = chat_job_module.chat_job(
        chat_payload(), lambda: None, provider=provider, factory=FACTORY
    )
    assert result["status"] == "clarification"
    assert result["plan"] is None
    assert result["evidence_id"] is None
    assert result["evidence_revision_id"] is None


def test_chat_job_rejects_extra_and_user_id_before_provider() -> None:
    provider = FailLLM()
    with pytest.raises(ValidationError):
        chat_job_module.chat_job(
            chat_payload(user_id=1),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )
    with pytest.raises(ValidationError):
        chat_job_module.chat_job(
            chat_payload(token="secret"),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )
    with pytest.raises(ValidationError):
        chat_job_module.chat_job(
            chat_payload(raw_ledger=[{"id": "tx-1"}]),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )


def test_chat_job_stale_cap_and_period(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)
    provider = FailLLM()
    stale = spending(refreshed_at=NOW - timedelta(hours=25))
    with pytest.raises(StaleSpendingError, match=STALE_SPENDING_ERROR):
        chat_job_module.chat_job(
            chat_payload(spending=stale),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )
    with pytest.raises(ValueError, match="current New York month"):
        chat_job_module.chat_job(
            chat_payload(spending=spending(period=date(2026, 8, 1))),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )
    saved: list[dict[str, object]] = []
    _patch_save(monkeypatch, saved)
    ok_provider = FakeLLM(_planner_then_final())
    result = chat_job_module.chat_job(
        chat_payload(spending=stale, plan_cap_cents=5_000),
        lambda: None,
        provider=ok_provider,
        factory=FACTORY,
    )
    assert result["status"] in {"planned", "needs_revision"}
    assert result["plan"] is not None


def _job_context(provider: FakeLLM) -> dict[str, object]:
    first = provider.requests[0]["messages"]
    assert isinstance(first, list)
    last = first[-1]
    assert isinstance(last, dict)
    content = last["content"]
    assert isinstance(content, list)
    block = content[0]
    assert isinstance(block, dict)
    text = block["text"]
    assert isinstance(text, str)
    loaded: object = json.loads(text)
    assert isinstance(loaded, dict)
    return {str(key): value for key, value in loaded.items()}


def test_chat_job_passes_explicit_plan_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)
    saved: list[dict[str, object]] = []
    _patch_save(monkeypatch, saved)
    provider = FakeLLM(_planner_then_final())
    payload = chat_payload(plan_cap_cents=20_000)
    original = copy.deepcopy(payload)
    result = chat_job_module.chat_job(
        payload, lambda: None, provider=provider, factory=FACTORY
    )
    assert result["status"] in {"planned", "needs_revision"}
    context = _job_context(provider)
    assert context["plan_cap_cents"] == 20_000
    budget_payload = context["budget"]
    assert isinstance(budget_payload, dict)
    expected_budget = calculate_budget(
        10_000,
        SpendingSnapshot(PERIOD, 2_500, 400, NOW - timedelta(hours=1)),
        now=NOW,
        plan_cap_cents=20_000,
    )
    assert budget_payload["available_cents"] == expected_budget.available_cents
    assert budget_payload["available_cents"] == 7_500
    inputs = saved[0]["inputs"]
    assert isinstance(inputs, EvidenceInputs)
    assert inputs.plan_cap_cents == 20_000
    assert payload == original
    last = provider.requests[0]["messages"]
    assert isinstance(last, list)
    content = last[-1]["content"]
    assert isinstance(content, list)
    assert content[-1] == {"text": "plan chicken tacos"}


def test_chat_job_preserves_cap_zero_one_and_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)
    saved: list[dict[str, object]] = []
    _patch_save(monkeypatch, saved)
    cases = (
        (0, 0),
        (1, 1),
        (None, 7_500),
    )
    for cap, available in cases:
        saved.clear()
        payload = chat_payload() if cap is None else chat_payload(plan_cap_cents=cap)
        provider = FakeLLM(_planner_then_final())
        chat_job_module.chat_job(
            payload, lambda: None, provider=provider, factory=FACTORY
        )
        context = _job_context(provider)
        assert context["plan_cap_cents"] == cap
        budget_payload = context["budget"]
        assert isinstance(budget_payload, dict)
        assert budget_payload["available_cents"] == available
        inputs = saved[0]["inputs"]
        assert isinstance(inputs, EvidenceInputs)
        assert inputs.plan_cap_cents == cap


def test_chat_job_rejects_invalid_plan_cap_before_provider() -> None:
    provider = FailLLM()
    with pytest.raises(ValidationError):
        chat_job_module.chat_job(
            chat_payload(plan_cap_cents=-1),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )
    with pytest.raises(ValidationError):
        chat_job_module.chat_job(
            chat_payload(plan_cap_cents=True),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )
    with pytest.raises(ValidationError):
        chat_job_module.chat_job(
            chat_payload(plan_cap_cents="1"),
            lambda: None,
            provider=provider,
            factory=FACTORY,
        )


def test_chat_job_omits_raw_ledger_from_model_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)
    saved: list[dict[str, object]] = []
    _patch_save(monkeypatch, saved)
    provider = FakeLLM(_planner_then_final())
    chat_job_module.chat_job(
        chat_payload(), lambda: None, provider=provider, factory=FACTORY
    )
    dumped = json.dumps(provider.requests)
    for token in (
        "posted_cents",
        "refreshed_at",
        "raw_ledger",
        "transactions",
        "access_token",
        "account_id",
    ):
        assert token not in dumped


def test_chat_job_provider_failure_stays_static(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)
    provider = FakeLLM([RuntimeError("bedrock-secret")])
    with pytest.raises(ChatUnavailable, match="unavailable") as caught:
        chat_job_module.chat_job(
            chat_payload(), lambda: None, provider=provider, factory=FACTORY
        )
    assert "bedrock-secret" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_chat_job_recorder_failure_skips_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)

    def boom_save(
        factory: sessionmaker[Session],
        user_id: int,
        planning: dict[str, object],
        inputs: EvidenceInputs,
    ) -> str:
        del factory, user_id, planning, inputs
        raise RuntimeError("store-failed")

    monkeypatch.setattr(chat_job_module, "save_plan_evidence", boom_save)
    provider = FakeLLM(_planner_then_final())
    with pytest.raises(RuntimeError, match="store-failed") as caught:
        chat_job_module.chat_job(
            chat_payload(), lambda: None, provider=provider, factory=FACTORY
        )
    assert caught.value.__cause__ is None
    assert len(provider.requests) == 1


def test_chat_job_heartbeat_failure_is_before_provider() -> None:
    def heartbeat() -> None:
        raise RuntimeError("heartbeat-lost")

    with pytest.raises(RuntimeError, match="heartbeat-lost"):
        chat_job_module.chat_job(
            chat_payload(), heartbeat, provider=FailLLM(), factory=FACTORY
        )
