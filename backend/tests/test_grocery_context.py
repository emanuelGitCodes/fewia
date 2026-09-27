"""Tests for shared grocery spending input."""

import os
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.domain.budget import NEW_YORK, SpendingSnapshot
from app.services.grocery_context import (
    FIXTURE_PENDING_CENTS,
    FIXTURE_POSTED_CENTS,
    SpendingUnavailable,
    spending_input,
)

FIXED_NY = datetime(2026, 9, 6, 12, 0, tzinfo=NEW_YORK)
UTC_SEPTEMBER_START = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)
SANDBOX_REFRESH = datetime(2026, 9, 2, 15, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clear_fewia_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


def test_fixture_uses_constants_and_current_new_york_month(
    session: Session,
) -> None:
    result = spending_input(session, 1, "fixture", FIXED_NY)

    assert result.period == date(2026, 9, 1)
    assert result.posted_cents == FIXTURE_POSTED_CENTS
    assert result.pending_cents == FIXTURE_PENDING_CENTS
    assert result.posted_cents == 18000
    assert result.pending_cents == 1200
    assert result.refreshed_at == FIXED_NY.astimezone(UTC)


def test_fixture_period_follows_new_york_from_utc(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> SpendingSnapshot:
        raise AssertionError("fixture mode MUST NOT load ledger spending")

    monkeypatch.setattr("app.services.grocery_context.load_spending", boom)
    result = spending_input(session, 1, "fixture", UTC_SEPTEMBER_START)

    assert UTC_SEPTEMBER_START.astimezone(NEW_YORK).date() == date(2026, 8, 31)
    assert result.period == date(2026, 8, 1)
    assert result.posted_cents == FIXTURE_POSTED_CENTS
    assert result.pending_cents == FIXTURE_PENDING_CENTS


def test_sandbox_copies_normalized_ledger_fields(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[object, object, object]] = []
    snapshot = SpendingSnapshot(
        period=date(2026, 9, 1),
        posted_cents=321,
        pending_cents=45,
        refreshed_at=SANDBOX_REFRESH,
    )

    def load(db: Session, user_id: int, period: date) -> SpendingSnapshot:
        calls.append((db, user_id, period))
        return snapshot

    monkeypatch.setattr("app.services.grocery_context.load_spending", load)
    result = spending_input(session, 7, "plaid_sandbox", FIXED_NY)

    assert calls == [(session, 7, date(2026, 9, 1))]
    assert result.period == snapshot.period
    assert result.posted_cents == 321
    assert result.pending_cents == 45
    assert result.refreshed_at == SANDBOX_REFRESH
    assert result.posted_cents != FIXTURE_POSTED_CENTS
    assert result.pending_cents != FIXTURE_PENDING_CENTS


def test_sandbox_missing_data_does_not_fall_back(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_args: object, **_kwargs: object) -> SpendingSnapshot:
        raise SpendingUnavailable()

    monkeypatch.setattr("app.services.grocery_context.load_spending", missing)
    with pytest.raises(SpendingUnavailable) as exc_info:
        spending_input(session, 1, "plaid_sandbox", FIXED_NY)

    assert str(exc_info.value) == "Spending is unavailable"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_sandbox_zero_totals_stay_ledger_values(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = SpendingSnapshot(
        period=date(2026, 9, 1),
        posted_cents=0,
        pending_cents=0,
        refreshed_at=SANDBOX_REFRESH,
    )
    monkeypatch.setattr(
        "app.services.grocery_context.load_spending",
        lambda *_args, **_kwargs: snapshot,
    )
    result = spending_input(session, 1, "plaid_sandbox", FIXED_NY)

    assert result.posted_cents == 0
    assert result.pending_cents == 0
    assert result.refreshed_at == SANDBOX_REFRESH


def test_manual_returns_zero_cost_and_rejects_naive_time(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> SpendingSnapshot:
        raise AssertionError("manual mode MUST NOT load ledger spending")

    monkeypatch.setattr("app.services.grocery_context.load_spending", boom)
    result = spending_input(session, 1, "manual", FIXED_NY)
    naive = datetime(2026, 9, 6, 12, 0)

    assert result.period == date(2026, 9, 1)
    assert result.posted_cents == 0
    assert result.pending_cents == 0
    assert result.refreshed_at == FIXED_NY.astimezone(UTC)
    with pytest.raises(ValueError, match="timezone-aware"):
        spending_input(session, 1, "manual", naive)


def test_rejects_naive_current_time(session: Session) -> None:
    naive = datetime(2026, 9, 6, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        spending_input(session, 1, "fixture", naive)


@pytest.mark.parametrize(
    "source",
    ["live", "plaid", "sandbox", "FIXTURE", "plaid_live", ""],
)
def test_unknown_source_is_unavailable_before_ledger(
    session: Session, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    def boom(*_args: object, **_kwargs: object) -> SpendingSnapshot:
        raise AssertionError("unknown source MUST NOT load ledger spending")

    monkeypatch.setattr("app.services.grocery_context.load_spending", boom)
    with pytest.raises(SpendingUnavailable) as exc_info:
        spending_input(session, 1, source, FIXED_NY)

    assert str(exc_info.value) == "Spending is unavailable"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
