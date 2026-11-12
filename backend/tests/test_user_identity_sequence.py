"""Check user identity repair on isolated PostgreSQL."""

from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, text

from app.runtime_database_access import ADVANCE_USER_IDENTITY_SQL
from tests.conftest import require_test_database_url
from tests.test_runtime_database_access import _is_test_database, _safe_target

_SCRIPTS = Path(__file__).resolve().parents[1] / "alembic"


def _revision() -> ModuleType:
    revision = ScriptDirectory(str(_SCRIPTS)).get_revision("0013")
    assert revision is not None
    return revision.module


def test_identity_revision_is_forward_only() -> None:
    revision = _revision()
    assert revision.revision == "0013"
    assert revision.down_revision == "0012"
    with pytest.raises(RuntimeError, match="Forward-only migration"):
        revision.downgrade()


def test_migration_and_provisioning_use_the_same_repair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _revision()
    statements: list[str] = []
    monkeypatch.setattr(revision.op, "execute", statements.append)
    revision.upgrade()
    assert len(statements) == 1
    assert statements[0].split() == ADVANCE_USER_IDENTITY_SQL.split()


@pytest.fixture()
def migration_connection() -> Iterator[Connection]:
    options = _safe_target(require_test_database_url())
    engine = create_engine("postgresql+psycopg://", connect_args=options)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                database = connection.exec_driver_sql(
                    "SELECT current_database()"
                ).scalar_one()
                assert database == options["dbname"]
                superuser = connection.exec_driver_sql(
                    "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
                ).scalar_one()
                assert superuser is True
                databases = connection.exec_driver_sql(
                    "SELECT datname FROM pg_database WHERE datname NOT IN "
                    "('postgres', 'template0', 'template1')"
                ).scalars()
                assert all(
                    isinstance(name, str) and _is_test_database(name)
                    for name in databases
                ), "identity tests require a dedicated PostgreSQL server"
                connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
                connection.exec_driver_sql("SET LOCAL statement_timeout = '10s'")
                connection.exec_driver_sql("SELECT pg_advisory_xact_lock(782346921)")
                connection.exec_driver_sql("DROP SCHEMA public CASCADE")
                connection.exec_driver_sql("CREATE SCHEMA public")
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _upgrade(connection: Connection, target: str, base: str = "base") -> None:
    scripts = ScriptDirectory(str(_SCRIPTS))
    revisions = list(scripts.iterate_revisions(target, base))
    with Operations.context(MigrationContext.configure(connection)):
        for revision in reversed(revisions):
            revision.module.upgrade()


def _sequence_state(connection: Connection) -> tuple[int, bool]:
    query = connection.execute(
        text(
            "SELECT format('SELECT last_value, is_called FROM %s', "
            "pg_get_serial_sequence('public.users', 'id')::regclass)"
        )
    ).scalar_one()
    assert isinstance(query, str)
    row = connection.exec_driver_sql(query).one()
    assert isinstance(row[0], int) and isinstance(row[1], bool)
    return row[0], row[1]


def test_clean_upgrade_reserves_user_one(migration_connection: Connection) -> None:
    _upgrade(migration_connection, "0013")
    assert _sequence_state(migration_connection) == (1, True)
    generated = migration_connection.exec_driver_sql(
        "INSERT INTO public.users (display_name) VALUES ('Synthetic user') RETURNING id"
    ).scalar_one()
    assert generated == 2


@pytest.mark.parametrize(
    ("existing_ids", "sequence_value", "is_called", "rename_sequence"),
    [
        ((), 1, False, False),
        ((1,), 1, False, False),
        ((1, 987654321), 1, True, False),
        ((1, 987654321), 1000000000, True, False),
        ((1, 987654321), 1000000000, False, False),
        ((1, 987654321), 1, False, True),
        ((1, 987654321), 1000000000, True, True),
    ],
)
def test_upgrade_from_0012_preserves_rows_and_advances_identity(
    migration_connection: Connection,
    existing_ids: tuple[int, ...],
    sequence_value: int,
    is_called: bool,
    rename_sequence: bool,
) -> None:
    connection = migration_connection
    _upgrade(connection, "0012")
    for user_id in existing_ids:
        connection.exec_driver_sql(
            "INSERT INTO public.users (id, display_name) VALUES (%s, %s)",
            (user_id, "Synthetic imported user"),
        )
    if rename_sequence:
        query = connection.execute(
            text(
                "SELECT format('ALTER SEQUENCE %s RENAME TO %I', "
                "pg_get_serial_sequence('public.users', 'id')::regclass, "
                "'Imported User \"Sequence.with.dot')"
            )
        ).scalar_one()
        assert isinstance(query, str)
        connection.exec_driver_sql(query)
    connection.exec_driver_sql(
        "SELECT setval(pg_get_serial_sequence('public.users', 'id'), %s, %s)",
        (sequence_value, is_called),
    )
    before = connection.exec_driver_sql(
        "SELECT to_jsonb(u) FROM public.users u ORDER BY id"
    ).all()
    expected = max(1, sequence_value, *existing_ids)
    _upgrade(connection, "0013", "0012")
    assert _sequence_state(connection) == (expected, True)
    after = connection.exec_driver_sql(
        "SELECT to_jsonb(u) FROM public.users u ORDER BY id"
    ).all()
    assert after == before
    generated = connection.exec_driver_sql(
        "INSERT INTO public.users (display_name, auth_issuer, auth_subject) "
        "VALUES ('Synthetic JIT user', 'https://issuer.example', 'synthetic-subject') "
        "RETURNING id"
    ).scalar_one()
    assert generated == expected + 1
    assert generated > max(existing_ids, default=1)
