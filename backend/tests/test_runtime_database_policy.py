"""Check the runtime policy on a disposable PostgreSQL server."""

import re
from collections.abc import Iterator, MutableMapping
from typing import cast

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.runtime_database_policy import (
    RUNTIME_GRANTS,
    RUNTIME_ROLE,
    UNSAFE_ACCESS_SQL,
    UNSAFE_ROLE_SQL,
    validate_runtime_password,
)
from tests.conftest import require_test_database_url

PgConnection = psycopg.Connection[tuple[object, ...]]
_TEST_ROLES = ("fewia_app", "fewia_eval_member", "fewia_eval_role_admin")
_TABLE_GRANTS: dict[str, frozenset[str]] = {
    "users": frozenset({"SELECT"}),
    "jobs": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "job_outbox": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "shopping_handoffs": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "grocery_evidence": frozenset({"SELECT", "INSERT"}),
    "plaid_items": frozenset({"SELECT"}),
    "plaid_transactions": frozenset({"SELECT"}),
    "daily_finance": frozenset(),
    "daily_environment": frozenset(),
    "daily_health": frozenset(),
    "model_runs": frozenset(),
    "predictions": frozenset(),
    "alembic_version": frozenset(),
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


@pytest.mark.parametrize(
    "password",
    [
        None,
        32,
        True,
        b"A" * 32,
        [],
        {},
        "",
        "A" * 31,
        "A" * 33,
        "A" * 31 + "_",
        "A" * 31 + "é",
        "A" * 31 + "\n",
        "A" * 31 + "\r",
        "A" * 31 + "\x00",
        "A" * 31 + " ",
        "A" * 31 + "'",
        "Ａ" * 32,
    ],
)
def test_password_validator_rejects_invalid_values_with_static_error(
    password: object,
) -> None:
    with pytest.raises(ValueError, match="^runtime database password is invalid$"):
        validate_runtime_password(cast(str, password))


def test_password_validator_accepts_exact_ascii_alphanumeric_value() -> None:
    password = "0123456789ABCDEFGHIJKLMNOPQRSTuv"
    assert validate_runtime_password(password) is password


def test_password_validator_rejects_string_subclasses() -> None:
    class Password(str):
        pass

    with pytest.raises(ValueError, match="^runtime database password is invalid$"):
        validate_runtime_password(Password("A1" * 16))


def test_runtime_grants_are_exact_and_immutable() -> None:
    assert RUNTIME_ROLE == "fewia_app"
    assert dict(RUNTIME_GRANTS) == {
        "users": "SELECT",
        "jobs": "SELECT, INSERT, UPDATE",
        "job_outbox": "SELECT, INSERT, UPDATE",
        "shopping_handoffs": "SELECT, INSERT, UPDATE",
        "grocery_evidence": "SELECT, INSERT",
        "plaid_items": "SELECT",
        "plaid_transactions": "SELECT",
    }
    with pytest.raises(TypeError):
        cast(MutableMapping[str, str], RUNTIME_GRANTS)["users"] = "ALL"


def _is_test_database(database: str) -> bool:
    return re.fullmatch(r"fewia_eval(?:_[A-Za-z0-9_]+)?", database) is not None


def _safe_target(url_text: str) -> dict[str, str | int]:
    try:
        url = make_url(url_text)
    except (ArgumentError, ValueError):
        raise ValueError("runtime role test database target is unsafe") from None
    if (
        url.get_backend_name() != "postgresql"
        or url.database is None
        or not _is_test_database(url.database)
        or url.host not in {"localhost", "127.0.0.1", "::1", None}
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
    if url.port is not None:
        options["port"] = url.port
    return options


@pytest.mark.parametrize(
    "database",
    ["fewia_eval", "fewia_eval_test", "fewia_eval_Runtime_42_policy"],
)
@pytest.mark.parametrize(
    ("authority", "host", "port"),
    [
        ("localhost", "localhost", None),
        ("localhost:5432", "localhost", 5432),
        ("127.0.0.1:6543", "127.0.0.1", 6543),
        ("[::1]", "::1", None),
        ("[::1]:6543", "::1", 6543),
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


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/fewia",
        "postgresql://localhost/postgres",
        "postgresql://localhost/fewia_eval_",
        "postgresql://localhost/fewia_evaltest",
        "postgresql://localhost/fewia_evaluation",
        "postgresql://localhost/other_fewia_eval_test",
        "postgresql://localhost/fewia_eval_tést",
        "postgresql://localhost/fewia_eval_１２",
        "postgresql://localhost/fewia_eval_test-other",
        "postgresql://localhost/fewia_eval_test/other",
        "postgresql://localhost/fewia_eval_test\n",
        "postgresql://remote/fewia_eval",
        "postgresql://remote/fewia_eval_runtime_database_policy",
        "postgresql://127.0.0.2/fewia_eval_test",
        "postgresql://localhost:invalid/fewia_eval",
        "postgresql://localhost/",
        "sqlite:///fewia_eval_runtime_database_policy",
        "postgresql://localhost/fewia_eval?host=remote",
        "postgresql://localhost/fewia_eval_runtime_database_policy?host=remote",
        "not a database URL",
    ],
)
def test_postgres_target_rejects_unsafe_database(url: str) -> None:
    with pytest.raises(
        ValueError, match="^runtime role test database target is unsafe$"
    ):
        _safe_target(url)


@pytest.fixture()
def admin() -> Iterator[PgConnection]:
    options = _safe_target(require_test_database_url())
    with psycopg.connect(**options, autocommit=True) as connection:
        assert connection.info.dbname == options["dbname"]
        assert connection.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone() == (True,), "runtime policy tests require a disposable superuser"
        assert all(
            _is_test_database(cast(str, row[0]))
            for row in connection.execute(
                "SELECT datname FROM pg_database WHERE datname NOT IN "
                "('postgres', 'template0', 'template1') "
            ).fetchall()
        ), "runtime policy tests require a dedicated PostgreSQL server"
        assert (
            connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = ANY(%s)", (list(_TEST_ROLES),)
            ).fetchone()
            is None
        ), "runtime policy tests require absent test roles"
        for table in _TABLE_GRANTS:
            assert connection.execute(
                "SELECT to_regclass(%s)", ("public." + table,)
            ).fetchone() != (None,), "runtime policy tests require migrated tables"
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout = '5s'")
            connection.execute("SET LOCAL statement_timeout = '10s'")
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


def _create_role(connection: PgConnection) -> None:
    connection.execute(
        "CREATE ROLE fewia_app LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
        "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
    )


def _grant_exact(connection: PgConnection) -> None:
    connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO fewia_app").format(
            sql.Identifier(connection.info.dbname)
        )
    )
    connection.execute("GRANT USAGE ON SCHEMA public TO fewia_app")
    for table, privileges in _TABLE_GRANTS.items():
        if privileges:
            connection.execute(
                sql.SQL("GRANT {} ON TABLE {} TO fewia_app").format(
                    sql.SQL(", ".join(sorted(privileges))),
                    sql.Identifier("public", table),
                )
            )


