from datetime import UTC, date, datetime
from decimal import Decimal
from typing import NoReturn, cast

import httpx
import pytest
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from app import evaluation_refresh_fixture as refresh
from app.domain.budget import StaleSpendingError, calculate_budget
from app.models import User
from app.plaid_models import PlaidItem, PlaidTransaction
from app.providers.plaid import PlaidUnavailable
from app.services.ledger_budget import SpendingUnavailable, load_spending
from app.services.plaid_sync import SyncProvider, sync_item


@pytest.fixture
def inputs() -> dict[str, object]:
    return {
        "user_id": 7,
        "budget_period": "2026-10-01",
        "spending_period": "2026-10-01",
        "now": "2026-10-02T12:00:00Z",
        "spending_refreshed_at": "2026-10-02T06:00:00-04:00",
        "cursor": "synthetic-cursor-before",
        "monthly_limit_cents": 40000,
        "plan_cap_cents": 9000,
        "posted_cents": 12345,
        "pending_cents": 678,
    }


def test_seeds_actual_owned_grocery_rows(inputs: dict[str, object]) -> None:
    with refresh.fixture(inputs) as facts:
        assert facts.factory is facts.session_factory
        assert facts.user_id == 7
        assert facts.item_id == refresh.ITEM_ID
        assert facts.period == date(2026, 10, 1)
        assert facts.clock == datetime(2026, 10, 2, 12, tzinfo=UTC)
        assert (facts.limit, facts.plan_cap) == (40000, 9000)
        assert (facts.posted, facts.pending) == (12345, 678)
        with facts.factory() as session:
            assert session.bind is not None
            assert session.bind.dialect.name == "sqlite"
            assert session.scalar(select(func.count()).select_from(User)) == 1
            assert session.scalar(select(func.count()).select_from(PlaidItem)) == 1
            owner = session.get(User, facts.user_id)
            assert owner is not None
            assert owner.display_name == "eval-refresh-user"
            item = session.get(PlaidItem, facts.item_id)
            assert item is not None
            assert item.user_id == facts.user_id
            assert item.provider_item_id == "eval-refresh-provider-item"
            assert item.credential_ref == "eval-refresh-credential-ref"
            rows = session.scalars(
                select(PlaidTransaction).order_by(PlaidTransaction.pending)
            ).all()
            assert len(rows) == 2
            assert [(row.amount_cents, row.pending) for row in rows] == [
                (12345, False),
                (678, True),
            ]
            assert all(row.item_id == facts.item_id for row in rows)
            assert all(row.transaction_date == facts.period for row in rows)
            assert all(row.currency == "USD" and row.is_grocery for row in rows)
            assert all(row.classification_version == "eval-v1" for row in rows)
            spending = load_spending(session, facts.user_id, facts.period)
            assert (spending.posted_cents, spending.pending_cents) == (12345, 678)
        assert facts.read_state() == (
            "synthetic-cursor-before",
            datetime(2026, 10, 2, 10, tzinfo=UTC),
        )


def test_contexts_are_isolated_and_state_reads_saved_values(
    inputs: dict[str, object],
) -> None:
    with refresh.fixture(inputs) as first, refresh.fixture(inputs) as second:
        assert first.factory.kw["bind"] is not second.factory.kw["bind"]
        before = second.read_state()
        with first.factory.begin() as session:
            item = session.get(PlaidItem, first.item_id)
            assert item is not None
            item.cursor = "synthetic-cursor-after"
            item.last_synced_at = first.clock
            row = session.get(PlaidTransaction, (first.item_id, "eval-posted"))
            assert row is not None
            row.amount_cents = 1
        assert first.read_state() == ("synthetic-cursor-after", first.clock)
        assert second.read_state() == before
        with second.factory() as session:
            spending = load_spending(session, second.user_id, second.period)
            assert spending.posted_cents == 12345


