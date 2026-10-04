from __future__ import annotations

import os
import re
from collections.abc import Mapping

from sqlalchemy.engine import URL

_INVALID = "Cloud database configuration is invalid"
_CLOUD_FIELDS = (
    "FEWIA_DATABASE_HOST",
    "FEWIA_DATABASE_NAME",
    "FEWIA_DATABASE_USER",
    "FEWIA_DATABASE_PASSWORD",
)
_FORBIDDEN_KEYS = (
    "DATABASE_URL",
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGPASSWORD",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSSLMODE",
    "PGSSLROOTCERT",
)
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HOST = re.compile(rf"{_LABEL}\.{_LABEL}\.us-east-1\.rds\.amazonaws\.com")


def _cloud_database_url(environ: Mapping[str, str]) -> URL | None:
    mode = environ.get("FEWIA_DATABASE_MODE", "local")
    if type(mode) is not str:
        raise ValueError(_INVALID)
    keys = set(environ)
    if mode == "local":
        if any(key in keys for key in _CLOUD_FIELDS):
            raise ValueError(_INVALID)
        return None
    if mode != "aws" or any(key in keys for key in _FORBIDDEN_KEYS):
        raise ValueError(_INVALID)
    values = tuple(environ[key] for key in _CLOUD_FIELDS)
    if any(type(value) is not str for value in values):
        raise ValueError(_INVALID)
    host, name, user, password = values
    if len(host) > 253 or _HOST.fullmatch(host) is None:
        raise ValueError(_INVALID)
    if name != "fewia" or user not in ("fewia_app", "fewia_admin"):
        raise ValueError(_INVALID)
    if not 1 <= len(password) <= 128:
        raise ValueError(_INVALID)
    if any(ord(character) < 32 or ord(character) == 127 for character in password):
        raise ValueError(_INVALID)
    return URL.create(
        "postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=5432,
        database=name,
        query={
            "sslmode": "verify-full",
            "sslrootcert": "/app/infra/rds/us-east-1-bundle.pem",
        },
    )


def cloud_database_url(environ: Mapping[str, str] | None = None) -> URL | None:
    try:
        return _cloud_database_url(os.environ if environ is None else environ)
    except Exception:  # noqa: BLE001
        pass
    raise ValueError(_INVALID) from None
