"""Test isolated evaluation databases and safe failures."""

import re
import sqlite3
import traceback
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, nullcontext
from typing import cast
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from conftest import require_test_database_url
from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import evaluation_database, models
from app.db import Base
from app.evaluation_database import (
    EvaluationDatabaseError,
    FixtureDatabase,
    fixture_database,
)
from app.job_models import Job

_MESSAGE = "Evaluation database operation failed."
_TABLE_NAMES = {
    "users",
    "daily_finance",
    "daily_environment",
    "daily_health",
    "model_runs",
    "predictions",
    "jobs",
    "job_outbox",
    "grocery_evidence",
    "shopping_handoffs",
    "plaid_items",
    "plaid_transactions",
}


def _engine(database: FixtureDatabase) -> Engine:
    return cast(Engine, database.factory.kw["bind"])


def _seed_user(database: FixtureDatabase) -> None:
    with database.factory() as session:
        session.add(models.User(id=1, display_name="Fixture user"))
        session.commit()


def _user_ids(database: FixtureDatabase) -> list[int]:
    with database.factory() as session:
        return list(session.scalars(select(models.User.id)))


def _assert_safe(error: EvaluationDatabaseError) -> None:
    assert str(error) == _MESSAGE
    assert error.__cause__ is None
    assert error.__suppress_context__ is True
    rendered = "".join(traceback.format_exception(error))
    assert "private-driver-detail" not in rendered


def test_sqlite_contexts_are_empty_and_isolated() -> None:
    with fixture_database() as first:
        assert first.backend == "sqlite"
        assert isinstance(_engine(first).pool, StaticPool)
        assert set(inspect(_engine(first)).get_table_names()) == _TABLE_NAMES
        assert _user_ids(first) == []
        _seed_user(first)
        with fixture_database() as second:
            assert _user_ids(second) == []
            _seed_user(second)
            assert _engine(first) is not _engine(second)
        assert _user_ids(first) == [1]
    with fixture_database() as third:
        assert _user_ids(third) == []


def test_sqlite_connections_allow_another_thread() -> None:
    with fixture_database() as database:
        _seed_user(database)
        with ThreadPoolExecutor(max_workers=1) as executor:
            assert executor.submit(_user_ids, database).result() == [1]


def test_sqlite_enforces_foreign_keys() -> None:
    with fixture_database() as database:
        with database.factory() as session:
            assert session.scalar(text("PRAGMA foreign_keys")) == 1
            session.add(Job(user_id=999, kind="agent", request_key="fk", payload={}))
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()


def test_fixture_sessions_accept_typed_options() -> None:
    with fixture_database() as database:
        with database.factory(autoflush=False, expire_on_commit=True) as session:
            assert session.autoflush is False
            assert session.expire_on_commit is True


@pytest.mark.parametrize("abort", [False, True])
def test_sqlite_closes_live_sessions_and_disposes_connections(abort: bool) -> None:
    outcome = (
        pytest.raises(RuntimeError, match="caller failure") if abort else nullcontext()
    )
    with outcome:
        with fixture_database() as database:
            session = database.factory()
            session.add(models.User(id=1, display_name="Uncommitted user"))
            session.flush()
            raw = cast(
                sqlite3.Connection, session.connection().connection.driver_connection
            )
            if abort:
                raise RuntimeError("caller failure")
    assert not session.in_transaction()
    with pytest.raises(sqlite3.ProgrammingError):
        raw.execute("SELECT 1")


def test_caller_exception_is_preserved_after_cleanup() -> None:
    failure = RuntimeError("caller failure")
    with pytest.raises(RuntimeError) as caught:
        with fixture_database() as database:
            _seed_user(database)
            raise failure
    assert caught.value is failure
    with fixture_database() as fresh:
        assert _user_ids(fresh) == []


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a URL",
        "sqlite://",
        "postgresql://localhost/eval_test",
        "postgresql+psycopg2://localhost/eval_test",
        "postgresql+psycopg://remote.example/eval_test",
        "postgresql+psycopg://localhost/production",
        "postgresql+psycopg://127.0.0.1/fewia",
        "postgresql+psycopg://postgres/",
        "postgresql+psycopg:///eval_test",
        "postgresql+psycopg://localhost/eval_test?host=remote.example",
        "postgresql+psycopg://localhost/eval_test?dbname=production",
        "postgresql+psycopg://localhost/eval_test?options=-csearch_path=public",
        "postgresql+psycopg://localhost/eval_test?service=production",
    ],
)
def test_bad_urls_are_rejected_before_engine_creation(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    create = Mock()
    monkeypatch.setattr(evaluation_database, "create_engine", create)
    with pytest.raises(EvaluationDatabaseError) as caught:
        with fixture_database(url):
            pytest.fail("Rejected URL entered the fixture context.")
    _assert_safe(caught.value)
    create.assert_not_called()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "postgres"])
