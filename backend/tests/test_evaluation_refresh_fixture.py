from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ResourceClosedError

from app.evaluation_budget_inputs import CENTS_ERROR, CLOCK_ERROR, _parse_clock
from app.evaluation_refresh_fixture import (
    INPUT_ERROR,
    ITEM_ID,
    FakeUnavailableSyncProvider,
    fixture,
)
from app.models import User
from app.plaid_models import PlaidItem, PlaidTransaction
from app.providers.plaid import PlaidUnavailable
from app.services.ledger_budget import load_spending

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
DRIVER_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "evaluation_refresh_fixture.py"
)
SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _p01_inputs() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "P01":
            inputs = row["inputs"]
            assert isinstance(inputs, dict)
            return cast(dict[str, object], inputs)
    raise AssertionError("P01 missing")


def _assert_static(exc: BaseException, message: str, raw: str) -> None:
    assert type(exc) is TypeError
    assert exc.args == (message,)
    assert exc.__context__ is None
    assert exc.__cause__ is None
    assert raw not in str(exc)
    assert raw not in repr(exc)
    assert SECRET_MARKER not in str(exc)
    assert SECRET_MARKER not in repr(exc)


def test_fk_seeding_and_ledger_totals() -> None:
    inputs = dict(_p01_inputs())
    inputs["posted_cents"] = 12000
    inputs["pending_cents"] = 4000
    with fixture(inputs) as ctx:
        with ctx.session_factory() as session:
            flags = session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar()
            user = session.get(User, ctx.user_id)
            item = session.get(PlaidItem, ITEM_ID)
            posted = session.get(PlaidTransaction, (ITEM_ID, "eval-posted"))
            pending = session.get(PlaidTransaction, (ITEM_ID, "eval-pending"))
            spending = load_spending(session, ctx.user_id, ctx.period)
            with pytest.raises(IntegrityError):
                with session.begin_nested():
                    session.add(
                        PlaidTransaction(
                            item_id="missing-item-id-000000000000000000001",
                            transaction_id="orphan",
                            account_id="eval-account",
                            amount_cents=1,
                            currency="USD",
                            transaction_date=ctx.period,
                            pending=False,
                            pending_transaction_id=None,
                            is_grocery=True,
                            classification_version="eval-v1",
                        )
                    )
        assert flags == 1
        assert user is not None
        assert item is not None
        assert item.user_id == ctx.user_id
        assert posted is not None
        assert pending is not None
        assert posted.pending is False
        assert pending.pending is True
        assert posted.amount_cents == 12000
        assert pending.amount_cents == 4000
        assert spending.posted_cents == 12000
        assert spending.pending_cents == 4000
        assert ctx.posted == 12000
        assert ctx.pending == 4000
        assert ctx.limit == 10000
        assert ctx.plan_cap is None


def test_snapshot_state() -> None:
    inputs = _p01_inputs()
    stamp = inputs["spending_refreshed_at"]
    assert type(stamp) is str
    with fixture(inputs) as ctx:
        cursor, last_synced = ctx.read_state()
        assert cursor == f"eval-cursor:{stamp}"
        assert last_synced is not None
        if last_synced.tzinfo is None:
            last_synced = last_synced.replace(tzinfo=UTC)
        else:
            last_synced = last_synced.astimezone(UTC)
        assert last_synced == _parse_clock(stamp)
        assert ctx.user_id == 1
        assert str(ctx.period) == "2026-09-01"
        assert ctx.clock == _parse_clock(inputs["now"])
        with ctx.session_factory() as session:
            posted = session.get(PlaidTransaction, (ITEM_ID, "eval-posted"))
            pending = session.get(PlaidTransaction, (ITEM_ID, "eval-pending"))
            spending = load_spending(session, ctx.user_id, ctx.period)
        assert posted is not None
        assert pending is not None
        assert ctx.posted == 0
        assert ctx.pending == 0
        assert spending.posted_cents == 0
        assert spending.pending_cents == 0


def test_isolated_repeats() -> None:
    other = dict(_p01_inputs())
    other["posted_cents"] = 12000
    other["pending_cents"] = 4000
    with fixture(_p01_inputs()) as first, fixture(other) as second:
        with first.session_factory() as session:
            left = load_spending(session, first.user_id, first.period)
        with second.session_factory() as session:
            right = load_spending(session, second.user_id, second.period)
        assert first.read_state()[0] == second.read_state()[0]
        assert left.posted_cents == 0
        assert left.pending_cents == 0
        assert right.posted_cents == 12000
        assert right.pending_cents == 4000
    with fixture(_p01_inputs()) as third:
        with third.session_factory() as session:
            again = load_spending(session, third.user_id, third.period)
        assert again.posted_cents == 0
        assert again.pending_cents == 0


def test_invalid_input_raises_only_static_error() -> None:
    base = _p01_inputs()
    bad_user = f"{SECRET_MARKER}-user"
    payload: dict[str, object] = dict(base)
    payload["user_id"] = bad_user
    with pytest.raises(TypeError) as user_error:
        with fixture(payload):
            raise AssertionError("must not enter")
    _assert_static(user_error.value, INPUT_ERROR, bad_user)

    bad_clock = f"{SECRET_MARKER}-not-a-clock"
    payload = dict(base)
    payload["now"] = bad_clock
    with pytest.raises(TypeError) as clock_error:
        with fixture(payload):
            raise AssertionError("must not enter")
    _assert_static(clock_error.value, CLOCK_ERROR, bad_clock)

    bad_cents = f"{SECRET_MARKER}-cents"
    payload = dict(base)
    payload["posted_cents"] = bad_cents
    with pytest.raises(TypeError) as cents_error:
        with fixture(payload):
            raise AssertionError("must not enter")
    _assert_static(cents_error.value, CENTS_ERROR, bad_cents)

    with pytest.raises(TypeError) as mapping_error:
        with fixture(cast(dict[str, object], SECRET_MARKER)):
            raise AssertionError("must not enter")
    _assert_static(mapping_error.value, INPUT_ERROR, SECRET_MARKER)


def test_cleanup_disposes_engine() -> None:
    with fixture(_p01_inputs()) as ctx:
        factory = ctx.session_factory
        with factory() as session:
            assert session.get(PlaidItem, ITEM_ID) is not None
    with pytest.raises((OperationalError, ResourceClosedError)):
        with factory() as session:
            session.get(PlaidItem, ITEM_ID)


def test_fake_provider_raises_plaid_unavailable_and_increments() -> None:
    provider = FakeUnavailableSyncProvider()
    assert provider.calls == 0
    with pytest.raises(PlaidUnavailable) as first:
        provider.sync_page("eval-refresh-credential-ref", None)
    assert first.value.__context__ is None
    assert provider.calls == 1
    with pytest.raises(PlaidUnavailable) as second:
        provider.sync_page("eval-refresh-credential-ref", "eval-cursor")
    assert second.value.__context__ is None
    assert provider.calls == 2
    assert "access_token" not in str(first.value)
    assert SECRET_MARKER not in str(second.value)


def test_module_stays_local_without_credentials() -> None:
    text = DRIVER_PATH.read_text(encoding="utf-8")
    assert text.count("\n") + 1 <= 150
    for forbidden in (
        "PlaidSandboxProvider",
        "boto3",
        "httpx",
        "SessionLocal",
        "create_app_engine",
        "os.environ",
        "sandbox.plaid.com",
        "from app.config",
        "evaluate_refresh_case",
        "def _observe",
    ):
        assert forbidden not in text
