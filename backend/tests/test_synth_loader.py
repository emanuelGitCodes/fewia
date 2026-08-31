"""Tests for the synthetic data loader."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DailyEnvironment, DailyFinance, DailyHealth
from app.synth import PROFILES, generate
from app.synth.loader import load

END_DATE = date(2099, 1, 2)
DATASET = generate(seed=42, days=2, end_date=END_DATE)
START_DATE = DATASET.finance[0].observation_date
USER_IDS = [profile.user_id for profile in PROFILES]
SKIP_MESSAGE = (
    "No database answers at DATABASE_URL. Start Postgres with "
    "`docker compose up -d postgres` and run `uv run alembic upgrade head`."
)


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    """Give a connected engine, or skip the module."""

    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect():
            pass
    except SQLAlchemyError as error:
        engine.dispose()
        pytest.skip(f"{SKIP_MESSAGE} Driver said: {error.__class__.__name__}.")
    yield engine
    engine.dispose()


@pytest.fixture()
def session(engine: Engine) -> Iterator[Session]:
    """Give a session that rolls back test records."""

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _counts(session: Session) -> tuple[int, int, int]:
    filter_ = lambda model: (  # noqa: E731
        model.user_id.in_(USER_IDS),
        model.observation_date.between(START_DATE, END_DATE),
    )
    finance = session.scalar(
        select(func.count()).select_from(DailyFinance).where(*filter_(DailyFinance))
    )
    environment = session.scalar(
        select(func.count())
        .select_from(DailyEnvironment)
        .where(*filter_(DailyEnvironment))
    )
    health = session.scalar(
        select(func.count()).select_from(DailyHealth).where(*filter_(DailyHealth))
    )
    return int(finance or 0), int(environment or 0), int(health or 0)


def test_load_writes_expected_row_counts(session: Session) -> None:
    load(session, DATASET)

    assert _counts(session) == (
        len(DATASET.finance),
        len(DATASET.environment),
        len(DATASET.health),
    )


def test_load_replaces_matching_rows(session: Session) -> None:
    load(session, DATASET)
    expected = _counts(session)

    load(session, DATASET)

    assert _counts(session) == expected


def test_load_writes_dataset_version_as_source(session: Session) -> None:
    load(session, DATASET)
    sources = {
        *session.scalars(
            select(DailyFinance.source).where(
                DailyFinance.user_id.in_(USER_IDS),
                DailyFinance.observation_date.between(START_DATE, END_DATE),
            )
        ).all(),
        *session.scalars(
            select(DailyEnvironment.source).where(
                DailyEnvironment.user_id.in_(USER_IDS),
                DailyEnvironment.observation_date.between(START_DATE, END_DATE),
            )
        ).all(),
        *session.scalars(
            select(DailyHealth.source).where(
                DailyHealth.user_id.in_(USER_IDS),
                DailyHealth.observation_date.between(START_DATE, END_DATE),
            )
        ).all(),
    }

    assert sources == {DATASET.data_version}
