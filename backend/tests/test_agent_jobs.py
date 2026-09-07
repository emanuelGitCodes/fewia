import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_chat_job import FailLLM, FakeLLM, _planner_then_final, chat_payload
from test_plan_job import NOW, expected_plan, payload

from app import models
from app.agent.chat_loop import ChatUnavailable
from app.db import Base
from app.evidence_models import GroceryEvidence
from app.services import chat_job as chat_job_module
from app.services import plan_job as plan_job_module
from app.services.agent_jobs import make_agent_handler
from app.services.evidence_store import load_evidence


@pytest.fixture()
def evidence_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "agent-jobs.db"
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


def seed_user(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))


def count_rows(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return int(
            session.scalar(select(func.count()).select_from(GroceryEvidence)) or 0
        )


def freeze_clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)


def test_handler_routes_plan_and_chat(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    provider = FakeLLM(_planner_then_final())
    handler = make_agent_handler(factory, provider)
    plan_body = payload()
    expected = expected_plan(plan_body)

    plan_result = handler(plan_body, lambda: None)

    assert plan_result["request"] == expected["request"]
    assert plan_result["plan"] == expected["plan"]
    assert plan_result["evidence_id"] == expected["evidence_id"]
    revision = plan_result["evidence_revision_id"]
    assert isinstance(revision, str)
    assert len(revision) == 64
    assert load_evidence(factory, 1, revision) is not None
    assert count_rows(factory) == 1

    chat_result = handler(chat_payload(), lambda: None)
    assert chat_result["status"] == "planned"
    assert chat_result["plan"] is not None
    chat_revision = chat_result["evidence_revision_id"]
    assert isinstance(chat_revision, str)
    assert load_evidence(factory, 1, chat_revision) is not None
    assert count_rows(factory) == 2
    assert len(provider.requests) == 2


def test_handler_rejects_unknown_operation_before_external_work(
    factory: sessionmaker[Session],
) -> None:
    handler = make_agent_handler(factory, FailLLM())
    with pytest.raises(ValueError, match="operation is invalid") as caught:
        handler({"operation": "purchase"}, lambda: None)
    assert "purchase" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert count_rows(factory) == 0


def test_handler_plan_recorder_persists_without_provider(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    handler = make_agent_handler(factory, None)
    result = handler(payload(), lambda: None)
    revision = result["evidence_revision_id"]
    assert isinstance(revision, str)
    snapshot = load_evidence(factory, 1, revision)
    assert snapshot is not None
    assert snapshot["planning"]["spending_source"] == "fixture"


def test_handler_does_not_fake_chat_when_provider_missing(
    factory: sessionmaker[Session],
) -> None:
    handler = make_agent_handler(factory, None)
    with pytest.raises(ChatUnavailable, match="unavailable") as caught:
        handler(chat_payload(), lambda: None)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert count_rows(factory) == 0


def test_handler_invalid_payloads_fail_closed(
    factory: sessionmaker[Session],
) -> None:
    handler = make_agent_handler(factory, FailLLM())
    with pytest.raises(ValidationError):
        handler(payload(unexpected="value"), lambda: None)
    with pytest.raises(ValidationError):
        handler(chat_payload(user_id=1), lambda: None)
    assert count_rows(factory) == 0