@pytest.fixture()
def runtime(admin: PgConnection) -> PgConnection:
    _create_role(admin)
    _grant_exact(admin)
    assert admin.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
    assert admin.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    return admin


def _create_extra_schema(connection: PgConnection) -> None:
    connection.execute("CREATE SCHEMA fewia_eval_extra")
    connection.execute("GRANT USAGE ON SCHEMA fewia_eval_extra TO fewia_app")


def _snapshot(connection: PgConnection) -> list[list[tuple[object, ...]]]:
    queries = (
        "SELECT rolname, rolsuper, rolinherit, rolcreatedb, rolcreaterole, "
        "rolreplication, rolbypassrls FROM pg_roles WHERE rolname = 'fewia_app'",
        "SELECT datdba, datacl::text FROM pg_database "
        "WHERE datname = current_database()",
        "SELECT oid, nspowner, nspacl::text FROM pg_namespace ORDER BY oid",
        "SELECT oid, relowner, relacl::text FROM pg_class ORDER BY oid",
        "SELECT attrelid, attnum, attacl::text FROM pg_attribute "
        "WHERE attacl IS NOT NULL ORDER BY attrelid, attnum",
        "SELECT oid, proowner, proacl::text, prosecdef FROM pg_proc ORDER BY oid",
        "SELECT roleid, member, admin_option FROM pg_auth_members "
        "ORDER BY roleid, member",
    )
    return [connection.execute(query).fetchall() for query in queries]