@pytest.mark.parametrize("name", ["eval_test", "fewia_eval_test"])
def test_allowed_urls_reach_connection_setup(
    monkeypatch: pytest.MonkeyPatch, host: str, name: str
) -> None:
    create = Mock(
        side_effect=OperationalError(
            "private-driver-detail", {}, RuntimeError("private-driver-detail")
        )
    )
    monkeypatch.setattr(evaluation_database, "create_engine", create)
    with pytest.raises(EvaluationDatabaseError) as caught:
        with fixture_database(f"postgresql+psycopg://{host}/{name}"):
            pytest.fail("Failed connection entered the fixture context.")
    assert create.call_count == 1
    _assert_safe(caught.value)


@pytest.mark.parametrize(
    "failure",
    [
        OperationalError(
            "private-driver-detail", {}, RuntimeError("private-driver-detail")
        ),
        ValueError("private-driver-detail"),
        ImportError("private-driver-detail"),
    ],
)
def test_setup_failure_disposes_the_sqlite_engine(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    dispose = Mock(wraps=engine.dispose)
    monkeypatch.setattr(engine, "dispose", dispose)
    monkeypatch.setattr(evaluation_database, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(
        Base.metadata,
        "create_all",
        Mock(side_effect=failure),
    )
    with pytest.raises(EvaluationDatabaseError) as caught:
        with fixture_database():
            pytest.fail("Failed setup entered the fixture context.")
    _assert_safe(caught.value)
    dispose.assert_called_once_with()


def test_unexpected_setup_failure_is_preserved_after_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    dispose = Mock(wraps=engine.dispose)
    failure = TypeError("setup programming error")
    monkeypatch.setattr(engine, "dispose", dispose)
    monkeypatch.setattr(evaluation_database, "create_engine", Mock(return_value=engine))
    monkeypatch.setattr(Base.metadata, "create_all", Mock(side_effect=failure))
    with pytest.raises(TypeError) as caught:
        with fixture_database():
            pytest.fail("Failed setup entered the fixture context.")
    assert caught.value is failure
    dispose.assert_called_once_with()


def test_database_errors_in_the_context_are_static() -> None:
    with pytest.raises(EvaluationDatabaseError) as caught:
        with fixture_database() as database:
            with database.factory() as session:
                session.execute(text("SELECT * FROM missing_fixture_table"))
    _assert_safe(caught.value)


def test_fixture_representation_contains_only_the_backend() -> None:
    with fixture_database() as database:
        assert repr(database) == "FixtureDatabase(backend='sqlite')"


def test_cleanup_continues_after_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=Session)
    engine = Mock(spec=Engine)
    admin = Mock(spec=Engine)
    session.close.side_effect = OperationalError(
        "private-driver-detail", {}, RuntimeError("private-driver-detail")
    )
    drop = Mock(side_effect=RuntimeError("private-driver-detail"))
    monkeypatch.setattr(evaluation_database, "_drop_schema", drop)
    with pytest.raises(EvaluationDatabaseError) as caught:
        evaluation_database._cleanup(engine, admin, "eval_owned", {session})
    _assert_safe(caught.value)
    engine.dispose.assert_called_once_with()
    drop.assert_called_once_with(admin, "eval_owned")
    admin.dispose.assert_called_once_with()


def test_postgres_uses_separate_engines_and_a_private_search_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = Mock(spec=Engine)
    fixture = Mock(spec=Engine)
    fixture.dialect = Mock()
    fixture.dialect.name = "postgresql"
    transaction = MagicMock()
    connection = transaction.__enter__.return_value
    admin.begin.return_value = transaction
    create = Mock(side_effect=[admin, fixture])
    tables = Mock()
    monkeypatch.setattr(evaluation_database, "create_engine", create)
    monkeypatch.setattr(Base.metadata, "create_all", tables)
    with fixture_database("postgresql+psycopg://localhost/eval_test") as database:
        assert database.backend == "postgresql"
        assert _engine(database) is fixture
        tables.assert_called_once_with(fixture, tables=evaluation_database._TABLES)
        admin_options = create.call_args_list[0].kwargs["connect_args"]["options"]
        fixture_options = create.call_args_list[1].kwargs["connect_args"]["options"]
        assert "search_path" not in admin_options
        name = fixture_options.split("search_path=")[1]
        assert re.fullmatch(r"eval_[0-9a-f]{32}", name)
        assert str(connection.execute.call_args_list[0].args[0]) == (
            f'CREATE SCHEMA "{name}"'
        )
    assert str(connection.execute.call_args_list[1].args[0]) == (
        f'DROP SCHEMA "{name}" CASCADE'
    )
    assert admin.begin.call_count == 2
    fixture.dispose.assert_called_once_with()
    admin.dispose.assert_called_once_with()


@pytest.mark.parametrize("fail_create_schema", [False, True])
def test_postgres_setup_failures_clean_up_only_the_created_schema(
    monkeypatch: pytest.MonkeyPatch, fail_create_schema: bool
) -> None:
    admin = Mock(spec=Engine)
    transaction = MagicMock()
    connection = transaction.__enter__.return_value
    admin.begin.return_value = transaction
    failure = OperationalError(
        "private-driver-detail", {}, RuntimeError("private-driver-detail")
    )
    if fail_create_schema:
        connection.execute.side_effect = failure
    create = Mock(side_effect=[admin, failure])
    monkeypatch.setattr(evaluation_database, "create_engine", create)
    with pytest.raises(EvaluationDatabaseError) as caught:
        with fixture_database("postgresql+psycopg://localhost/eval_test"):
            pytest.fail("Failed setup entered the fixture context.")
    _assert_safe(caught.value)
    admin.dispose.assert_called_once_with()
    statements = [str(call.args[0]) for call in connection.execute.call_args_list]
    assert len(statements) == (1 if fail_create_schema else 2)
    assert re.fullmatch(r'CREATE SCHEMA "eval_[0-9a-f]{32}"', statements[0])
    if not fail_create_schema:
        name = statements[0].split('"')[1]
        assert statements[1] == f'DROP SCHEMA "{name}" CASCADE'


@pytest.fixture
def local_postgres() -> Iterator[Engine]:
    url = evaluation_database._validated_url(require_test_database_url())
    engine = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        yield engine
    finally:
        engine.dispose()


def _postgres_context(engine: Engine) -> AbstractContextManager[FixtureDatabase]:
    return fixture_database(engine.url.render_as_string(hide_password=False))


def _schema(database: FixtureDatabase) -> str:
    with database.factory() as session:
        name = session.scalar(text("SELECT current_schema()"))
        assert isinstance(name, str)
        assert re.fullmatch(r"eval_[0-9a-f]{32}", name)
        assert session.scalar(text("SHOW search_path")) == name
        return name


def _schema_exists(engine: Engine, name: str) -> bool:
    with engine.connect() as connection:
        return bool(
            connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :name)"
                ),
                {"name": name},
            )
        )


