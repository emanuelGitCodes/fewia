import copy
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from conftest import require_test_database_url
from sqlalchemy import Connection, Engine, create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from test_evidence_contract import genuine_planning, inputs

from app import models
from app.db import Base
from app.evidence_models import GroceryEvidence
from app.services.evidence_contract import canonical_json, normalize_snapshot
from app.services.evidence_store import (
    EvidenceConflict,
    load_evidence,
    save_plan_evidence,
)


@pytest.fixture()
def evidence_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "evidence.db"
    test_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        isolation_level=None,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(
        dbapi_connection: sqlite3.Connection, connection_record: object
    ) -> None:
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")

    @event.listens_for(test_engine, "begin")
    def begin_sqlite_transaction(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    tables = [models.User.__table__, GroceryEvidence.__table__]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def factory(evidence_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=evidence_engine, expire_on_commit=False)


def seed_users(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(models.User(id=2, display_name="Other"))


def expected_id(user_id: int, snapshot: dict[str, object]) -> str:
    return sha256(
        canonical_json({"user_id": user_id, "snapshot": snapshot}).encode("utf-8")
    ).hexdigest()


def count_rows(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return int(
            session.scalar(select(func.count()).select_from(GroceryEvidence)) or 0
        )


def test_missing_user_propagates_integrity_error(
    factory: sessionmaker[Session],
) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    with pytest.raises(IntegrityError):
        save_plan_evidence(factory, 1, planning, parsed)
    assert count_rows(factory) == 0


def test_duplicate_replay_returns_the_same_id(
    factory: sessionmaker[Session],
) -> None:
    seed_users(factory)
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    first = save_plan_evidence(factory, 1, planning, parsed)
    snapshot = normalize_snapshot(1, planning, parsed)
    assert first == expected_id(1, snapshot)
    second = save_plan_evidence(factory, 1, copy.deepcopy(planning), parsed)
    assert first == second
    assert count_rows(factory) == 1
    loaded = load_evidence(factory, 1, first)
    assert loaded == snapshot
    assert loaded is not None
    loaded["tamper"] = True
    assert load_evidence(factory, 1, first) == snapshot


def test_changed_inputs_create_a_new_id(factory: sessionmaker[Session]) -> None:
    seed_users(factory)
    first_inputs = inputs()
    first_planning = genuine_planning(evidence_inputs=first_inputs)
    first = save_plan_evidence(factory, 1, first_planning, first_inputs)
    second_inputs = inputs(monthly_limit_cents=9_000)
    second_planning = genuine_planning(evidence_inputs=second_inputs)
    second = save_plan_evidence(factory, 1, second_planning, second_inputs)
    assert first != second
    assert count_rows(factory) == 2
    assert load_evidence(factory, 1, first) is not None
    assert load_evidence(factory, 1, second) is not None


def test_owner_isolation(factory: sessionmaker[Session]) -> None:
    seed_users(factory)
    parsed = inputs()
    planning = genuine_planning(user_id=1, evidence_inputs=parsed)
    evidence_id = save_plan_evidence(factory, 1, planning, parsed)
    assert load_evidence(factory, 2, evidence_id) is None
    other_planning = genuine_planning(user_id=2, evidence_inputs=parsed)
    other_id = save_plan_evidence(factory, 2, other_planning, parsed)
    assert other_id != evidence_id
    assert load_evidence(factory, 1, other_id) is None
    assert load_evidence(factory, 2, other_id) is not None
    with pytest.raises(ValueError, match="user_id is invalid"):
        load_evidence(factory, True, evidence_id)  # type: ignore[arg-type]


def test_commit_failure_does_not_return_an_id(
    evidence_engine: Engine, factory: sessionmaker[Session]
) -> None:
    seed_users(factory)
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)

    def failing_factory() -> Session:
        session = Session(bind=evidence_engine, expire_on_commit=False)

        def fail() -> None:
            raise RuntimeError("commit failed")

        session.commit = fail  # type: ignore[method-assign]
        return session

    with pytest.raises(RuntimeError, match="commit failed"):
        save_plan_evidence(failing_factory, 1, planning, parsed)  # type: ignore[arg-type]
    assert count_rows(factory) == 0


def test_conflicting_row_is_not_overwritten(
    factory: sessionmaker[Session],
) -> None:
    seed_users(factory)
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    snapshot = normalize_snapshot(1, planning, parsed)
    evidence_id = expected_id(1, snapshot)
    with factory.begin() as session:
        session.add(
            GroceryEvidence(
                id=evidence_id,
                user_id=1,
                snapshot={"planning": {"forged": True}},
            )
        )
    with pytest.raises(EvidenceConflict, match="evidence snapshot conflicts") as caught:
        save_plan_evidence(factory, 1, planning, parsed)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    loaded = load_evidence(factory, 1, evidence_id)
    assert loaded == {"planning": {"forged": True}}
    assert count_rows(factory) == 1


@pytest.fixture()
def postgres_factory() -> Iterator[sessionmaker[Session]]:
    url = require_test_database_url()
    schema = f"evidence_{uuid4().hex}"
    admin = create_engine(url)
    if admin.dialect.name != "postgresql":
        admin.dispose()
        pytest.fail("The evidence concurrency test requires PostgreSQL.")
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    with engine.begin() as connection:
        Base.metadata.create_all(
            connection,
            tables=[models.User.__table__, GroceryEvidence.__table__],
        )
        connection.execute(
            models.User.__table__.insert().values(id=1, display_name="pg-owner")
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_concurrent_identical_saves(
    postgres_factory: sessionmaker[Session],
) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    start = Barrier(2)

    def save() -> str:
        start.wait(timeout=10)
        return save_plan_evidence(postgres_factory, 1, planning, parsed)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(save) for _ in range(2)]
        ids = [future.result(timeout=20) for future in futures]
    assert ids[0] == ids[1]
    assert count_rows(postgres_factory) == 1
    loaded = load_evidence(postgres_factory, 1, ids[0])
    assert loaded == normalize_snapshot(1, planning, parsed)
