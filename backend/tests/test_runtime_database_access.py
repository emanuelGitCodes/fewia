import base64
import hashlib
import hmac
import re
from collections.abc import Iterator
from typing import cast
from unittest.mock import MagicMock

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.runtime_database_access import (
    RuntimeDatabaseAccessError,
    provision_runtime_access,
)
from app.runtime_database_policy import (
    RUNTIME_GRANTS,
    RUNTIME_ROLE,
    UNSAFE_ACCESS_SQL,
    UNSAFE_ROLE_SQL,
    validate_runtime_password,
)
from tests.conftest import require_test_database_url

PASSWORD = "A1" * 16
VERIFIER = b"SCRAM-SHA-256$4096:synthetic-test-verifier"


def make_connection(
    *, exists: bool = False, columns: tuple[tuple[str, str], ...] = ()
) -> MagicMock:
    connection = MagicMock()
    connection.info.dbname = "runtime_access_test"
    connection.pgconn.encrypt_password.return_value = VERIFIER

    def execute(query: str | sql.Composable) -> MagicMock:
        cursor = MagicMock()
        if query in (UNSAFE_ROLE_SQL, UNSAFE_ACCESS_SQL):
            cursor.fetchone.return_value = (False,)
        elif query == "SELECT 1 FROM pg_roles WHERE rolname = 'fewia_app'":
            cursor.fetchone.return_value = (1,) if exists else None
        cursor.fetchall.return_value = columns
        return cursor

    connection.execute.side_effect = execute
    return connection


def provision(connection: MagicMock, password: str = PASSWORD) -> None:
    provision_runtime_access(
        cast("psycopg.Connection[tuple[object, ...]]", connection), password
    )


def statements(connection: MagicMock) -> list[str]:
    return [
        query if isinstance(query := call.args[0], str) else query.as_string()
        for call in connection.execute.call_args_list
    ]


@pytest.mark.parametrize("exists", [False, True])
def test_provision_runtime_access_uses_fixed_role_and_grants(exists: bool) -> None:
    connection = make_connection(exists=exists, columns=(("users", "email"),))

    provision(connection)

    executed = statements(connection)
    role = sql.Identifier(RUNTIME_ROLE).as_string()
    assert executed[0] == "SELECT pg_advisory_xact_lock(782346921)"
    assert executed[1] == UNSAFE_ROLE_SQL
    assert sum(statement.startswith("CREATE ROLE ") for statement in executed) == (
        0 if exists else 1
    )
    if not exists:
        assert (
            f"CREATE ROLE {role} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
            "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
        ) in executed
    connection.pgconn.encrypt_password.assert_called_once_with(
        validate_runtime_password(PASSWORD).encode("ascii"),
        RUNTIME_ROLE.encode("ascii"),
        b"scram-sha-256",
    )
    assert f"ALTER ROLE {role} LOGIN PASSWORD '{VERIFIER.decode('ascii')}'" in executed
    assert f'REVOKE ALL ON DATABASE "runtime_access_test" FROM {role}' in executed
    assert f"REVOKE ALL ON SCHEMA public FROM {role}" in executed
    for kind in ("TABLES", "SEQUENCES"):
        assert f"REVOKE ALL ON ALL {kind} IN SCHEMA public FROM {role}" in executed
    assert f'REVOKE ALL ("email") ON TABLE "public"."users" FROM {role}' in executed
    expected_grants = [
        f'GRANT CONNECT ON DATABASE "runtime_access_test" TO {role}',
        f"GRANT USAGE ON SCHEMA public TO {role}",
        *[
            f"GRANT {privileges} ON TABLE "
            f"{sql.Identifier('public', table).as_string()} TO {role}"
            for table, privileges in RUNTIME_GRANTS.items()
        ],
    ]
    assert executed[executed.index(UNSAFE_ACCESS_SQL) + 1 :] == expected_grants
    assert all(PASSWORD not in statement for statement in executed)
    connection.transaction.assert_called_once_with()
    connection.transaction.return_value.__exit__.assert_called_once_with(
        None, None, None
    )


@pytest.mark.parametrize("password", ["", "A" * 31, "A" * 33, "!" * 32, "é" * 32])
def test_invalid_password_does_not_touch_database(password: str) -> None:
    connection = make_connection()

    with pytest.raises(ValueError, match="runtime database password is invalid"):
        provision(connection, password)

    connection.transaction.assert_not_called()
    connection.execute.assert_not_called()
    connection.pgconn.encrypt_password.assert_not_called()