def test_stale_uncapped_facts_remain_stale(inputs: dict[str, object]) -> None:
    inputs["spending_refreshed_at"] = "2026-09-29T12:00:00Z"
    inputs["plan_cap_cents"] = None
    with refresh.fixture(inputs) as facts, facts.factory() as session:
        spending = load_spending(session, facts.user_id, facts.period)
        assert spending.refreshed_at == datetime(2026, 9, 29, 12, tzinfo=UTC)
        assert spending.posted_cents == 12345
        with pytest.raises(StaleSpendingError):
            calculate_budget(facts.limit, spending, now=facts.clock)


def test_signed_spending_and_zero_limits_are_facts(inputs: dict[str, object]) -> None:
    inputs.update(
        posted_cents=-125, pending_cents=-25, monthly_limit_cents=0, plan_cap_cents=0
    )
    with refresh.fixture(inputs) as facts, facts.factory() as session:
        spending = load_spending(session, facts.user_id, facts.period)
        assert (spending.posted_cents, spending.pending_cents) == (-125, -25)
        assert (facts.limit, facts.plan_cap) == (0, 0)


@pytest.mark.parametrize("cursor", [None, "", "   "])
def test_incomplete_cursor_does_not_become_zero_spending(
    inputs: dict[str, object], cursor: str | None
) -> None:
    inputs["cursor"] = cursor
    with refresh.fixture(inputs) as facts, facts.factory() as session:
        assert facts.read_state()[0] == cursor
        with pytest.raises(SpendingUnavailable):
            load_spending(session, facts.user_id, facts.period)


@pytest.mark.parametrize("period_key", ["budget_period", "spending_period"])
def test_single_period_and_default_cursor(
    inputs: dict[str, object], period_key: str
) -> None:
    inputs.pop(period_key)
    inputs.pop("cursor")
    inputs.pop("plan_cap_cents")
    with refresh.fixture(inputs) as facts:
        assert facts.period == date(2026, 10, 1)
        assert facts.plan_cap is None
        assert facts.read_state()[0] == f"eval-cursor:{inputs['spending_refreshed_at']}"


def _forbid_database(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("Validation reached database creation")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("user_id", True),
        ("user_id", 0),
        ("user_id", -1),
        ("user_id", "7"),
        ("user_id", 7.0),
        ("budget_period", "2026-10-02"),
        ("budget_period", "2026-09-01"),
        ("budget_period", "20261001"),
        ("spending_period", "2026-10-02"),
        ("spending_period", "20261001"),
        ("spending_period", "2026-02-30"),
        ("spending_period", True),
        ("spending_period", date(2026, 10, 1)),
        ("now", "2026-10-02T12:00:00"),
        ("now", "malformed"),
        ("now", True),
        ("spending_refreshed_at", "2026-10-02T10:00:00"),
        ("spending_refreshed_at", "malformed"),
        ("spending_refreshed_at", None),
        ("posted_cents", True),
        ("posted_cents", "12345"),
        ("posted_cents", Decimal("12345")),
        ("posted_cents", 12345.0),
        ("pending_cents", False),
        ("pending_cents", None),
        ("pending_cents", 0.5),
        ("monthly_limit_cents", -1),
        ("monthly_limit_cents", True),
        ("monthly_limit_cents", "40000"),
        ("plan_cap_cents", -1),
        ("plan_cap_cents", False),
        ("plan_cap_cents", 9000.0),
        ("cursor", True),
        ("cursor", 1),
    ],
)
def test_invalid_values_fail_before_database_creation(
    inputs: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: object,
) -> None:
    monkeypatch.setattr(refresh, "fixture_database", _forbid_database)
    inputs[key] = value
    with pytest.raises((TypeError, ValueError)), refresh.fixture(inputs):
        pytest.fail("Invalid inputs reached the fixture body")


