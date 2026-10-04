from __future__ import annotations

import io
import os
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout
from typing import TYPE_CHECKING

from app.bootstrap_database import StaticArgumentParser, emit

if TYPE_CHECKING:
    import psycopg
    from sqlalchemy.engine import URL


def _configuration() -> tuple[URL, str]:
    from app.cloud_database_settings import cloud_database_url
    from app.runtime_database_policy import validate_runtime_password

    url = cloud_database_url()
    if url is None or url.username != "fewia_admin" or url.database != "fewia":
        raise ValueError("Invalid hosted database configuration.")
    password = validate_runtime_password(
        os.environ["FEWIA_APPLICATION_DATABASE_PASSWORD"]
    )
    return url, password


def _bootstrap() -> int:
    from app.bootstrap_database import main as bootstrap_database

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return bootstrap_database(["--run"])


def _connect(url: URL) -> psycopg.Connection[tuple[object, ...]]:
    import psycopg

    return psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
        connect_timeout=10,
        options="-c statement_timeout=30000 -c lock_timeout=5000",
    )


def _permissions(
    connection: psycopg.Connection[tuple[object, ...]], password: str
) -> None:
    from psycopg import sql

    from app.runtime_database_access import provision_runtime_access

    with connection.transaction():
        connection.execute(
            sql.SQL("REVOKE CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(connection.info.dbname)
            )
        )
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        provision_runtime_access(connection, password)


def main(argv: Sequence[str] | None = None) -> int:
    stage = "arguments"
    try:
        parser = StaticArgumentParser(
            prog="python -m app.bootstrap_hosting",
            description="Prepare the dedicated hosted database.",
            add_help=False,
            allow_abbrev=False,
        )
        parser.add_argument("-h", "--help", action="store_true", help="Show help.")
        parser.add_argument(
            "--run", action="store_true", help="Run the hosted database setup."
        )
        args = parser.parse_args(argv)
        if args.help:
            parser.print_help()
            return 0
        if not args.run:
            emit("failed", stage)
            return 1
        stage = "configuration"
        url, password = _configuration()
        stage = "database"
        result = _bootstrap()
        if result:
            emit("interrupted" if result == 130 else "failed", stage)
            return 130 if result == 130 else 1
        connection = _connect(url)
        with connection:
            stage = "permissions"
            _permissions(connection, password)
    except KeyboardInterrupt:
        emit("interrupted", stage)
        return 130
    except Exception:  # noqa: BLE001
        emit("failed", stage)
        return 1
    emit("ok", "complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