@pytest.mark.parametrize("unsafe_query", [UNSAFE_ROLE_SQL, UNSAFE_ACCESS_SQL])
@pytest.mark.parametrize("result", [(True,), None])
def test_unsafe_or_missing_policy_result_fails_closed(
    unsafe_query: str, result: tuple[bool] | None
) -> None:
    connection = make_connection()
    execute = connection.execute.side_effect

    def unsafe_execute(query: str | sql.Composable) -> MagicMock:
        cursor = execute(query)
        if query == unsafe_query:
            cursor.fetchone.return_value = result
        return cast(MagicMock, cursor)

    connection.execute.side_effect = unsafe_execute

    with pytest.raises(RuntimeDatabaseAccessError) as error:
        provision(connection)

    assert str(error.value) == "runtime database access provisioning failed"
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    assert not any(
        statement.startswith("GRANT ") for statement in statements(connection)
    )
    if unsafe_query == UNSAFE_ROLE_SQL:
        connection.pgconn.encrypt_password.assert_not_called()
    assert connection.transaction.return_value.__exit__.call_args.args[0] is (
        RuntimeDatabaseAccessError
    )


def test_encryption_failure_does_not_send_plaintext_or_change_role() -> None:
    connection = make_connection()
    connection.pgconn.encrypt_password.return_value = PASSWORD.encode("ascii")

    with pytest.raises(RuntimeDatabaseAccessError) as error:
        provision(connection)

    assert str(error.value) == "runtime database access provisioning failed"
    assert all(PASSWORD not in statement for statement in statements(connection))
    assert not any(
        statement.startswith(("CREATE ROLE ", "ALTER ROLE "))
        for statement in statements(connection)
    )


def test_database_failure_hides_password_and_driver_error() -> None:
    connection = make_connection()
    connection.execute.side_effect = psycopg.OperationalError(PASSWORD)

    with pytest.raises(RuntimeDatabaseAccessError) as error:
        provision(connection)

    assert str(error.value) == "runtime database access provisioning failed"
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    assert PASSWORD not in str(error.value)
    assert connection.transaction.return_value.__exit__.call_args.args[0] is (
        psycopg.OperationalError
    )


def test_encryption_exception_is_static_and_rolls_back() -> None:
    connection = make_connection()
    connection.pgconn.encrypt_password.side_effect = AttributeError(PASSWORD)
    with pytest.raises(RuntimeDatabaseAccessError) as caught:
        provision(connection)
    _assert_static_error(caught.value)
    assert (
        connection.transaction.return_value.__exit__.call_args.args[0] is AttributeError
    )
    assert all(s.lstrip().startswith("SELECT") for s in statements(connection))


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_process_interrupt_propagates(exception: type[BaseException]) -> None:
    connection = make_connection()
    connection.execute.side_effect = exception()
    with pytest.raises(exception):
        provision(connection)
    assert connection.transaction.return_value.__exit__.call_args.args[0] is exception


PgConnection = psycopg.Connection[tuple[object, ...]]
_DATABASE = "fewia_eval_runtime_database_provisioning"
_TEST_ROLES = (RUNTIME_ROLE, "fewia_eval_member", "fewia_eval_role_admin")
_LEGACY_TABLES = (
    "daily_finance",
    "daily_environment",
    "daily_health",
    "model_runs",
    "predictions",
    "alembic_version",
)
_TABLE_GRANTS: dict[str, frozenset[str]] = {
    **{
        table: frozenset(grants.split(", ")) for table, grants in RUNTIME_GRANTS.items()
    },
    **{table: frozenset[str]() for table in _LEGACY_TABLES},
}
_PRIVILEGES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)
_COLUMN_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "REFERENCES"}


def _is_test_database(database: str) -> bool:
    return re.fullmatch(r"fewia_eval(?:_[A-Za-z0-9_]+)?", database) is not None


def _safe_target(url_text: str) -> dict[str, str | int]:
    try:
        url = make_url(url_text)
        port = url.port
    except (ArgumentError, ValueError):
        raise ValueError("runtime role test database target is unsafe") from None
    if (
        url.get_backend_name() != "postgresql"
        or url.database is None
        or not _is_test_database(url.database)
        or url.host not in {"localhost", "127.0.0.1", "::1", None}
        or (port is not None and not 1 <= port <= 65535)
        or url.query
    ):
        raise ValueError("runtime role test database target is unsafe")
    options: dict[str, str | int] = {
        "dbname": url.database,
        "host": url.host or "/tmp",
        "connect_timeout": 5,
    }
    if url.username is not None:
        options["user"] = url.username
    if url.password is not None:
        options["password"] = url.password
    if port is not None:
        options["port"] = port
    return options


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/fewia",
        "postgresql://127.0.0.1:55447/postgres",
        "postgresql://localhost/fewia_eval_",
        "postgresql://localhost/fewia_evaltest",
        "postgresql://localhost/fewia_evaluation",
        "postgresql://localhost/other_fewia_eval_test",
        "postgresql://localhost/fewia_eval_tést",
        "postgresql://localhost/fewia_eval_１２",
        "postgresql://localhost/fewia_eval_test-other",
        "postgresql://localhost/fewia_eval_test/other",
        "postgresql://localhost/fewia_eval_test\n",
        f"postgresql://remote:55447/{_DATABASE}",
        "postgresql://remote/fewia_eval",
        "postgresql://127.0.0.2/fewia_eval_test",
        "postgresql://localhost:invalid/fewia_eval",
        "postgresql://localhost:0/fewia_eval",
        "postgresql://localhost:-1/fewia_eval",
        "postgresql://localhost:65536/fewia_eval",
        "postgresql://localhost/",
        "postgresql://localhost/fewia_eval?host=remote",
        "postgresql://localhost/fewia_eval?dbname=postgres",
        f"postgresql://127.0.0.1:55447/{_DATABASE}?host=remote",
        f"sqlite:///{_DATABASE}",
        "not a database URL",
    ],
)
def test_postgres_target_rejects_unsafe_database(url: str) -> None:
    with pytest.raises(
        ValueError, match="^runtime role test database target is unsafe$"
    ):
        _safe_target(url)