def test_postgres_exact_grants_and_catalog_visibility_are_safe(
    runtime: PgConnection,
) -> None:
    privileges = (
        (*_PRIVILEGES, "MAINTAIN")
        if runtime.info.server_version >= 170000
        else _PRIVILEGES
    )
    for table, allowed in _TABLE_GRANTS.items():
        for privilege in privileges:
            assert runtime.execute(
                "SELECT has_table_privilege('fewia_app', %s, %s), "
                "has_table_privilege('fewia_app', %s, %s)",
                (
                    "public." + table,
                    privilege,
                    "public." + table,
                    privilege + " WITH GRANT OPTION",
                ),
            ).fetchone() == (privilege in allowed, False)
            if privilege in _COLUMN_PRIVILEGES:
                assert runtime.execute(
                    "SELECT has_any_column_privilege('fewia_app', %s, %s), "
                    "has_any_column_privilege('fewia_app', %s, %s)",
                    (
                        "public." + table,
                        privilege,
                        "public." + table,
                        privilege + " WITH GRANT OPTION",
                    ),
                ).fetchone() == (privilege in allowed, False)
    with runtime.transaction():
        runtime.execute("SET LOCAL ROLE fewia_app")
        assert runtime.execute("SELECT count(*) FROM pg_catalog.pg_class").fetchone()
        assert runtime.execute(
            "SELECT count(*) FROM information_schema.tables"
        ).fetchone()
        assert runtime.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
        assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
        runtime.execute("RESET ROLE")


def test_postgres_policy_queries_do_not_change_role_or_acls(
    runtime: PgConnection,
) -> None:
    before = _snapshot(runtime)
    assert runtime.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    assert _snapshot(runtime) == before


@pytest.mark.parametrize("privilege", ["CREATE", "TEMPORARY"])
@pytest.mark.parametrize("recipient", ["PUBLIC", "fewia_app"])
def test_postgres_database_create_and_public_temp_are_unsafe(
    runtime: PgConnection, privilege: str, recipient: str
) -> None:
    runtime.execute(
        sql.SQL("GRANT {} ON DATABASE {} TO {}").format(
            sql.SQL(privilege),
            sql.Identifier(runtime.info.dbname),
            sql.SQL(recipient),
        )
    )
    before = _snapshot(runtime)
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)
    assert _snapshot(runtime) == before


@pytest.mark.parametrize("schema", ["public", "fewia_eval_extra"])
@pytest.mark.parametrize("recipient", ["PUBLIC", "fewia_app"])
def test_postgres_schema_create_is_unsafe(
    runtime: PgConnection, schema: str, recipient: str
) -> None:
    _create_extra_schema(runtime)
    runtime.execute(
        sql.SQL("GRANT CREATE ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.SQL(recipient)
        )
    )
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE fewia_eval_extra.denied (id integer)",
        "CREATE TABLE fewia_eval_extra.denied (id integer) PARTITION BY RANGE (id)",
        "CREATE VIEW fewia_eval_extra.denied AS SELECT 1 AS id",
        "CREATE MATERIALIZED VIEW fewia_eval_extra.denied AS SELECT 1 AS id",
    ],
)
@pytest.mark.parametrize("recipient", ["PUBLIC", "fewia_app"])
def test_postgres_other_schema_relation_access_is_unsafe(
    runtime: PgConnection, ddl: str, recipient: str
) -> None:
    _create_extra_schema(runtime)
    runtime.execute(ddl)
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    runtime.execute(
        sql.SQL("GRANT SELECT ON fewia_eval_extra.denied TO {}").format(
            sql.SQL(recipient)
        )
    )
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)


