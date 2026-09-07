"""Test shared shopping-list handoff contract helpers."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.handoff_models import ShoppingHandoff
from app.services.handoff_contract import (
    INVALID_CACHED_URL,
    PAYLOAD_MISMATCH,
    HandoffNotFound,
    HandoffView,
    _canonical_json,
    _view,
    is_handoff_unique_conflict,
    validated_cached_payload,
)
from app.services.shopping_payload import shopping_payload_hash

NOW = datetime(2026, 9, 6, 15, 0, tzinfo=UTC)
SUCCESS_URL = "https://www.instacart.com/store/lists/demo"
UNSAFE_URL = "https://example.com/store/lists/demo"
SENTINEL = "SECRET_DB_TOKEN"
UNIQUE_NAME = "uq_shopping_handoffs_user_request_hash"


def shopping_payload(quantity: object = 240) -> dict[str, object]:
    return {
        "title": "FEWIA grocery plan",
        "link_type": "shopping_list",
        "expires_in": 7,
        "line_items": [
            {
                "name": "black beans",
                "line_item_measurements": [{"quantity": quantity, "unit": "g"}],
            }
        ],
    }


def assert_static(error: BaseException, message: str) -> None:
    assert str(error) == message
    assert error.__cause__ is None
    assert error.__context__ is None
    assert SENTINEL not in str(error)
    assert SENTINEL not in repr(error)


def make_succeeded(url: str | None) -> ShoppingHandoff:
    row = ShoppingHandoff(
        user_id=1, request_hash="cached-hash", request_payload=shopping_payload()
    )
    row.id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    row.state = "succeeded"
    row.attempts = 1
    row.started_at = NOW
    row.expires_at = NOW + timedelta(days=7)
    row.url = url
    return row


class _Diag:
    def __init__(self, name: object) -> None:
        self.constraint_name = name


class _PgError(Exception):
    def __init__(self, sqlstate: object, name: object, pgcode: object = None) -> None:
        super().__init__(SENTINEL)
        self.sqlstate = sqlstate
        self.pgcode = pgcode
        self.diag = _Diag(name)


class _SqliteError(Exception):
    def __init__(self, code: object) -> None:
        super().__init__(SENTINEL)
        self.sqlite_errorcode = code


def test_view_fields_and_missing_handoff() -> None:
    assert set(HandoffView.__dataclass_fields__) == {
        "id",
        "state",
        "attempts",
        "url",
        "error_code",
        "expires_at",
        "retry_allowed",
    }
    assert HandoffView.__dataclass_params__.frozen is True
    assert str(HandoffNotFound()) == "shopping handoff is missing"


def test_validated_payload_rejects_true_for_one() -> None:
    digest = shopping_payload_hash(shopping_payload())
    payload = shopping_payload(True)
    items = payload["line_items"]
    assert isinstance(items, list)
    line = items[0]
    assert isinstance(line, dict)
    measures = line["line_item_measurements"]
    assert isinstance(measures, list)
    measure = measures[0]
    assert isinstance(measure, dict)
    assert measure["quantity"] is True
    with pytest.raises(ValueError) as raised:
        validated_cached_payload(payload, digest)
    assert_static(raised.value, PAYLOAD_MISMATCH)


def test_validated_payload_rejects_hash_mismatch() -> None:
    payload = shopping_payload(241)
    digest = shopping_payload_hash(shopping_payload())
    with pytest.raises(ValueError) as raised:
        validated_cached_payload(payload, digest)
    assert_static(raised.value, PAYLOAD_MISMATCH)


def test_validated_payload_returns_json_copy() -> None:
    payload = shopping_payload()
    digest = shopping_payload_hash(payload)
    copied = validated_cached_payload(payload, digest)
    payload["title"] = "mutated"
    assert copied["title"] == "FEWIA grocery plan"
    assert copied == shopping_payload()


def test_canonical_json_distinguishes_true_and_one() -> None:
    as_true = shopping_payload(True)
    as_one = shopping_payload(1)
    assert as_true == as_one
    assert _canonical_json(as_true) != _canonical_json(as_one)


def test_unsafe_cached_url_is_not_returned() -> None:
    row = make_succeeded(UNSAFE_URL)
    view = _view(row, NOW)
    assert view.url is None
    assert view.state == "uncertain"
    assert view.error_code == INVALID_CACHED_URL
    assert view.retry_allowed is True
    assert row.url is None
    assert row.state == "uncertain"
    assert row.request_payload == shopping_payload()


def test_missing_success_url_is_not_invented() -> None:
    row = make_succeeded(None)
    view = _view(row, NOW)
    assert view.url is None
    assert view.state == "uncertain"
    assert view.error_code == INVALID_CACHED_URL
    assert view.retry_allowed is True


def test_expired_url_is_hidden_not_invented() -> None:
    row = make_succeeded(SUCCESS_URL)
    row.expires_at = NOW - timedelta(seconds=1)
    view = _view(row, NOW)
    assert view.state == "succeeded"
    assert view.url is None
    assert view.retry_allowed is True
    assert view.expires_at is None
    assert row.url == SUCCESS_URL


def test_safe_success_url_is_returned() -> None:
    row = make_succeeded(SUCCESS_URL)
    view = _view(row, NOW)
    assert view.state == "succeeded"
    assert view.url == SUCCESS_URL
    assert view.retry_allowed is False


def test_pg_unique_sqlstate_and_constraint() -> None:
    error = IntegrityError("INSERT", {}, _PgError("23505", UNIQUE_NAME))
    assert is_handoff_unique_conflict(error) is True


def test_pg_unique_pgcode_and_constraint() -> None:
    error = IntegrityError("INSERT", {}, _PgError(None, UNIQUE_NAME, "23505"))
    assert is_handoff_unique_conflict(error) is True


def test_pg_unique_wrong_constraint_is_false() -> None:
    error = IntegrityError("INSERT", {}, _PgError("23505", "users_pkey"))
    assert is_handoff_unique_conflict(error) is False


def test_sqlite_unique_code_is_true() -> None:
    error = IntegrityError("INSERT", {}, _SqliteError(sqlite3.SQLITE_CONSTRAINT_UNIQUE))
    assert is_handoff_unique_conflict(error) is True


def test_sqlite_foreign_key_code_is_false() -> None:
    error = IntegrityError(
        "INSERT", {}, _SqliteError(sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY)
    )
    assert is_handoff_unique_conflict(error) is False


def test_raw_integrity_error_sentinel_is_not_unique() -> None:
    error = IntegrityError("INSERT", {}, Exception(SENTINEL))
    assert is_handoff_unique_conflict(error) is False
    assert SENTINEL in str(error.orig)