def test_postgres_target_accepts_assigned_endpoint() -> None:
    assert _safe_target(f"postgresql://127.0.0.1:55447/{_DATABASE}") == {
        "dbname": _DATABASE,
        "host": "127.0.0.1",
        "port": 55447,
        "connect_timeout": 5,
    }


@pytest.mark.parametrize(
    "database",
    ["fewia_eval", "fewia_eval_test", "fewia_eval_Runtime_42_provisioning"],
)
@pytest.mark.parametrize(
    ("authority", "host", "port"),
    [
        ("localhost", "localhost", None),
        ("localhost:5432", "localhost", 5432),
        ("127.0.0.1:55447", "127.0.0.1", 55447),
        ("[::1]", "::1", None),
        ("[::1]:5432", "::1", 5432),
        ("", "/tmp", None),
    ],
)
def test_postgres_target_accepts_local_test_database(
    database: str, authority: str, host: str, port: int | None
) -> None:
    expected: dict[str, str | int] = {
        "dbname": database,
        "host": host,
        "connect_timeout": 5,
    }
    if port is not None:
        expected["port"] = port
    assert _safe_target(f"postgresql://{authority}/{database}") == expected


@pytest.fixture()
def admin() -> Iterator[PgConnection]:
    options = _safe_target(require_test_database_url())
    with psycopg.connect(**options, autocommit=True) as connection:
        assert connection.info.dbname == options["dbname"]
        assert connection.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone() == (True,), "runtime role tests require a disposable superuser"
        assert connection.execute(
            "SELECT datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user) "
            "FROM pg_database WHERE datname = current_database()"
        ).fetchone() == (True,), "runtime role tests require the task database owner"
        assert all(
            _is_test_database(cast(str, row[0]))
            for row in connection.execute(
                "SELECT datname FROM pg_database WHERE datname NOT IN "
                "('postgres', 'template0', 'template1')"
            ).fetchall()
        ), "runtime role tests require an isolated PostgreSQL server"
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout = '5s'")
            connection.execute("SET LOCAL statement_timeout = '10s'")
            connection.execute("SELECT pg_advisory_xact_lock(782346921)")
            assert (
                connection.execute(
                    "SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)",
                    (list(_TEST_ROLES),),
                ).fetchone()
                is None
            ), "runtime role tests require absent test roles"
            original = _catalog(connection)
            for table in _TABLE_GRANTS:
                assert connection.execute(
                    "SELECT to_regclass(%s)", ("public." + table,)
                ).fetchone() != (None,), "runtime role tests require migrated tables"
            assert connection.execute(
                "SELECT count(*) FROM public.alembic_version"
            ).fetchone() == (1,), "runtime role tests require a migration revision"
            assert connection.execute(
                "SELECT 1 FROM pg_trigger WHERE tgrelid = "
                "'public.grocery_evidence'::regclass "
                "AND tgname = 'fewia_grocery_evidence_immutable' AND tgenabled = 'O'"
            ).fetchone() == (1,), "runtime role tests require the evidence trigger"
            connection.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(connection.info.dbname)
                )
            )
            connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            connection.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC")
            connection.execute(
                "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC"
            )
            try:
                yield connection
            finally:
                raise psycopg.Rollback()
        assert (
            connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (list(_TEST_ROLES),)
            ).fetchone()
            is None
        ), "runtime role tests MUST roll back test roles"
        assert _catalog(connection) == original


class RecordingConnection:
    def __init__(self, connection: PgConnection, *, fail: bool = False) -> None:
        self.connection = connection
        self.pgconn = connection.pgconn
        self.info = connection.info
        self.statements: list[str] = []
        self.fail = fail

    def transaction(self) -> psycopg.Transaction:
        return self.connection.transaction()

    def execute(
        self, query: str | sql.Composable
    ) -> psycopg.Cursor[tuple[object, ...]]:
        rendered = query if isinstance(query, str) else query.as_string(self.connection)
        self.statements.append(rendered)
        if (
            self.fail
            and rendered.startswith("GRANT")
            and "shopping_handoffs" in rendered
        ):
            self.connection.execute("SELECT 1 / 0")
        return self.connection.execute(query)


