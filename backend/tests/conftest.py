"""Shared fixtures for deterministic tool tests."""

from collections.abc import Collection, Iterator, Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.deps import get_session
from app.main import app


class UserSeeder(Protocol):
    """Seed one user and return its ID."""

    def __call__(self, user_id: int = 1, display_name: str = "Test user") -> int: ...


class RowSeeder(Protocol):
    """Seed a range of daily rows and return the inserted dates."""

    def __call__(
        self,
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]: ...


DailyRowType = (
    type[models.DailyHealth] | type[models.DailyFinance] | type[models.DailyEnvironment]
)


def _days(start_date: date, end_date: date) -> Iterator[date]:
    current_date = start_date
    while current_date <= end_date:
        yield current_date
        current_date += timedelta(days=1)


def _seed_rows(
    session: Session,
    row_type: DailyRowType,
    defaults: Mapping[str, object],
    user_id: int,
    start_date: date,
    end_date: date,
    *,
    skip_days: Collection[date] = (),
    null_fields: Collection[str] = (),
    source: str = "synthetic-v1",
    overrides: Mapping[str, object] | None = None,
) -> list[date]:
    inserted_dates: list[date] = []
    for observation_date in _days(start_date, end_date):
        if observation_date in skip_days:
            continue
        values: dict[str, object] = {
            "user_id": user_id,
            "observation_date": observation_date,
            "source": source,
            **defaults,
        }
        for field_name in null_fields:
            values[field_name] = None
        if overrides is not None:
            values.update(overrides)
        session.add(row_type(**values))
        inserted_dates.append(observation_date)
    session.flush()
    return inserted_dates


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Give the suite one in-memory SQLite engine."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    """Give each test a session that rolls back its rows."""
    connection: Connection = engine.connect()
    transaction = connection.begin()
    test_session = Session(bind=connection)
    try:
        yield test_session
    finally:
        test_session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    """Give each test a client that uses its database session."""

    def get_test_session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture()
def seed_user(session: Session) -> UserSeeder:
    """Give tests a user factory."""

    def seed(user_id: int = 1, display_name: str = "Test user") -> int:
        session.add(models.User(id=user_id, display_name=display_name))
        session.flush()
        return user_id

    return seed


@pytest.fixture()
def seed_health(session: Session) -> RowSeeder:
    """Give tests a daily health row factory."""

    def seed(
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]:
        defaults: dict[str, object] = {
            "steps": 8000,
            "resting_heart_rate": Decimal("60.00"),
            "sleep_minutes": 420,
            "intensity_minutes": 30,
            "stress_score": Decimal("25.00"),
        }
        return _seed_rows(
            session,
            models.DailyHealth,
            defaults,
            user_id,
            start_date,
            end_date,
            skip_days=skip_days,
            null_fields=null_fields,
            source=source,
            overrides=overrides,
        )

    return seed


@pytest.fixture()
def seed_finance(session: Session) -> RowSeeder:
    """Give tests a daily finance row factory."""

    def seed(
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]:
        defaults: dict[str, object] = {
            "total_spending": Decimal("100.00"),
            "grocery_spending": Decimal("40.00"),
            "restaurant_spending": Decimal("20.00"),
            "transportation_spending": Decimal("15.00"),
            "fitness_spending": Decimal("10.00"),
            "discretionary_spending": Decimal("15.00"),
            "cash_flow": Decimal("50.00"),
        }
        return _seed_rows(
            session,
            models.DailyFinance,
            defaults,
            user_id,
            start_date,
            end_date,
            skip_days=skip_days,
            null_fields=null_fields,
            source=source,
            overrides=overrides,
        )

    return seed


@pytest.fixture()
def seed_environment(session: Session) -> RowSeeder:
    """Give tests a daily environment row factory."""

    def seed(
        user_id: int,
        start_date: date,
        end_date: date,
        *,
        skip_days: Collection[date] = (),
        null_fields: Collection[str] = (),
        source: str = "synthetic-v1",
        overrides: Mapping[str, object] | None = None,
    ) -> list[date]:
        defaults: dict[str, object] = {
            "park_count": 2,
            "gym_count": 1,
            "grocery_store_count": 3,
            "restaurant_count": 5,
            "location_type": "urban",
        }
        return _seed_rows(
            session,
            models.DailyEnvironment,
            defaults,
            user_id,
            start_date,
            end_date,
            skip_days=skip_days,
            null_fields=null_fields,
            source=source,
            overrides=overrides,
        )

    return seed