@pytest.mark.parametrize("abort", [False, True])
def test_postgres_schema_cleanup_and_public_row_preservation(
    local_postgres: Engine, abort: bool
) -> None:
    table = f"eval_sentinel_{uuid4().hex}"
    with local_postgres.begin() as connection:
        connection.execute(text(f'CREATE TABLE public."{table}" (value INTEGER)'))
        connection.execute(text(f'INSERT INTO public."{table}" VALUES (42)'))
    try:
        outcome = (
            pytest.raises(RuntimeError, match="caller failure")
            if abort
            else nullcontext()
        )
        with outcome:
            with _postgres_context(local_postgres) as database:
                name = _schema(database)
                assert database.backend == "postgresql"
                assert _schema_exists(local_postgres, name)
                assert set(inspect(_engine(database)).get_table_names()) == _TABLE_NAMES
                assert _user_ids(database) == []
                _seed_user(database)
                session = database.factory()
                session.execute(text("SELECT 1"))
                if abort:
                    raise RuntimeError("caller failure")
        assert not session.in_transaction()
        assert not _schema_exists(local_postgres, name)
        with local_postgres.connect() as connection:
            assert connection.scalar(text(f'SELECT value FROM public."{table}"')) == 42
    finally:
        with local_postgres.begin() as connection:
            connection.execute(text(f'DROP TABLE public."{table}"'))


def test_postgres_contexts_use_distinct_schemas(local_postgres: Engine) -> None:
    with _postgres_context(local_postgres) as first:
        first_name = _schema(first)
        _seed_user(first)
        with _postgres_context(local_postgres) as second:
            second_name = _schema(second)
            assert first_name != second_name
            assert _user_ids(second) == []
            _seed_user(second)
        assert not _schema_exists(local_postgres, second_name)
        assert _user_ids(first) == [1]
    assert not _schema_exists(local_postgres, first_name)


def test_postgres_setup_failure_removes_created_schema(
    local_postgres: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def fail_tables(engine: Engine, **kwargs: object) -> None:
        del kwargs
        with engine.connect() as connection:
            captured.append(str(connection.scalar(text("SELECT current_schema()"))))
        raise OperationalError("private-driver-detail", {}, RuntimeError())

    monkeypatch.setattr(Base.metadata, "create_all", fail_tables)
    with pytest.raises(EvaluationDatabaseError) as caught:
        with _postgres_context(local_postgres):
            pytest.fail("Failed table setup entered the fixture context.")
    _assert_safe(caught.value)
    assert len(captured) == 1
    assert not _schema_exists(local_postgres, captured[0])