def _create_role(connection: PgConnection) -> None:
    connection.execute(
        "CREATE ROLE fewia_app LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )


def _rows(connection: PgConnection) -> dict[str, list[tuple[object, ...]]]:
    return {
        table: connection.execute(
            sql.SQL("SELECT to_jsonb(t)::text FROM {} AS t ORDER BY 1").format(
                sql.Identifier("public", table)
            )
        ).fetchall()
        for table in _TABLE_GRANTS
    }


def _catalog(connection: PgConnection) -> list[list[tuple[object, ...]]]:
    queries = (
        "SELECT * FROM pg_authid WHERE rolname = 'fewia_app'",
        "SELECT datdba, datacl::text FROM pg_database "
        "WHERE datname = current_database()",
        "SELECT oid, nspowner, nspacl::text FROM pg_namespace ORDER BY oid",
        "SELECT oid, relowner, relacl::text FROM pg_class ORDER BY oid",
        "SELECT attrelid, attnum, attacl::text FROM pg_attribute "
        "WHERE attacl IS NOT NULL ORDER BY attrelid, attnum",
        "SELECT oid, proowner, proacl::text, prosecdef FROM pg_proc ORDER BY oid",
        "SELECT oid, typowner FROM pg_type ORDER BY oid",
        "SELECT roleid, member, admin_option FROM pg_auth_members "
        "ORDER BY roleid, member",
        "SELECT oid, defaclrole, defaclnamespace, defaclobjtype, defaclacl::text "
        "FROM pg_default_acl ORDER BY oid",
    )
    return [connection.execute(query).fetchall() for query in queries]


def _assert_static_error(error: RuntimeDatabaseAccessError) -> None:
    assert str(error) == "runtime database access provisioning failed"
    assert repr(error) == (
        "RuntimeDatabaseAccessError('runtime database access provisioning failed')"
    )
    assert error.__cause__ is None
    assert error.__context__ is None


def _assert_privileges(connection: PgConnection) -> None:
    privileges = (
        (*_PRIVILEGES, "MAINTAIN")
        if connection.info.server_version >= 170000
        else _PRIVILEGES
    )
    tables = connection.execute(
        "SELECT c.relname FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')"
    ).fetchall()
    for (table,) in tables:
        allowed = _TABLE_GRANTS.get(str(table), frozenset())
        for privilege in privileges:
            for suffix in ("", " WITH GRANT OPTION"):
                assert connection.execute(
                    "SELECT has_table_privilege('fewia_app', %s, %s)",
                    ("public." + str(table), privilege + suffix),
                ).fetchone() == (privilege in allowed and not suffix,)
                if privilege in _COLUMN_PRIVILEGES:
                    assert connection.execute(
                        "SELECT has_any_column_privilege('fewia_app', %s, %s)",
                        ("public." + str(table), privilege + suffix),
                    ).fetchone() == (privilege in allowed and not suffix,)
    for privilege in ("CONNECT", "CREATE", "TEMPORARY"):
        for suffix in ("", " WITH GRANT OPTION"):
            assert connection.execute(
                "SELECT has_database_privilege('fewia_app', current_database(), %s)",
                (privilege + suffix,),
            ).fetchone() == (privilege == "CONNECT" and not suffix,)
    for privilege in ("USAGE", "CREATE"):
        for suffix in ("", " WITH GRANT OPTION"):
            assert connection.execute(
                "SELECT has_schema_privilege('fewia_app', 'public', %s)",
                (privilege + suffix,),
            ).fetchone() == (privilege == "USAGE" and not suffix,)
    assert (
        connection.execute(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND CASE WHEN c.relkind = 'S' "
            "THEN has_sequence_privilege('fewia_app', c.oid, 'SELECT, USAGE, UPDATE') "
            "ELSE false END"
        ).fetchone()
        is None
    )
    assert connection.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
    assert connection.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)


def _seed_direct_acl(connection: PgConnection) -> None:
    connection.execute(
        sql.SQL("GRANT ALL ON DATABASE {} TO fewia_app WITH GRANT OPTION").format(
            sql.Identifier(connection.info.dbname)
        )
    )
    connection.execute("GRANT ALL ON SCHEMA public TO fewia_app WITH GRANT OPTION")
    for kind in ("TABLES", "SEQUENCES"):
        connection.execute(
            sql.SQL(
                "GRANT ALL ON ALL {} IN SCHEMA public TO fewia_app WITH GRANT OPTION"
            ).format(sql.SQL(kind))
        )
    connection.execute("GRANT UPDATE (display_name) ON users TO fewia_app")
    connection.execute(
        "GRANT SELECT (display_name) ON users TO fewia_app WITH GRANT OPTION"
    )


def _assert_password(connection: PgConnection, password: str) -> str:
    row = connection.execute(
        "SELECT rolpassword FROM pg_authid WHERE rolname = 'fewia_app'"
    ).fetchone()
    assert row is not None and isinstance(row[0], str)
    verifier = row[0]
    algorithm, parameters, keys = verifier.split("$")
    assert algorithm == "SCRAM-SHA-256"
    iterations, salt = parameters.split(":")
    stored_key, server_key = keys.split(":")
    salted = hashlib.pbkdf2_hmac(
        "sha256", password.encode("ascii"), base64.b64decode(salt), int(iterations)
    )
    client_key = hmac.digest(salted, b"Client Key", "sha256")
    assert hashlib.sha256(client_key).digest() == base64.b64decode(stored_key)
    assert hmac.digest(salted, b"Server Key", "sha256") == base64.b64decode(server_key)
    return verifier