@pytest.mark.parametrize(
    "key",
    [
        "user_id",
        "now",
        "spending_refreshed_at",
        "posted_cents",
        "pending_cents",
        "monthly_limit_cents",
    ],
)
def test_missing_values_fail_before_database_creation(
    inputs: dict[str, object], monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setattr(refresh, "fixture_database", _forbid_database)
    inputs.pop(key)
    with pytest.raises((TypeError, ValueError)), refresh.fixture(inputs):
        pytest.fail("Missing inputs reached the fixture body")


def test_missing_periods_fail_before_database_creation(
    inputs: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(refresh, "fixture_database", _forbid_database)
    inputs.pop("budget_period")
    inputs.pop("spending_period")
    with pytest.raises(TypeError), refresh.fixture(inputs):
        pytest.fail("Missing periods reached the fixture body")


@pytest.mark.parametrize("value", [None, [], True, "invalid"])
def test_non_dictionary_inputs_fail_before_database_creation(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    monkeypatch.setattr(refresh, "fixture_database", _forbid_database)
    with pytest.raises(TypeError), refresh.fixture(cast(dict[str, object], value)):
        pytest.fail("Invalid inputs reached the fixture body")


def test_expected_gold_and_override_fields_do_not_supply_facts(
    inputs: dict[str, object],
) -> None:
    inputs.update(
        expected={"posted_cents": 0},
        gold={"available_cents": 999999},
        database_url="unsupported://synthetic",
        model="synthetic-model",
        evidence_class="synthetic-class",
    )
    with refresh.fixture(inputs) as facts, facts.factory() as session:
        assert session.bind is not None
        assert session.bind.dialect.name == "sqlite"
        spending = load_spending(session, facts.user_id, facts.period)
        assert spending.posted_cents == 12345
        assert facts.posted == 12345


@pytest.mark.parametrize("stage", ["normal", "body", "seed"])
def test_cleanup_on_normal_body_and_seed_exits(
    inputs: dict[str, object], monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    disposed: list[Engine] = []

    def record_disposal(engine: Engine) -> None:
        disposed.append(engine)

    def fail_seed(*args: object, **kwargs: object) -> NoReturn:
        raise RuntimeError("synthetic-seed-failure")

    event.listen(Engine, "engine_disposed", record_disposal)
    held: Session | None = None
    try:
        if stage == "seed":
            monkeypatch.setattr(refresh, "_transaction", fail_seed)
        try:
            with refresh.fixture(inputs) as facts:
                held = facts.factory()
                assert held.get(User, facts.user_id) is not None
                assert held.in_transaction()
                if stage == "body":
                    raise RuntimeError("synthetic-body-failure")
        except RuntimeError as error:
            assert stage != "normal"
            assert str(error) == f"synthetic-{stage}-failure"
        else:
            assert stage == "normal"
        assert len(disposed) == 1
        if held is not None:
            assert not held.in_transaction()
            assert len(held.identity_map) == 0
    finally:
        event.remove(Engine, "engine_disposed", record_disposal)


def test_counted_unavailable_sync_preserves_state_without_network(
    inputs: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbid_http(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Unexpected HTTP request")

    monkeypatch.setattr(httpx.Client, "send", forbid_http)
    unavailable = refresh.FakeUnavailableSyncProvider()
    provider: SyncProvider = unavailable
    assert unavailable.calls == 0
    for attempt in range(1, 3):
        with pytest.raises(PlaidUnavailable) as failure:
            provider.sync_page("eval-refresh-credential-ref", None)
        assert failure.value.args == (refresh.UNAVAILABLE_SENTINEL,)
        assert unavailable.calls == attempt
    with refresh.fixture(inputs) as facts:
        before = facts.read_state()
        with pytest.raises(PlaidUnavailable) as failure:
            sync_item(facts.factory, facts.item_id, provider, user_id=facts.user_id)
        assert failure.value.args == (refresh.UNAVAILABLE_SENTINEL,)
        assert unavailable.calls == 3
        assert facts.read_state() == before
        with facts.factory() as session:
            spending = load_spending(session, facts.user_id, facts.period)
            assert (spending.posted_cents, spending.pending_cents) == (12345, 678)
