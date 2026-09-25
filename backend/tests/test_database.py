"""Tests that run against a live database. They skip when no database answers."""

from collections.abc import Iterator

import pytest
from conftest import require_test_database_url, skip_or_fail_unreachable_test_database
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import db as db_module
from app.config import settings

EXPECTED_TABLES = {
    "users",
    "daily_finance",
    "daily_environment",
    "daily_health",
    "model_runs",
    "predictions",
}


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    """Give a connected engine, or skip the module."""
    engine = create_engine(
        require_test_database_url(),
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect():
            pass
    except SQLAlchemyError as error:
        engine.dispose()
        skip_or_fail_unreachable_test_database(error)
    yield engine
    engine.dispose()


def test_the_six_tables_exist(engine: Engine) -> None:
    names = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= names


def test_daily_health_checks_that_steps_are_not_negative(engine: Engine) -> None:
    checks = inspect(engine).get_check_constraints("daily_health")
    texts = [str(check["sqltext"]) for check in checks]
    assert any("steps" in text and ">= 0" in text for text in texts)


_PG_CONNECT_ARGS: dict[str, int | str] = {
    "connect_timeout": 3,
    "options": "-c statement_timeout=10000 -c lock_timeout=5000",
}
_PSYCOPG_URL = "postgresql+psycopg://worker:worker@127.0.0.1:5432/fewia"
_POSTGRES_URLS = (
    _PSYCOPG_URL,
    "postgresql://worker:worker@127.0.0.1:5432/fewia",
)
_POSTGRES_ALIAS_URLS = (
    "postgres://worker:worker@127.0.0.1:5432/fewia",
    "postgres+psycopg://worker:worker@127.0.0.1:5432/fewia",
)
_SQLITE_URLS = ("sqlite://", "sqlite+pysqlite://")


def test_postgresql_urls_pass_pool_and_connect_timeouts() -> None:
    for url in _POSTGRES_URLS:
        assert make_url(url).get_backend_name() == "postgresql"
        kwargs = db_module.engine_connect_kwargs(url)
        assert kwargs["pool_pre_ping"] is True
        assert kwargs["pool_timeout"] == 3
        assert kwargs["connect_args"] == _PG_CONNECT_ARGS
    created = db_module.create_app_engine(_PSYCOPG_URL)
    try:
        assert created.pool.timeout() == 3
    finally:
        created.dispose()


def test_postgres_scheme_alias_is_unsupported() -> None:
    for url in _POSTGRES_ALIAS_URLS:
        assert make_url(url).get_backend_name() == "postgres"
        kwargs = db_module.engine_connect_kwargs(url)
        assert kwargs == {"pool_pre_ping": True}
        assert "connect_args" not in kwargs
        assert "pool_timeout" not in kwargs


def test_sqlite_urls_omit_postgres_connect_args() -> None:
    for url in _SQLITE_URLS:
        kwargs = db_module.engine_connect_kwargs(url)
        assert kwargs == {"pool_pre_ping": True}
        assert "connect_args" not in kwargs
        assert "pool_timeout" not in kwargs
        created = db_module.create_app_engine(url)
        try:
            assert "connect_timeout" not in str(created.url.query)
        finally:
            created.dispose()


def test_module_engine_keeps_pool_pre_ping_and_session_expire_flag() -> None:
    kwargs = db_module.engine_connect_kwargs(settings.database_url)
    assert kwargs["pool_pre_ping"] is True
    session: Session = db_module.SessionLocal()
    try:
        assert session.expire_on_commit is False
    finally:
        session.close()
    if make_url(settings.database_url).get_backend_name() == "postgresql":
        assert db_module.engine.pool.timeout() == 3
        assert kwargs["connect_args"] == _PG_CONNECT_ARGS
    else:
        assert "connect_args" not in kwargs
        assert "pool_timeout" not in kwargs