def _other_role_acl(connection: PgConnection) -> list[tuple[object, ...]]:
    return connection.execute(
        "WITH a AS ("
        "SELECT 'database' AS kind, oid AS object_id, 0 AS column_id, datacl AS acl "
        "FROM pg_database WHERE datname = current_database() UNION ALL "
        "SELECT 'schema', oid, 0, nspacl FROM pg_namespace UNION ALL "
        "SELECT 'relation', oid, 0, relacl FROM pg_class UNION ALL "
        "SELECT 'column', attrelid, attnum, attacl FROM pg_attribute) "
        "SELECT kind, object_id, column_id, p.grantor, "
        "p.privilege_type, p.is_grantable "
        "FROM a CROSS JOIN LATERAL aclexplode(a.acl) p "
        "WHERE p.grantee = "
        "(SELECT oid FROM pg_roles WHERE rolname = 'fewia_eval_member') "
        "ORDER BY kind, object_id, column_id, p.privilege_type"
    ).fetchall()


def test_postgres_create_repeat_reset_rotate_and_preserve_rows(
    admin: PgConnection,
) -> None:
    admin.execute(
        "INSERT INTO users (id, display_name) VALUES (987654321, 'Role test')"
    )
    admin.execute("CREATE ROLE fewia_eval_member NOLOGIN")
    admin.execute("GRANT SELECT ON users TO fewia_eval_member WITH GRANT OPTION")
    admin.execute("GRANT UPDATE (display_name) ON users TO fewia_eval_member")
    admin.execute("GRANT USAGE ON SCHEMA public TO fewia_eval_member")
    admin.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO fewia_eval_member")
    admin.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO fewia_eval_member").format(
            sql.Identifier(admin.info.dbname)
        )
    )
    before = _rows(admin)
    unrelated = _other_role_acl(admin)
    recording = RecordingConnection(admin)
    connection = cast(PgConnection, recording)
    provision_runtime_access(connection, PASSWORD)
    _assert_privileges(admin)
    assert admin.execute(
        "SELECT rolcanlogin, rolinherit, rolsuper, rolcreatedb, rolcreaterole, "
        "rolreplication, rolbypassrls FROM pg_roles WHERE rolname = 'fewia_app'"
    ).fetchone() == (True, False, False, False, False, False, False)
    first = _assert_password(admin, PASSWORD)
    provision_runtime_access(connection, PASSWORD)
    _assert_privileges(admin)
    _assert_password(admin, PASSWORD)
    _seed_direct_acl(admin)
    assert admin.execute(
        "SELECT has_column_privilege('fewia_app', 'public.users', 'display_name', "
        "'UPDATE'), has_column_privilege('fewia_app', 'public.users', 'display_name', "
        "'SELECT WITH GRANT OPTION')"
    ).fetchone() == (True, True)
    rotated = "B2" * 16
    provision_runtime_access(connection, rotated)
    _assert_privileges(admin)
    assert _assert_password(admin, rotated) != first
    assert (
        admin.execute(
            "SELECT 1 FROM pg_attribute a CROSS JOIN LATERAL aclexplode(a.attacl) acl "
            "WHERE acl.grantee = (SELECT oid FROM pg_roles WHERE rolname = 'fewia_app')"
        ).fetchone()
        is None
    )
    assert (
        admin.execute(
            "SELECT 1 FROM pg_default_acl WHERE defaclrole = "
            "(SELECT oid FROM pg_roles WHERE rolname = 'fewia_app')"
        ).fetchone()
        is None
    )
    assert _rows(admin) == before
    assert _other_role_acl(admin) == unrelated
    assert (
        sum(s.startswith('CREATE ROLE "fewia_app"') for s in recording.statements) == 1
    )
    assert all(PASSWORD not in s and rotated not in s for s in recording.statements)
    assert any("SCRAM-SHA-256$" in s for s in recording.statements)


@pytest.mark.parametrize("existing", [False, True])
def test_postgres_late_sql_failure_rolls_back_all_changes(
    admin: PgConnection, existing: bool
) -> None:
    if existing:
        provision_runtime_access(admin, PASSWORD)
        _seed_direct_acl(admin)
    before, rows = _catalog(admin), _rows(admin)
    recording = RecordingConnection(admin, fail=True)
    with pytest.raises(RuntimeDatabaseAccessError) as caught:
        provision_runtime_access(cast(PgConnection, recording), PASSWORD)
    _assert_static_error(caught.value)
    assert any(
        "shopping_handoffs" in s and s.startswith("GRANT") for s in recording.statements
    )
    assert _catalog(admin) == before
    assert _rows(admin) == rows
    assert all(PASSWORD not in s for s in recording.statements)


