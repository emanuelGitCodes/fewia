"""Tests for chat HTTP body models and ChatJobInput metadata."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.agent.chat_context import MAX_MESSAGE_LEN
from app.api.chat_models import CreateChatJobBody
from app.services.chat_job import ChatJobInput

PARENT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PERIOD = date(2026, 9, 1)
REFRESHED = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def valid_body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "message": "plan chicken tacos",
        "monthly_limit_cents": 40000,
    }
    values.update(overrides)
    return values


def stored_chat_payload(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "operation": "chat",
        "message": "plan chicken tacos",
        "monthly_limit_cents": 40000,
        "spending": {
            "period": "2026-09-01",
            "posted_cents": 18000,
            "pending_cents": 1200,
            "refreshed_at": "2026-09-02T12:00:00Z",
        },
        "spending_source": "fixture",
        "history": [{"role": "user", "text": "prior"}],
        "previous_request": {
            "meals": [{"recipe_id": "chicken_tacos", "servings": 1}],
            "budget_period": "2026-09-01",
        },
    }
    values.update(overrides)
    return values


def test_create_body_accepts_caller_fields() -> None:
    body = CreateChatJobBody.model_validate(valid_body())
    dumped = body.model_dump(mode="json")

    assert body.message == "plan chicken tacos"
    assert body.monthly_limit_cents == 40000
    assert body.plan_cap_cents is None
    assert body.previous_job_id is None
    assert body.plan_revision_id is None
    assert set(CreateChatJobBody.model_fields) == {
        "message",
        "monthly_limit_cents",
        "plan_cap_cents",
        "previous_job_id",
        "plan_revision_id",
    }
    assert dumped == {
        "message": "plan chicken tacos",
        "monthly_limit_cents": 40000,
        "plan_cap_cents": None,
        "previous_job_id": None,
        "plan_revision_id": None,
    }


def test_create_body_preserves_message_text() -> None:
    text = "  plan chicken tacos\nplease  "
    body = CreateChatJobBody.model_validate(valid_body(message=text))

    assert body.message == text


@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_create_body_rejects_blank_message(value: str) -> None:
    with pytest.raises(ValidationError):
        CreateChatJobBody.model_validate(valid_body(message=value))


def test_create_body_enforces_message_length() -> None:
    CreateChatJobBody.model_validate(valid_body(message="x" * MAX_MESSAGE_LEN))
    too_long = "x" * (MAX_MESSAGE_LEN + 1)
    with pytest.raises(ValidationError):
        CreateChatJobBody.model_validate(valid_body(message=too_long))


@pytest.mark.parametrize("value", [-1, True, 1.5, "100"])
def test_create_body_rejects_invalid_monthly_limit(value: object) -> None:
    with pytest.raises(ValidationError):
        CreateChatJobBody.model_validate(valid_body(monthly_limit_cents=value))


@pytest.mark.parametrize("value", [-1, True, 1.5, "100"])
def test_create_body_rejects_invalid_plan_cap(value: object) -> None:
    with pytest.raises(ValidationError):
        CreateChatJobBody.model_validate(valid_body(plan_cap_cents=value))


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "spending",
        "history",
        "previous_request",
        "operation",
        "token",
        "access_token",
        "credentials",
        "raw_ledger",
    ],
)
def test_create_body_rejects_forbidden_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        CreateChatJobBody.model_validate({**valid_body(), field: 1})


def test_previous_job_id_canonicalizes_uuid() -> None:
    body = CreateChatJobBody.model_validate(
        valid_body(previous_job_id="AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA")
    )

    assert body.previous_job_id == PARENT_ID
    assert body.model_dump(mode="json")["previous_job_id"] == str(PARENT_ID)


def test_previous_job_id_rejects_invalid_uuid() -> None:
    with pytest.raises(ValidationError):
        CreateChatJobBody.model_validate(valid_body(previous_job_id="not-a-uuid"))


def test_matches_stored_caller_fields_ignores_generated_fields() -> None:
    body = CreateChatJobBody.model_validate(valid_body())
    same = stored_chat_payload()
    other_message = stored_chat_payload(message="plan bean tacos")
    other_parent = stored_chat_payload(previous_job_id=str(PARENT_ID))
    bool_limit = stored_chat_payload(monthly_limit_cents=True)
    plan_payload = {
        "request": {"meals": [{"recipe_id": "bean_tacos", "servings": 1}]},
        "monthly_limit_cents": 40000,
        "message": "plan chicken tacos",
    }

    assert body.matches_stored_caller_fields(same) is True
    assert body.matches_stored_caller_fields(other_message) is False
    assert body.matches_stored_caller_fields(other_parent) is False
    assert body.matches_stored_caller_fields(bool_limit) is False
    assert body.matches_stored_caller_fields(plan_payload) is False
    assert body.matches_stored_caller_fields("job") is False


def test_matches_stored_caller_fields_canonicalizes_parent_id() -> None:
    body = CreateChatJobBody.model_validate(valid_body(previous_job_id=PARENT_ID))
    stored = stored_chat_payload(previous_job_id="AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA")

    assert body.matches_stored_caller_fields(stored) is True


def test_matches_stored_plan_cap() -> None:
    body = CreateChatJobBody.model_validate(valid_body(plan_cap_cents=5000))
    stored = stored_chat_payload(plan_cap_cents=5000)
    other = stored_chat_payload(plan_cap_cents=1)

    assert body.matches_stored_caller_fields(stored) is True
    assert body.matches_stored_caller_fields(other) is False


def test_matches_stored_plan_revision_id() -> None:
    revision_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    body = CreateChatJobBody.model_validate(valid_body(plan_revision_id=revision_id))
    same = stored_chat_payload(plan_revision_id=revision_id)
    other = stored_chat_payload(plan_revision_id=str(PARENT_ID))

    assert body.matches_stored_caller_fields(same) is True
    assert body.matches_stored_caller_fields(other) is False
    assert body.matches_stored_caller_fields(stored_chat_payload()) is False


def test_create_body_plan_revision_id_rejects_invalid_uuid() -> None:
    with pytest.raises(ValidationError):
        CreateChatJobBody.model_validate(valid_body(plan_revision_id="not-a-uuid"))


def test_chat_job_input_previous_job_id_defaults_none() -> None:
    parsed = ChatJobInput.model_validate(
        {
            "message": "plan chicken tacos",
            "monthly_limit_cents": 40000,
            "spending": {
                "period": PERIOD,
                "posted_cents": 0,
                "pending_cents": 0,
                "refreshed_at": REFRESHED,
            },
            "spending_source": "fixture",
        }
    )

    assert parsed.previous_job_id is None
    assert parsed.operation == "chat"


def test_chat_job_input_accepts_previous_job_id() -> None:
    parsed = ChatJobInput.model_validate(
        {
            "message": "plan chicken tacos",
            "monthly_limit_cents": 40000,
            "spending": {
                "period": PERIOD,
                "posted_cents": 0,
                "pending_cents": 0,
                "refreshed_at": REFRESHED,
            },
            "spending_source": "fixture",
            "previous_job_id": str(PARENT_ID),
        }
    )

    assert parsed.previous_job_id == PARENT_ID
