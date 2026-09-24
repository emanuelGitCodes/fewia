import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import NoReturn

from sqlalchemy import Table, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.evaluation_budget_inputs import CLOCK_ERROR, _cents, _parse_clock, _parse_date
from app.models import User
from app.plaid_models import PlaidItem, PlaidTransaction
from app.providers.plaid import PlaidUnavailable

ITEM_ID = "evalrefresh000000000000000000000001"
INPUT_ERROR = "inputs are invalid"
_TABLE_NAMES = ("users", "plaid_items", "plaid_transactions")


class FakeUnavailableSyncProvider:
    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def sync_page(self, credential_ref: str, cursor: str | None) -> NoReturn:
        del credential_ref, cursor
        self.calls += 1
        raise PlaidUnavailable()


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

    def read_state(self) -> tuple[str | None, datetime | None]:
        with self.session_factory() as session:
            item = session.get(PlaidItem, ITEM_ID)
            if item is None:
                return None, None
            return item.cursor, item.last_synced_at


def _user_id(value: object) -> int:
    if type(value) is not int or value < 1:
        raise TypeError(INPUT_ERROR)
    return value


def _tables() -> list[Table]:
    # Index Table values by name. Mapped __table__ infers FromClause.
    catalog = Base.metadata.tables
    return [catalog[name] for name in _TABLE_NAMES]


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


def _seed(
    session: Session,
    user_id: int,
    period: date,
    stamp: str,
    refreshed: datetime,
    posted: int,
    pending: int,
) -> None:
    session.add(User(id=user_id, display_name="eval-refresh-user"))
    session.flush()
    session.add(
        PlaidItem(
            id=ITEM_ID,
            user_id=user_id,
            provider_item_id="eval-refresh-provider-item",
            credential_ref="eval-refresh-credential-ref",
            cursor=f"eval-cursor:{stamp}",
            last_synced_at=refreshed,
        )
    )
    session.flush()
    session.add(_transaction("eval-posted", posted, False, period))
    session.add(_transaction("eval-pending", pending, True, period))
    session.flush()


@contextmanager
def fixture(inputs: dict[str, object]) -> Iterator[RefreshFixture]:
    if type(inputs) is not dict:
        raise TypeError(INPUT_ERROR)
    user_id = _user_id(inputs.get("user_id"))
    stamp = inputs.get("spending_refreshed_at")
    if type(stamp) is not str:
        raise TypeError(CLOCK_ERROR)
    period = _parse_date(inputs.get("spending_period", inputs.get("budget_period")))
    clock = _parse_clock(inputs.get("now"))
    refreshed = _parse_clock(stamp)
    posted = _cents(inputs.get("posted_cents"))
    pending = _cents(inputs.get("pending_cents"))
    limit = _cents(inputs.get("monthly_limit_cents"))
    cap = inputs.get("plan_cap_cents")
    plan_cap = None if cap is None else _cents(cap)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    try:
        Base.metadata.create_all(engine, tables=_tables())
        factory: sessionmaker[Session] = sessionmaker(
            bind=engine, expire_on_commit=False
        )
        with factory.begin() as session:
            _seed(session, user_id, period, stamp, refreshed, posted, pending)
        yield RefreshFixture(
            factory, user_id, period, clock, limit, plan_cap, posted, pending
        )
    finally:
        engine.dispose()