@pytest.mark.parametrize(
    "change",
    [
        "ALTER ROLE fewia_app INHERIT",
        "ALTER ROLE fewia_app SUPERUSER",
        "ALTER ROLE fewia_app CREATEDB",
        "ALTER ROLE fewia_app CREATEROLE",
        "ALTER ROLE fewia_app REPLICATION",
        "ALTER ROLE fewia_app BYPASSRLS",
        "GRANT fewia_eval_member TO fewia_app",
        "GRANT fewia_eval_member TO fewia_app WITH ADMIN OPTION",
        "ALTER TABLE jobs OWNER TO fewia_app",
        "ALTER SCHEMA public OWNER TO fewia_app",
        "database_owner",
        "sequence_owner",
        "function_owner",
        "type_owner",
    ],
)
def test_postgres_unsafe_role_is_unchanged(admin: PgConnection, change: str) -> None:
    provision_runtime_access(admin, PASSWORD)
    admin.execute("CREATE ROLE fewia_eval_member NOLOGIN")
    _seed_direct_acl(admin)
    if change == "database_owner":
        admin.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO fewia_app").format(
                sql.Identifier(admin.info.dbname)
            )
        )
    elif change == "sequence_owner":
        admin.execute("CREATE SEQUENCE public.fewia_eval_owned")
        admin.execute("ALTER SEQUENCE public.fewia_eval_owned OWNER TO fewia_app")
    elif change == "function_owner":
        admin.execute(
            "CREATE FUNCTION public.fewia_eval_owned() RETURNS integer "
            "LANGUAGE sql AS 'SELECT 1'"
        )
        admin.execute("ALTER FUNCTION public.fewia_eval_owned() OWNER TO fewia_app")
    elif change == "type_owner":
        admin.execute("CREATE TYPE public.fewia_eval_owned AS ENUM ('fixture')")
        admin.execute("ALTER TYPE public.fewia_eval_owned OWNER TO fewia_app")
    else:
        admin.execute(change)
    before = _catalog(admin)
    recording = RecordingConnection(admin)
    with pytest.raises(RuntimeDatabaseAccessError) as caught:
        provision_runtime_access(cast(PgConnection, recording), "B2" * 16)
    _assert_static_error(caught.value)
    assert all(s.lstrip().startswith("SELECT") for s in recording.statements)
    assert _catalog(admin) == before


@pytest.mark.parametrize("admin_option", [False, True])
def test_postgres_incoming_membership_is_preserved(
    admin: PgConnection, admin_option: bool
) -> None:
    _create_role(admin)
    admin.execute("CREATE ROLE fewia_eval_member NOLOGIN")
    admin.execute(
        "GRANT fewia_app TO fewia_eval_member"
        + (" WITH ADMIN OPTION" if admin_option else "")
    )
    provision_runtime_access(admin, PASSWORD)
    _assert_privileges(admin)
    assert admin.execute(
        "SELECT m.admin_option FROM pg_auth_members m "
        "JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles u ON u.oid = m.member "
        "WHERE r.rolname = 'fewia_app' AND u.rolname = 'fewia_eval_member'"
    ).fetchone() == (admin_option,)


