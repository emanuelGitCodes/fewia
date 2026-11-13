"""Expose explicit retention actions for a separately authenticated operator."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Sequence
from datetime import datetime
from ipaddress import ip_address
from pathlib import PurePosixPath
from typing import NoReturn
from urllib.parse import parse_qsl
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool

from app.services.operator_retention import OperatorRetention
from app.services.retention_manifest import RetentionError, utc

_LIBPQ_OVERRIDES = frozenset(
    {
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGSYSCONFDIR",
        "PGSSLMODE",
        "PGSSLROOTCERT",
        "PGREQUIRESSL",
        "PGGSSENCMODE",
        "PGSSLCERT",
        "PGSSLCERTMODE",
        "PGSSLKEY",
        "PGSSLCRL",
        "PGSSLCRLDIR",
        "PGSSLSNI",
        "PGSSLNEGOTIATION",
        "PGSSLCOMPRESSION",
        "PGSSLMINPROTOCOLVERSION",
        "PGSSLMAXPROTOCOLVERSION",
        "PGREQUIREAUTH",
        "PGCHANNELBINDING",
        "PGGSSLIB",
        "PGKRBSRVNAME",
        "PGOPTIONS",
        "PGTARGETSESSIONATTRS",
        "PGLOADBALANCEHOSTS",
        "PGCONNECT_TIMEOUT",
    }
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}
_IDENTIFIER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_HOST_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_SSL_MODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def _valid_host(host: str) -> bool:
    if "%" in host:
        return False
    try:
        ip_address(host)
    except ValueError:
        return len(host) <= 253 and all(
            _HOST_LABEL.fullmatch(label) is not None
            for label in host.removesuffix(".").split(".")
        )
    return True


def _valid_ca_path(path: str) -> bool:
    return (
        path.startswith("/")
        and not path.startswith("//")
        and path != "/"
        and "\\" not in path
        and ".." not in path.split("/")
        and str(PurePosixPath(path)) == path
        and all(char.isprintable() and not char.isspace() for char in path)
    )


def _operator_url(database_url: str) -> URL:
    if any(key in os.environ for key in _LIBPQ_OVERRIDES):
        raise RetentionError()
    mode = os.environ.get("FEWIA_DATABASE_MODE", "local")
    if mode not in {"local", "aws"}:
        raise RetentionError()
    url = make_url(database_url)
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise RetentionError()
    if (
        not url.host
        or not _valid_host(url.host)
        or not url.database
        or _IDENTIFIER.fullmatch(url.database) is None
        or not url.username
        or _IDENTIFIER.fullmatch(url.username) is None
        or url.username in {"fewia_app", "fewia_maintenance"}
        or (url.port is not None and not 1 <= url.port <= 65535)
    ):
        raise RetentionError()
    host = f"[{url.host}]" if ":" in url.host else url.host
    port = f":{url.port}" if url.port is not None else ""
    raw_target, separator, raw_query = database_url.partition("?")
    raw_target = raw_target.partition("://")[2].rpartition("@")[2]
    if raw_target != f"{host}{port}/{url.database}":
        raise RetentionError()
    if "#" in raw_query or re.search(r"%(?![A-Fa-f0-9]{2})", raw_query):
        raise RetentionError()
    query: dict[str, str] = {}
    for key, value in parse_qsl(
        raw_query, keep_blank_values=True, strict_parsing=True, errors="strict"
    ):
        if key not in {"sslmode", "sslrootcert"} or key in query or not value:
            raise RetentionError()
        query[key] = value
    if separator and not query:
        raise RetentionError()
    sslmode = query.get("sslmode")
    rootcert = query.get("sslrootcert")
    if sslmode is not None and sslmode not in _SSL_MODES:
        raise RetentionError()
    if rootcert is not None and not _valid_ca_path(rootcert):
        raise RetentionError()
    if (mode != "local" or url.host not in _LOCAL_HOSTS) and (
        sslmode != "verify-full" or rootcert is None
    ):
        raise RetentionError()
    return url.set(drivername="postgresql+psycopg", query=query)


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
        url = _operator_url(database_url)
        engine = sa.create_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            connect_args={"connect_timeout": 3, "gssencmode": "disable"},
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
