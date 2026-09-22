import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, Table, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.evaluation_budget_inputs import _parse_clock
from app.evaluation_plan_inputs import fixture_plan
from app.handoff_models import ShoppingHandoff
from app.models import User
from app.providers.instacart import InstacartUncertain
from app.services.grocery_planner import PlanEstimate
from app.services.shopping_payload import build_shopping_payload

_USER_ERROR = "user_id MUST be a positive integer"
_CONSENT_ERROR = "plan_accepted MUST be True"
_REJECTED_ERROR = "plan MUST be accepted"


@dataclass(frozen=True, slots=True)
class HandoffFixture:
    factory: sessionmaker[Session]
    user_id: int
    clock: datetime
    plan: PlanEstimate
    payload: dict[str, object]


class FakeUncertainHandoffProvider:
    def __init__(self) -> None:
        self.calls = 0

    def create_link(self, payload: dict[str, object]) -> str:
        del payload
        self.calls += 1
        raise InstacartUncertain()


def _user_id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(_USER_ERROR)
    return value


def _handoff_tables() -> list[Table]:
    tables = Base.metadata.tables
    return [tables[User.__tablename__], tables[ShoppingHandoff.__tablename__]]


def _enable_foreign_keys(
    dbapi_connection: sqlite3.Connection, connection_record: object
) -> None:
    del connection_record
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


@contextmanager
def fixture(inputs: dict[str, object]) -> Iterator[HandoffFixture]:
    user_id = _user_id(inputs.get("user_id"))
    clock = _parse_clock(inputs.get("now"))
    if inputs.get("plan_accepted") is not True:
        raise ValueError(_CONSENT_ERROR)
    plan = fixture_plan(inputs)
    if plan.accepted is not True:
        raise ValueError(_REJECTED_ERROR)
    payload = build_shopping_payload(plan)
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", _enable_foreign_keys)
    tables = _handoff_tables()
    try:
        Base.metadata.create_all(engine, tables=tables)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        with factory.begin() as session:
            session.add(User(id=user_id, display_name="Owner"))
            session.flush()
        yield HandoffFixture(factory, user_id, clock, plan, payload)
    finally:
        engine.dispose()