def test_postgres_non_superuser_creator_with_admin_option(admin: PgConnection) -> None:
    if admin.info.server_version < 160000:
        pytest.skip("automatic creator ADMIN OPTION requires PostgreSQL 16")
    admin.execute(
        "CREATE ROLE fewia_eval_role_admin NOLOGIN NOINHERIT NOSUPERUSER "
        "CREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS"
    )
    admin.execute(
        sql.SQL(
            "GRANT ALL ON DATABASE {} TO fewia_eval_role_admin WITH GRANT OPTION"
        ).format(sql.Identifier(admin.info.dbname))
    )
    admin.execute(
        "GRANT ALL ON SCHEMA public TO fewia_eval_role_admin WITH GRANT OPTION"
    )
    for kind in ("TABLES", "SEQUENCES"):
        admin.execute(
            sql.SQL(
                "GRANT ALL ON ALL {} IN SCHEMA public "
                "TO fewia_eval_role_admin WITH GRANT OPTION"
            ).format(sql.SQL(kind))
        )
    with admin.transaction():
        admin.execute("SET LOCAL ROLE fewia_eval_role_admin")
        assert admin.execute(
            "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ).fetchone() == (False, True)
        provision_runtime_access(admin, PASSWORD)
        provision_runtime_access(admin, "B2" * 16)
        assert admin.execute(
            "SELECT m.admin_option FROM pg_auth_members m "
            "JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles u ON u.oid = m.member "
            "WHERE r.rolname = 'fewia_app' AND u.rolname = current_user"
        ).fetchone() == (True,)
        admin.execute("RESET ROLE")
    _assert_privileges(admin)
    _assert_password(admin, "B2" * 16)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "grant",
    [
        "GRANT CREATE ON SCHEMA public TO PUBLIC",
        "GRANT SELECT ON daily_health TO PUBLIC",
        "GRANT UPDATE ON grocery_evidence TO PUBLIC",
        "GRANT INSERT ON plaid_items TO PUBLIC",
        "GRANT UPDATE (display_name) ON users TO PUBLIC",
        "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO PUBLIC",
        "database_create",
        "database_temp",
        "custom_table",
        "custom_sequence",
    ],
)
def test_postgres_excess_effective_access_refuses_and_rolls_back(
    admin: PgConnection, existing: bool, grant: str
) -> None:
    if existing:
        provision_runtime_access(admin, PASSWORD)
        _seed_direct_acl(admin)
    if grant in {"database_create", "database_temp"}:
        privilege = "CREATE" if grant == "database_create" else "TEMPORARY"
        admin.execute(
            sql.SQL("GRANT {} ON DATABASE {} TO PUBLIC").format(
                sql.SQL(privilege), sql.Identifier(admin.info.dbname)
            )
        )
    elif grant in {"custom_table", "custom_sequence"}:
        admin.execute("CREATE SCHEMA fewia_eval_extra")
        admin.execute("GRANT USAGE ON SCHEMA fewia_eval_extra TO PUBLIC")
        if grant == "custom_table":
            admin.execute("CREATE TABLE fewia_eval_extra.users (id integer)")
            admin.execute("GRANT SELECT ON fewia_eval_extra.users TO PUBLIC")
        else:
            admin.execute("CREATE SEQUENCE fewia_eval_extra.denied")
            admin.execute("GRANT USAGE ON SEQUENCE fewia_eval_extra.denied TO PUBLIC")
    else:
        admin.execute(grant)
    before, rows = _catalog(admin), _rows(admin)
    recording = RecordingConnection(admin)
    with pytest.raises(RuntimeDatabaseAccessError) as caught:
        provision_runtime_access(cast(PgConnection, recording), "B2" * 16)
    _assert_static_error(caught.value)
    assert UNSAFE_ACCESS_SQL in recording.statements
    assert any(s.startswith("REVOKE") for s in recording.statements)
    assert not any(s.startswith("GRANT") for s in recording.statements)
    assert _catalog(admin) == before
    assert _rows(admin) == rows


def test_postgres_public_column_grant_option_refuses_and_restores_acl(
    admin: PgConnection,
) -> None:
    provision_runtime_access(admin, PASSWORD)
    _seed_direct_acl(admin)
    admin.execute(
        "UPDATE pg_attribute SET attacl = array_append(attacl, "
        "makeaclitem(0, (SELECT oid FROM pg_roles WHERE rolname = current_user), "
        "'SELECT', true)) "
        "WHERE attrelid = 'public.users'::regclass AND attname = 'display_name'"
    )
    assert admin.execute(
        "SELECT acl.privilege_type, acl.is_grantable FROM pg_attribute a "
        "CROSS JOIN LATERAL aclexplode(a.attacl) acl "
        "WHERE a.attrelid = 'public.users'::regclass "
        "AND a.attname = 'display_name' AND acl.grantee = 0"
    ).fetchall() == [("SELECT", True)]
    before = _catalog(admin)
    with pytest.raises(RuntimeDatabaseAccessError) as caught:
        provision_runtime_access(admin, "B2" * 16)
    _assert_static_error(caught.value)
    assert _catalog(admin) == before


@pytest.mark.parametrize("schema", ["public", "fewia_eval_extra"])
@pytest.mark.parametrize("kind", ["FUNCTION", "PROCEDURE"])
@pytest.mark.parametrize("recipient", ["PUBLIC", "fewia_app"])
def test_postgres_executable_definer_refuses_and_rolls_back(
    admin: PgConnection, schema: str, kind: str, recipient: str
) -> None:
    provision_runtime_access(admin, PASSWORD)
    if schema != "public":
        admin.execute("CREATE SCHEMA fewia_eval_extra")
        admin.execute("GRANT USAGE ON SCHEMA fewia_eval_extra TO PUBLIC")
    routine = sql.Identifier(schema, "fewia_eval_routine")
    if kind == "FUNCTION":
        admin.execute(
            sql.SQL(
                "CREATE FUNCTION {}() RETURNS bigint LANGUAGE sql SECURITY DEFINER "
                "AS 'SELECT count(*) FROM public.daily_health'"
            ).format(routine)
        )
    else:
        admin.execute(
            sql.SQL(
                "CREATE PROCEDURE {}() LANGUAGE plpgsql SECURITY DEFINER "
                "AS 'BEGIN PERFORM count(*) FROM public.daily_health; END;'"
            ).format(routine)
        )
    if recipient != "PUBLIC":
        admin.execute(
            sql.SQL("REVOKE EXECUTE ON {} {}() FROM PUBLIC").format(
                sql.SQL(kind), routine
            )
        )
        admin.execute(
            sql.SQL("GRANT EXECUTE ON {} {}() TO fewia_app").format(
                sql.SQL(kind), routine
            )
        )
    with admin.transaction():
        admin.execute("SET LOCAL ROLE fewia_app")
        admin.execute(
            sql.SQL("SELECT {}()" if kind == "FUNCTION" else "CALL {}()").format(
                routine
            )
        )
        admin.execute("RESET ROLE")
    _seed_direct_acl(admin)
    before, rows = _catalog(admin), _rows(admin)
    with pytest.raises(RuntimeDatabaseAccessError) as caught:
        provision_runtime_access(admin, "B2" * 16)
    _assert_static_error(caught.value)
    assert _catalog(admin) == before
    assert _rows(admin) == rows


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.fewia_eval_forbidden (id integer)",
        "CREATE TEMP TABLE fewia_eval_forbidden (id integer)",
        "ALTER TABLE users ADD COLUMN fewia_eval_forbidden integer",
        "SELECT * FROM daily_health",
        "SELECT * FROM alembic_version",
        "DELETE FROM jobs",
        "UPDATE grocery_evidence SET snapshot = '{}'::json",
        "DELETE FROM grocery_evidence",
        "UPDATE plaid_items SET cursor = NULL",
        "DELETE FROM plaid_transactions",
        "TRUNCATE users",
        "SELECT nextval(pg_get_serial_sequence('users', 'id'))",
    ],
)
def test_postgres_runtime_forbidden_operations(
    admin: PgConnection, statement: str
) -> None:
    provision_runtime_access(admin, PASSWORD)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with admin.transaction():
            admin.execute("SET LOCAL ROLE fewia_app")
            admin.execute(statement)


