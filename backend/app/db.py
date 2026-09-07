"""Database engine, session factory, and the declarative base."""

from typing import TypedDict

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_PG_OPTIONS = "-c statement_timeout=10000 -c lock_timeout=5000"


class EngineConnectKwargs(TypedDict, total=False):
    pool_pre_ping: bool
    pool_timeout: int
    connect_args: dict[str, int | str]


class Base(DeclarativeBase):
    """Base class for every mapped model."""


def engine_connect_kwargs(database_url: str) -> EngineConnectKwargs:
    """Build create_engine kwargs. PostgreSQL timeouts do not close a stuck socket."""
    kwargs: EngineConnectKwargs = {"pool_pre_ping": True}
    if make_url(database_url).get_backend_name() == "postgresql":
        kwargs["pool_timeout"] = 3
        kwargs["connect_args"] = {
            "connect_timeout": 3,
            "options": _PG_OPTIONS,
        }
    return kwargs


def create_app_engine(database_url: str) -> Engine:
    return create_engine(database_url, **engine_connect_kwargs(database_url))


engine: Engine = create_app_engine(settings.database_url)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