@pytest.mark.parametrize("table", list(RUNTIME_GRANTS))
def test_postgres_allowed_table_names_in_other_schema_are_unsafe(
    runtime: PgConnection, table: str
) -> None:
    _create_extra_schema(runtime)
    relation = sql.Identifier("fewia_eval_extra", table)
    runtime.execute(sql.SQL("CREATE TABLE {} (id integer)").format(relation))
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    runtime.execute(sql.SQL("GRANT SELECT ON {} TO PUBLIC").format(relation))
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)


@pytest.mark.parametrize("schema", ["public", "fewia_eval_extra"])
@pytest.mark.parametrize("privilege", ["USAGE", "SELECT", "UPDATE"])
@pytest.mark.parametrize("recipient", ["PUBLIC", "fewia_app"])
def test_postgres_sequence_access_is_unsafe(
    runtime: PgConnection, schema: str, privilege: str, recipient: str
) -> None:
    _create_extra_schema(runtime)
    relation = sql.Identifier(schema, "fewia_eval_sequence")
    runtime.execute(sql.SQL("CREATE SEQUENCE {}").format(relation))
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    runtime.execute(
        sql.SQL("GRANT {} ON SEQUENCE {} TO {}").format(
            sql.SQL(privilege), relation, sql.SQL(recipient)
        )
    )
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)


@pytest.mark.parametrize(
    "grant",
    [
        "GRANT SELECT ON public.daily_health TO PUBLIC",
        "GRANT SELECT ON public.alembic_version TO fewia_app",
        "GRANT UPDATE ON public.grocery_evidence TO PUBLIC",
        "GRANT INSERT ON public.plaid_items TO PUBLIC",
        "GRANT UPDATE ON public.plaid_transactions TO fewia_app",
        "GRANT DELETE ON public.jobs TO PUBLIC",
        "GRANT TRUNCATE ON public.users TO fewia_app",
        "GRANT REFERENCES ON public.job_outbox TO PUBLIC",
        "GRANT TRIGGER ON public.shopping_handoffs TO fewia_app",
    ],
)
def test_postgres_excess_table_privileges_are_unsafe(
    runtime: PgConnection, grant: str
) -> None:
    runtime.execute(grant)
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)


def test_postgres_unknown_public_table_access_is_unsafe(
    runtime: PgConnection,
) -> None:
    runtime.execute("CREATE TABLE public.fewia_eval_denied (id integer)")
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    runtime.execute("GRANT SELECT ON public.fewia_eval_denied TO PUBLIC")
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)


@pytest.mark.parametrize(
    ("table", "privilege"),
    [
        (table, privilege)
        for table, privileges in _TABLE_GRANTS.items()
        for privilege in sorted(privileges)
    ],
)
def test_postgres_allowed_table_grant_options_are_unsafe(
    runtime: PgConnection, table: str, privilege: str
) -> None:
    runtime.execute(
        sql.SQL("GRANT {} ON TABLE {} TO fewia_app WITH GRANT OPTION").format(
            sql.SQL(privilege), sql.Identifier("public", table)
        )
    )
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)


