from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import NoReturn

from sqlalchemy.orm import Session, sessionmaker

from app.evaluation_budget_inputs import _cents, _parse_clock, _parse_date
from app.evaluation_database import fixture_database
from app.models import User
from app.plaid_models import PlaidItem, PlaidTransaction
from app.providers.plaid import PlaidUnavailable

ITEM_ID = "evalrefresh000000000000000000000001"
INPUT_ERROR = "inputs are invalid"
UNAVAILABLE_SENTINEL = "synthetic-refresh-unavailable"


class FakeUnavailableSyncProvider:
    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def sync_page(self, credential_ref: str, cursor: str | None) -> NoReturn:
        del credential_ref, cursor
        self.calls += 1
        error = PlaidUnavailable()
        error.args = (UNAVAILABLE_SENTINEL,)
        raise error


@dataclass(frozen=True, slots=True)
class RefreshFixture:
    session_factory: sessionmaker[Session]
    user_id: int
    period: date
    clock: datetime
    limit: int
    plan_cap: int | None
    posted: int
    pending: int
    item_id: str = ITEM_ID

    @property
    def factory(self) -> sessionmaker[Session]:
        return self.session_factory

    def read_state(self) -> tuple[str | None, datetime | None]:
        with self.session_factory() as session:
            item = session.get(PlaidItem, self.item_id)
            if item is None:
                return None, None
            refreshed = item.last_synced_at
            if refreshed is not None:
                if refreshed.tzinfo is None or refreshed.utcoffset() is None:
                    refreshed = refreshed.replace(tzinfo=UTC)
                else:
                    refreshed = refreshed.astimezone(UTC)
            return item.cursor, refreshed


def _period(value: object) -> date:
    period = _parse_date(value)
    if period.day != 1 or period.isoformat() != value:
        raise ValueError(INPUT_ERROR)
    return period


def _clock(value: object) -> datetime:
    clock = _parse_clock(value)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError(INPUT_ERROR)
    return clock


def _transaction(
    txn_id: str, amount: int, pending: bool, period: date
) -> PlaidTransaction:
    return PlaidTransaction(
        item_id=ITEM_ID,
        transaction_id=txn_id,
        account_id="eval-account",
        amount_cents=amount,
        currency="USD",
        transaction_date=period,
        pending=pending,
        pending_transaction_id=None,
        is_grocery=True,
        classification_version="eval-v1",
    )


@contextmanager
def fixture(inputs: dict[str, object]) -> Iterator[RefreshFixture]:
    if type(inputs) is not dict:
        raise TypeError(INPUT_ERROR)
    user_id = _cents(inputs.get("user_id"))
    if user_id < 1:
        raise ValueError(INPUT_ERROR)
    period = _period(inputs.get("spending_period", inputs.get("budget_period")))
    if "budget_period" in inputs and _period(inputs["budget_period"]) != period:
        raise ValueError(INPUT_ERROR)
    clock = _clock(inputs.get("now"))
    stamp = inputs.get("spending_refreshed_at")
    refreshed = _clock(stamp).astimezone(UTC)
    posted = _cents(inputs.get("posted_cents"))
    pending = _cents(inputs.get("pending_cents"))
    limit = _cents(inputs.get("monthly_limit_cents"))
    cap = inputs.get("plan_cap_cents")
    plan_cap = None if cap is None else _cents(cap)
    if limit < 0 or (plan_cap is not None and plan_cap < 0):
        raise ValueError(INPUT_ERROR)
    cursor = inputs.get("cursor", f"eval-cursor:{stamp}")
    if cursor is not None and type(cursor) is not str:
        raise TypeError(INPUT_ERROR)
    with fixture_database() as database:
        factory = database.factory
        with factory.begin() as session:
            session.add(User(id=user_id, display_name="eval-refresh-user"))
            session.flush()
            session.add(
                PlaidItem(
                    id=ITEM_ID,
                    user_id=user_id,
                    provider_item_id="eval-refresh-provider-item",
                    credential_ref="eval-refresh-credential-ref",
                    cursor=cursor,
                    last_synced_at=refreshed,
                )
            )
            session.flush()
            session.add(_transaction("eval-posted", posted, False, period))
            session.add(_transaction("eval-pending", pending, True, period))
        yield RefreshFixture(
            factory, user_id, period, clock, limit, plan_cap, posted, pending
        )
