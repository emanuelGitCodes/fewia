"""Database URLs for private local credentials."""

import os
from pathlib import Path

from sqlalchemy.engine import URL, make_url

from app.local_secret_state import LocalStateError, read_password

DEFAULT_DATABASE_URL = "postgresql+psycopg://fewia_app@localhost:5432/fewia"
LOCAL_CONTAINER_URL = "postgresql+psycopg://fewia_app@postgres:5432/fewia"


def local_database_url(*, admin: bool = False) -> URL | None:
    name = (
        "FEWIA_LOCAL_ADMIN_PASSWORD_FILE"
        if admin
        else "FEWIA_LOCAL_DATABASE_PASSWORD_FILE"
    )
    filename = os.environ.get(name)
    if not filename:
        if admin:
            raise LocalStateError("Local bootstrap admin file is missing.")
        return None
    url = make_url(os.environ.get("DATABASE_URL", LOCAL_CONTAINER_URL))
    if (
        url.drivername != "postgresql+psycopg"
        or url.host != "postgres"
        or url.port != 5432
        or url.database != "fewia"
        or url.password is not None
        or url.username != "fewia_app"
        or url.query
    ):
        raise LocalStateError("Invalid local database target.")
    return url.set(
        username="fewia" if admin else "fewia_app",
        password=read_password(Path(filename)),
    )