@pytest.mark.parametrize(
    ("grant", "unsafe"),
    [
        ("GRANT UPDATE (display_name) ON public.users TO fewia_app", True),
        ("GRANT UPDATE (display_name) ON public.users TO PUBLIC", True),
        ("GRANT SELECT (display_name) ON public.users TO PUBLIC", False),
        (
            "GRANT SELECT (display_name) ON public.users TO fewia_app "
            "WITH GRANT OPTION",
            True,
        ),
        ("GRANT INSERT (snapshot) ON public.grocery_evidence TO fewia_app", False),
        ("GRANT UPDATE (snapshot) ON public.grocery_evidence TO PUBLIC", True),
        ("GRANT REFERENCES (id) ON public.jobs TO fewia_app", True),
        ("GRANT UPDATE (cursor) ON public.plaid_items TO PUBLIC", True),
        ("GRANT SELECT (id) ON fewia_eval_extra.jobs TO PUBLIC", True),
        (
            "GRANT SELECT (id) ON fewia_eval_extra.jobs TO fewia_app WITH GRANT OPTION",
            True,
        ),
    ],
)
def test_postgres_column_privileges_and_grant_options_follow_whitelist(
    runtime: PgConnection, grant: str, unsafe: bool
) -> None:
    _create_extra_schema(runtime)
    runtime.execute("CREATE TABLE fewia_eval_extra.jobs (id integer)")
    runtime.execute("REVOKE SELECT ON public.users FROM fewia_app")
    runtime.execute(grant)
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (unsafe,)


@pytest.mark.parametrize("schema", ["public", "fewia_eval_extra"])
@pytest.mark.parametrize("kind", ["FUNCTION", "PROCEDURE"])
@pytest.mark.parametrize("security", ["INVOKER", "DEFINER"])
@pytest.mark.parametrize("recipient", ["PUBLIC", "fewia_app", "none"])
def test_postgres_executable_definer_routines_are_unsafe(
    runtime: PgConnection, schema: str, kind: str, security: str, recipient: str
) -> None:
    _create_extra_schema(runtime)
    routine = sql.Identifier(schema, "fewia_eval_routine")
    if kind == "FUNCTION":
        runtime.execute(
            sql.SQL(
                "CREATE FUNCTION {}() RETURNS bigint LANGUAGE sql SECURITY {} "
                "AS 'SELECT count(*) FROM public.daily_health'"
            ).format(routine, sql.SQL(security))
        )
    else:
        runtime.execute(
            sql.SQL(
                "CREATE PROCEDURE {}() LANGUAGE plpgsql SECURITY {} "
                "AS 'BEGIN PERFORM count(*) FROM public.daily_health; END;'"
            ).format(routine, sql.SQL(security))
        )
    if recipient != "PUBLIC":
        runtime.execute(
            sql.SQL("REVOKE EXECUTE ON {} {}() FROM PUBLIC").format(
                sql.SQL(kind), routine
            )
        )
        if recipient == "fewia_app":
            runtime.execute(
                sql.SQL("GRANT EXECUTE ON {} {}() TO fewia_app").format(
                    sql.SQL(kind), routine
                )
            )
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (
        security == "DEFINER" and recipient != "none",
    )
    if recipient != "none":
        call = sql.SQL("SELECT {}()" if kind == "FUNCTION" else "CALL {}()").format(
            routine
        )
        if security == "DEFINER":
            with runtime.transaction():
                runtime.execute("SET LOCAL ROLE fewia_app")
                runtime.execute(call)
                runtime.execute("RESET ROLE")
        else:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with runtime.transaction():
                    runtime.execute("SET LOCAL ROLE fewia_app")
                    runtime.execute(call)


@pytest.mark.parametrize(
    "flag",
    ["SUPERUSER", "INHERIT", "CREATEDB", "CREATEROLE", "REPLICATION", "BYPASSRLS"],
)
def test_postgres_unsafe_role_flags_are_rejected(
    admin: PgConnection, flag: str
) -> None:
    _create_role(admin)
    assert admin.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
    admin.execute(sql.SQL("ALTER ROLE fewia_app {}").format(sql.SQL(flag)))
    assert admin.execute(UNSAFE_ROLE_SQL).fetchone() == (True,)


@pytest.mark.parametrize("admin_option", [False, True])
def test_postgres_outgoing_membership_is_unsafe(
    runtime: PgConnection, admin_option: bool
) -> None:
    runtime.execute("CREATE ROLE fewia_eval_member NOLOGIN")
    runtime.execute(
        "GRANT fewia_eval_member TO fewia_app"
        + (" WITH ADMIN OPTION" if admin_option else "")
    )
    assert runtime.execute(UNSAFE_ROLE_SQL).fetchone() == (True,)


