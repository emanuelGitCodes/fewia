"""Tests that run against a live database. They skip when no database answers."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings

EXPECTED_TABLES = {
    "users",
    "daily_finance",
    "daily_environment",
    "daily_health",
    "model_runs",
    "predictions",
}

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


def test_the_six_tables_exist(engine: Engine) -> None:
    names = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= names


def test_daily_health_checks_that_steps_are_not_negative(engine: Engine) -> None:
    checks = inspect(engine).get_check_constraints("daily_health")
    texts = [str(check["sqltext"]) for check in checks]
    assert any("steps" in text and ">= 0" in text for text in texts)