def test_postgres_active_writes_and_evidence_trigger_survive_provisioning(
    admin: PgConnection,
) -> None:
    admin.execute(
        "INSERT INTO users (id, display_name) VALUES (987654321, 'Role test')"
    )
    trigger_query = (
        "SELECT pg_get_triggerdef(oid), tgenabled, "
        "(SELECT proname FROM pg_proc WHERE oid = tgfoid) FROM pg_trigger "
        "WHERE tgrelid = 'public.grocery_evidence'::regclass "
        "AND tgname = 'fewia_grocery_evidence_immutable'"
    )
    trigger_before = admin.execute(trigger_query).fetchone()
    assert trigger_before is not None
    assert isinstance(trigger_before[2], str)
    provision_runtime_access(admin, PASSWORD)
    with admin.transaction():
        admin.execute("SET LOCAL ROLE fewia_app")
        assert admin.execute(
            "SELECT display_name FROM users WHERE id = 987654321"
        ).fetchone() == ("Role test",)
        admin.execute(
            "INSERT INTO jobs (id, user_id, kind, request_key, payload) "
            "VALUES ('role-test-job', 987654321, 'agent', 'role-test', '{}')"
        )
        admin.execute("UPDATE jobs SET status = 'running' WHERE id = 'role-test-job'")
        admin.execute(
            "INSERT INTO job_outbox (id, job_id) "
            "VALUES ('role-test-outbox', 'role-test-job')"
        )
        admin.execute(
            "UPDATE job_outbox SET published_at = now() WHERE id = 'role-test-outbox'"
        )
        admin.execute(
            "INSERT INTO shopping_handoffs "
            "(id, user_id, request_hash, request_payload) "
            "VALUES ('role-test-handoff', 987654321, 'role-test', '{}')"
        )
        admin.execute(
            "UPDATE shopping_handoffs SET attempts = 1 WHERE id = 'role-test-handoff'"
        )
        admin.execute(
            "INSERT INTO grocery_evidence (id, user_id, snapshot) VALUES (%s, %s, %s)",
            ("a" * 64, 987654321, "{}"),
        )
        for table in RUNTIME_GRANTS:
            admin.execute(
                sql.SQL("SELECT * FROM {}").format(sql.Identifier("public", table))
            )
        admin.execute("RESET ROLE")
    before = _rows(admin)
    provision_runtime_access(admin, PASSWORD)
    assert _rows(admin) == before
    assert admin.execute(trigger_query).fetchone() == trigger_before
    for statement in (
        "UPDATE grocery_evidence SET snapshot = snapshot WHERE id = %s",
        "DELETE FROM grocery_evidence WHERE id = %s",
    ):
        with pytest.raises(psycopg.Error) as caught:
            with admin.transaction():
                admin.execute(statement, ("a" * 64,))
        assert caught.value.sqlstate != "42501"
        assert trigger_before[2] in (caught.value.diag.context or "")
        assert _rows(admin) == before


def test_postgres_future_objects_have_no_default_access(admin: PgConnection) -> None:
    provision_runtime_access(admin, PASSWORD)
    defaults_before = admin.execute(
        "SELECT * FROM pg_default_acl ORDER BY oid"
    ).fetchall()
    admin.execute("CREATE TABLE public.fewia_eval_future (id integer)")
    admin.execute("CREATE SEQUENCE public.fewia_eval_future_sequence")
    _assert_privileges(admin)
    provision_runtime_access(admin, PASSWORD)
    _assert_privileges(admin)
    assert (
        admin.execute("SELECT * FROM pg_default_acl ORDER BY oid").fetchall()
        == defaults_before
    )