@pytest.mark.parametrize(
    "ownership",
    ["database", "schema", "table", "sequence", "function", "type"],
)
def test_postgres_any_object_ownership_is_unsafe(
    runtime: PgConnection, ownership: str
) -> None:
    if ownership == "database":
        runtime.execute(
            sql.SQL("ALTER DATABASE {} OWNER TO fewia_app").format(
                sql.Identifier(runtime.info.dbname)
            )
        )
    elif ownership == "schema":
        runtime.execute("CREATE SCHEMA fewia_eval_owned AUTHORIZATION fewia_app")
    elif ownership == "table":
        runtime.execute("ALTER TABLE public.jobs OWNER TO fewia_app")
    elif ownership == "sequence":
        runtime.execute("CREATE SEQUENCE public.fewia_eval_owned")
        runtime.execute("ALTER SEQUENCE public.fewia_eval_owned OWNER TO fewia_app")
    elif ownership == "function":
        runtime.execute(
            "CREATE FUNCTION public.fewia_eval_owned() RETURNS integer "
            "LANGUAGE sql AS 'SELECT 1'"
        )
        runtime.execute("ALTER FUNCTION public.fewia_eval_owned() OWNER TO fewia_app")
    else:
        runtime.execute("CREATE TYPE public.fewia_eval_owned AS ENUM ('fixture')")
        runtime.execute("ALTER TYPE public.fewia_eval_owned OWNER TO fewia_app")
    assert runtime.execute(UNSAFE_ROLE_SQL).fetchone() == (True,)


@pytest.mark.parametrize("admin_option", [False, True])
def test_postgres_incoming_administrator_membership_is_safe(
    runtime: PgConnection, admin_option: bool
) -> None:
    runtime.execute("CREATE ROLE fewia_eval_member NOLOGIN")
    runtime.execute(
        "GRANT fewia_app TO fewia_eval_member"
        + (" WITH ADMIN OPTION" if admin_option else "")
    )
    assert runtime.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
    assert runtime.execute(
        "SELECT m.admin_option FROM pg_auth_members m "
        "JOIN pg_roles r ON r.oid = m.roleid "
        "JOIN pg_roles u ON u.oid = m.member "
        "WHERE r.rolname = 'fewia_app' AND u.rolname = 'fewia_eval_member'"
    ).fetchone() == (admin_option,)


def test_postgres_non_superuser_creator_admin_membership_is_safe(
    admin: PgConnection,
) -> None:
    if admin.info.server_version < 160000:
        pytest.skip("automatic creator ADMIN OPTION requires PostgreSQL 16")
    admin.execute(
        "CREATE ROLE fewia_eval_role_admin NOLOGIN NOINHERIT NOSUPERUSER "
        "CREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS"
    )
    with admin.transaction():
        admin.execute("SET LOCAL ROLE fewia_eval_role_admin")
        assert admin.execute(
            "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ).fetchone() == (False, True)
        _create_role(admin)
        assert admin.execute(
            "SELECT m.admin_option FROM pg_auth_members m "
            "JOIN pg_roles r ON r.oid = m.roleid "
            "JOIN pg_roles u ON u.oid = m.member "
            "WHERE r.rolname = 'fewia_app' AND u.rolname = current_user"
        ).fetchone() == (True,)
        assert admin.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
        assert admin.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)
        admin.execute("RESET ROLE")
    _grant_exact(admin)
    assert admin.execute(UNSAFE_ROLE_SQL).fetchone() == (False,)
    assert admin.execute(UNSAFE_ACCESS_SQL).fetchone() == (False,)


def test_postgres_maintain_privilege_is_unsafe(runtime: PgConnection) -> None:
    if runtime.info.server_version < 170000:
        pytest.skip("MAINTAIN requires PostgreSQL 17")
    runtime.execute("GRANT MAINTAIN ON public.jobs TO fewia_app")
    assert runtime.execute(UNSAFE_ACCESS_SQL).fetchone() == (True,)
