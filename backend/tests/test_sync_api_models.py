"""Tests for Plaid sync HTTP body models."""

import pytest
from pydantic import ValidationError

from app.api.sync_models import CreateSyncJobBody

ITEM_ID = "item-1"


def valid_body(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {"item_id": ITEM_ID}
    values.update(overrides)
    return values


def test_create_body_accepts_item_id() -> None:
    body = CreateSyncJobBody.model_validate(valid_body())
    dumped = body.model_dump(mode="json")

    assert body.item_id == ITEM_ID
    assert set(CreateSyncJobBody.model_fields) == {"item_id"}
    assert dumped == {"item_id": ITEM_ID}


def test_create_body_preserves_item_id_text() -> None:
    text = "  item-1  "
    body = CreateSyncJobBody.model_validate(valid_body(item_id=text))

    assert body.item_id == text


@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_create_body_rejects_blank_item_id(value: str) -> None:
    with pytest.raises(ValidationError):
        CreateSyncJobBody.model_validate(valid_body(item_id=value))


def test_create_body_enforces_item_id_length() -> None:
    CreateSyncJobBody.model_validate(valid_body(item_id="x" * 256))
    with pytest.raises(ValidationError):
        CreateSyncJobBody.model_validate(valid_body(item_id="x" * 257))


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "operation",
        "token",
        "access_token",
        "cursor",
        "account",
        "transaction",
        "credentials",
    ],
)
def test_create_body_rejects_forbidden_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        CreateSyncJobBody.model_validate({**valid_body(), field: "secret"})


def test_caller_fields_match_stored_sync_payload() -> None:
    body = CreateSyncJobBody.model_validate(valid_body())
    same = {"operation": "plaid_sync", "item_id": ITEM_ID, "cursor": "x"}
    changed = {"operation": "plaid_sync", "item_id": "item-2"}
    wrong_op = {"operation": "chat", "item_id": ITEM_ID}

    assert body.matches_stored_caller_fields(same) is True
    assert body.matches_stored_caller_fields(changed) is False
    assert body.matches_stored_caller_fields(wrong_op) is False
    assert body.matches_stored_caller_fields("job") is False
    assert body.matches_stored_caller_fields({"item_id": ITEM_ID}) is False
