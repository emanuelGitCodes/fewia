"""Expose explicit retention actions for a separately authenticated operator."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import datetime
from typing import NoReturn
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.services.operator_retention import OperatorRetention
from app.services.retention_manifest import RetentionError, utc


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise RetentionError()


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _Parser(description="Run one explicit operator action.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("preview", "purge", "enable", "disable"):
        child = commands.add_parser(command)
        child.add_argument("--owner-id", required=True)
        if command in {"preview", "purge"}:
            child.add_argument("--before", required=True)
        else:
            child.add_argument("--workspace-id", required=True)
        if command == "purge":
            child.add_argument("--digest", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    engine: sa.Engine | None = None
    try:
        args = _arguments(argv)
        owner_id = int(args.owner_id)
        database_url = os.environ.get("FEWIA_RETENTION_DATABASE_URL", "")
        if not database_url:
            raise RetentionError()
        url = make_url(database_url)
        if url.get_backend_name() != "postgresql" or not url.database:
            raise RetentionError()
        if url.username in {"fewia_app", "fewia_maintenance"}:
            raise RetentionError()
        if set(url.query) - {"sslmode"}:
            raise RetentionError()
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        if url.drivername != "postgresql+psycopg":
            raise RetentionError()
        engine = sa.create_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={"connect_timeout": 3},
        )
        service = OperatorRetention(engine)
        if args.command in {"enable", "disable"}:
            response = service.set_owner_status(
                owner_id=owner_id,
                workspace_id=UUID(args.workspace_id),
                enabled=args.command == "enable",
            )
        else:
            before = utc(datetime.fromisoformat(args.before))
            if args.command == "preview":
                response = service.preview(owner_id=owner_id, before=before)
            else:
                response = service.purge(
                    owner_id=owner_id,
                    before=before,
                    digest=args.digest,
                )
        print(json.dumps(response, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        argparse.ArgumentError,
        ImportError,
        OSError,
        RetentionError,
        TypeError,
        ValueError,
        sa.exc.SQLAlchemyError,
    ):
        print('{"error":"operator_retention_refused"}')
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
