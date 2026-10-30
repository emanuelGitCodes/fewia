import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

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
from app.job_models import Job, JobOutbox
from app.providers.local_sqs_consumer import QueueMessage
from app.services import chat_job as chat_job_module
from app.services import plan_job as plan_job_module
from app.services.agent_jobs import make_agent_handler
from app.services.evidence_store import load_evidence
from app.services.job_consumer import process_one
from app.services.job_submission import create_job


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

    tables = [
        models.User.__table__,
        GroceryEvidence.__table__,
        Job.__table__,
        JobOutbox.__table__,
    ]
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


class FakeQueue:
    def __init__(self, body: str) -> None:
        self.message = QueueMessage(body=body, receipt_handle="receipt")

    def receive(self) -> QueueMessage:
        return self.message

    def acknowledge(self, message: QueueMessage) -> None:
        assert message == self.message

    def extend(self, message: QueueMessage, seconds: int) -> None:
        assert message == self.message
        del seconds


def submit_agent_job(factory: sessionmaker[Session], body: dict[str, object]) -> str:
    with factory.begin() as session:
        job, created = create_job(session, 1, "agent", str(uuid4()), body)
        assert created is True
        return job.id


def stored_job(factory: sessionmaker[Session], job_id: str) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


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
    assert len(provider.requests) == 1


def test_process_one_succeeds_for_plan_and_chat(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    provider = FakeLLM(_planner_then_final())
    handler = make_agent_handler(factory, provider)
    plan_body = plan_job_module.PlanJobInput.model_validate(payload()).model_dump(
        mode="json"
    )
    chat_body = chat_job_module.ChatJobInput.model_validate(chat_payload()).model_dump(
        mode="json"
    )
    plan_id = submit_agent_job(factory, plan_body)
    chat_id = submit_agent_job(factory, chat_body)
    plan_queue = FakeQueue(json.dumps({"job_id": plan_id}))
    chat_queue = FakeQueue(json.dumps({"job_id": chat_id}))
    assert (
        process_one(factory, plan_queue, "agent", handler, now=lambda: NOW)
        == "succeeded"
    )
    assert (
        process_one(factory, chat_queue, "agent", handler, now=lambda: NOW)
        == "succeeded"
    )
    plan_job_row = stored_job(factory, plan_id)
    chat_job_row = stored_job(factory, chat_id)
    assert plan_job_row.status == "succeeded"
    assert chat_job_row.status == "succeeded"
    assert plan_job_row.result is not None
    assert chat_job_row.result is not None


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
