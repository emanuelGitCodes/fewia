"""Create isolated databases for evaluation fixtures."""

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import evidence_models, handoff_models, job_models, models, plaid_models
from app.db import Base

_TABLES = [
    models.User.__table__,
    models.DailyFinance.__table__,
    models.DailyEnvironment.__table__,
    models.DailyHealth.__table__,
    models.ModelRun.__table__,
    models.Prediction.__table__,
    job_models.Job.__table__,
    job_models.JobOutbox.__table__,
    evidence_models.GroceryEvidence.__table__,
    handoff_models.ShoppingHandoff.__table__,
    plaid_models.PlaidItem.__table__,
    plaid_models.PlaidTransaction.__table__,
]


class EvaluationDatabaseError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Evaluation database operation failed.")


@dataclass(frozen=True)
class FixtureDatabase:
    factory: sessionmaker[Session] = field(repr=False)
    backend: str


def _validated_url(database_url: str) -> URL:
    url = make_url(database_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "postgres"}
        or not (url.database or "").startswith(("eval", "fewia_eval"))
        or url.query
    ):
        raise EvaluationDatabaseError()
    return url


def _enable_foreign_keys(connection: sqlite3.Connection, record: object) -> None:
    del record
    cursor = connection.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _drop_schema(admin: Engine, schema: str) -> None:
    with admin.begin() as connection:
        connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _cleanup(
    engine: Engine | None,
    admin: Engine | None,
    schema: str | None,
    sessions: set[Session],
) -> None:
    actions: list[Callable[[], None]] = [session.close for session in sessions]
    if engine is not None:
        actions.append(engine.dispose)
    if admin is not None:
        if schema is not None:
            actions.append(partial(_drop_schema, admin, schema))
        actions.append(admin.dispose)
    failed = False
    for action in actions:
        try:
            action()
        except Exception:
            failed = True
    if failed:
        raise EvaluationDatabaseError() from None


@contextmanager
def fixture_database(database_url: str | None = None) -> Iterator[FixtureDatabase]:
    engine: Engine | None = None
    admin: Engine | None = None
    schema: str | None = None
    sessions: set[Session] = set()

    class FixtureSession(Session):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            sessions.add(self)

    try:
        try:
            if database_url is None:
                engine = create_engine(
                    "sqlite://",
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False},
                )
                event.listen(engine, "connect", _enable_foreign_keys)
            else:
                url = _validated_url(database_url)
                options = "-c statement_timeout=10000 -c lock_timeout=5000"
                admin = create_engine(
                    url, connect_args={"connect_timeout": 3, "options": options}
                )
                name = f"eval_{uuid4().hex}"
                with admin.begin() as connection:
                    connection.execute(text(f'CREATE SCHEMA "{name}"'))
                schema = name
                engine = create_engine(
                    url,
                    connect_args={
                        "connect_timeout": 3,
                        "options": f"{options} -c search_path={schema}",
                    },
                )
            Base.metadata.create_all(engine, tables=_TABLES)
            factory: sessionmaker[Session] = sessionmaker(
                bind=engine, class_=FixtureSession, expire_on_commit=False
            )
        except Exception:
            raise EvaluationDatabaseError() from None
        try:
            yield FixtureDatabase(factory=factory, backend=engine.dialect.name)
        except SQLAlchemyError:
            raise EvaluationDatabaseError() from None
    finally:
        _cleanup(engine, admin, schema, sessions)
