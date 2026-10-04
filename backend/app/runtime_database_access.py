"""Provision the fixed application role through a privileged connection."""

import psycopg
from psycopg import sql

from app.runtime_database_policy import (
    RUNTIME_GRANTS,
    RUNTIME_ROLE,
    UNSAFE_ACCESS_SQL,
    UNSAFE_ROLE_SQL,
    validate_runtime_password,
)


class RuntimeDatabaseAccessError(RuntimeError):
    """The application role cannot meet the access contract."""


def provision_runtime_access(
    connection: psycopg.Connection[tuple[object, ...]], password: str
) -> None:
    validate_runtime_password(password)
    failed = False
    try:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_xact_lock(782346921)")
            if connection.execute(UNSAFE_ROLE_SQL).fetchone() != (False,):
                raise RuntimeDatabaseAccessError("runtime database role is unsafe")
            encrypted = connection.pgconn.encrypt_password(
                password.encode("ascii"), RUNTIME_ROLE.encode("ascii"), b"scram-sha-256"
            ).decode("ascii")
            if not encrypted.startswith("SCRAM-SHA-256$"):
                raise RuntimeDatabaseAccessError("runtime password encryption failed")
            role = sql.Identifier(RUNTIME_ROLE)
            exists = connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = 'fewia_app'"
            ).fetchone()
            if exists is None:
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                    ).format(role)
                )
            connection.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    role, sql.Literal(encrypted)
                )
            )
            database = sql.Identifier(connection.info.dbname)
            connection.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(database, role)
            )
            connection.execute(
                sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(role)
            )
            for kind in ("TABLES", "SEQUENCES"):
                connection.execute(
                    sql.SQL("REVOKE ALL ON ALL {} IN SCHEMA public FROM {}").format(
                        sql.SQL(kind), role
                    )
                )
            columns = connection.execute(
                "SELECT c.relname, a.attname FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND a.attnum > 0 AND NOT a.attisdropped "
                "AND EXISTS (SELECT 1 FROM aclexplode(a.attacl) acl "
                "JOIN pg_roles r ON r.oid = acl.grantee WHERE r.rolname = 'fewia_app')"
            ).fetchall()
            for table, column in columns:
                connection.execute(
                    sql.SQL("REVOKE ALL ({}) ON TABLE {} FROM {}").format(
                        sql.Identifier(str(column)),
                        sql.Identifier("public", str(table)),
                        role,
                    )
                )
            if connection.execute(UNSAFE_ACCESS_SQL).fetchone() != (False,):
                raise RuntimeDatabaseAccessError("runtime database access is unsafe")
            connection.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role)
            )
            connection.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role)
            )
            for table, privileges in RUNTIME_GRANTS.items():
                connection.execute(
                    sql.SQL("GRANT {} ON TABLE {} TO {}").format(
                        sql.SQL(privileges), sql.Identifier("public", table), role
                    )
                )
    except Exception:  # noqa: BLE001
        failed = True
    if failed:
        raise RuntimeDatabaseAccessError("runtime database access provisioning failed")
