"""Tests for durable job result supermarket estimate removal."""

import importlib.util
import json
import threading
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from conftest import UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker
from test_job_submission import seed_user as seed_job_user
from test_worker import (
    SECRET,
    SPOONACULAR_KEY_MARKER,
    clear_fewia,
    dummy_handler,
    forbid_provider_builds,
    invoke_main,
)

from app import worker
from app.job_models import Job
from app.provider_settings import GroceryProviderSettings
from app.services.job_delivery import JobHandler, JobQueue
from app.services.job_leases import claim_job, finish_job
from app.services.job_result import without_supermarket_estimate
from app.services.job_submission import create_job

pytest_plugins = ["test_job_submission", "test_job_submission_postgres"]

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "alembic"
    / "versions"
    / "0008_remove_stored_supermarket_estimates.py"
)
NESTED_ESTIMATE = {"total_cents": 12, "notice": "nested"}
ROOT_ESTIMATE = {"total_cents": 99, "notice": "root"}


def stored_result() -> dict[str, object]:
    return {
        "status": "ok",
        "answer": "Here is a labeled estimate.",
        "budget": {"available_cents": 7500, "pending_cents": 400},
        "plan": {
            "total_cents": 2100,
            "notice": "Estimated from the demo price catalog.",
            "supermarket_estimate": dict(NESTED_ESTIMATE),
        },
        "nutrition": {
            "notice": "Estimated nutrition from USDA FoodData Central.",
            "total": {
                "energy_kcal": 640,
                "protein_mg": 32000,
                "carbohydrate_mg": 80000,
                "fat_mg": 18000,
            },
        },
        "evidence_revision_id": "a" * 64,
        "supermarket_estimate": dict(ROOT_ESTIMATE),
    }


def load_revision_0008() -> ModuleType:
    spec = importlib.util.spec_from_file_location("alembic_rev_0008", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def add_job(
    session: Session,
    *,
    result: dict[str, object] | None,
    payload: dict[str, object],
    request_key: str | None = None,
) -> Job:
    job = Job(
        id=str(uuid4()),
        user_id=1,
        kind="agent",
        request_key=request_key or str(uuid4()),
        payload=payload,
        result=result,
        status="succeeded",
        attempts=0,
    )
    session.add(job)
    session.flush()
    return job


def test_projection_copies_and_drops_only_root_estimate() -> None:
    original = stored_result()
    snapshot = json.loads(json.dumps(original))

    projected = without_supermarket_estimate(original)

    assert projected is not original
    assert projected is not None
    assert original == snapshot
    assert "supermarket_estimate" not in projected
    assert projected["budget"] == snapshot["budget"]
    assert projected["nutrition"] == snapshot["nutrition"]
    assert projected["plan"] == snapshot["plan"]
    assert projected["answer"] == snapshot["answer"]
    assert projected["evidence_revision_id"] == snapshot["evidence_revision_id"]
    assert projected["status"] == snapshot["status"]
    projected["budget"] = {"available_cents": 0}
    assert original["budget"] == snapshot["budget"]
    assert without_supermarket_estimate(None) is None
    empty: dict[str, object] = {}
    copied = without_supermarket_estimate(empty)
    assert copied == {}
    assert copied is not empty


def test_finish_job_strips_root_estimate_and_keeps_macros(
    job_session: Session,
) -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    seed_job_user(job_session)
    job, created = create_job(job_session, 1, "agent", "retain-1", {"meal": "tacos"})
    assert created is True
    job_session.flush()
    token = claim_job(job_session, job.id, now=now)
    assert token is not None
    original = stored_result()
    snapshot = json.loads(json.dumps(original))

    assert finish_job(job_session, job.id, token, now=now, result=original) is True

    assert original == snapshot
    job_session.expire_all()
    stored = job_session.get(Job, job.id)
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.result is not None
    assert "supermarket_estimate" not in stored.result
    assert stored.result["budget"] == snapshot["budget"]
    assert stored.result["nutrition"] == snapshot["nutrition"]
    assert stored.result["plan"] == snapshot["plan"]
    assert stored.result["evidence_revision_id"] == snapshot["evidence_revision_id"]


def test_grocery_and_chat_get_omit_legacy_root_estimate(
    client: TestClient, session: Session, seed_user: UserSeeder
) -> None:
    seed_user()
    legacy = stored_result()
    snapshot = json.loads(json.dumps(legacy))
    plan_job = add_job(
        session,
        result=legacy,
        payload={"request": {"meals": []}},
        request_key="plan-legacy",
    )
    chat_job = add_job(
        session,
        result=legacy,
        payload={"operation": "chat", "message": "plan meals"},
        request_key="chat-legacy",
    )

    plan_body = client.get(f"/grocery/jobs/{plan_job.id}").json()
    chat_body = client.get(f"/grocery/chat/jobs/{chat_job.id}").json()
    stored_plan = session.get(Job, plan_job.id)
    stored_chat = session.get(Job, chat_job.id)

    assert stored_plan is not None and stored_chat is not None
    assert stored_plan.result == snapshot
    assert stored_chat.result == snapshot
    assert "supermarket_estimate" not in plan_body["result"]
    assert "supermarket_estimate" not in chat_body["result"]
    assert plan_body["result"]["budget"] == snapshot["budget"]
    assert plan_body["result"]["nutrition"] == snapshot["nutrition"]
    assert chat_body["result"]["answer"] == snapshot["answer"]
    assert chat_body["status"] == "succeeded"


def test_worker_default_agent_does_not_call_price_builder(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clear_fewia(monkeypatch)
    forbid_provider_builds(monkeypatch)
    settings = GroceryProviderSettings(
        spoonacular_key_file=Path(SPOONACULAR_KEY_MARKER)
    )
    captured: list[object] = []

    def boom(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("spoonacular")

    def loaded() -> GroceryProviderSettings:
        return settings

    def fake_agent(
        factory: sessionmaker[Session], provider: object, **kwargs: object
    ) -> JobHandler:
        del factory, provider
        captured.append("supermarket_estimator" in kwargs)
        return dummy_handler

    monkeypatch.setattr(worker, "load_provider_settings", loaded)
    monkeypatch.setattr("app.provider_runtime.build_spoonacular", boom)
    monkeypatch.setattr(worker, "make_agent_handler", fake_agent)
    stop = threading.Event()

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, handler
        assert kind == "agent"
        stop.set()
        return "succeeded"

    code = invoke_main(
        monkeypatch,
        processor=processor,
        handler=None,
        stop=stop,
    )
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 0
    assert captured == [False]
    assert not hasattr(worker, "build_spoonacular")
    assert not hasattr(worker, "_spoonacular_estimator")
    assert result["status"] == "stopped"
    assert SPOONACULAR_KEY_MARKER not in output.out
    assert SPOONACULAR_KEY_MARKER not in output.err
    assert SECRET not in output.out
    assert SECRET not in output.err


def test_migration_0008_compiles_for_postgresql() -> None:
    module = load_revision_0008()
    assert module.revision == "0008"
    assert module.down_revision == "0007"
    buffer = StringIO()
    context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={"as_sql": True, "output_buffer": buffer, "literal_binds": True},
    )
    with Operations.context(context):
        module.upgrade()
    sql = buffer.getvalue()
    assert "UPDATE jobs" in sql
    assert "supermarket_estimate" in sql
    assert "result::jsonb" in sql
    assert "(result::jsonb - 'supermarket_estimate')::json" in sql
    assert "jsonb_exists(result::jsonb, 'supermarket_estimate')" in sql
    assert "grocery_evidence" not in sql
    assert "DELETE FROM" not in sql.upper()
    with pytest.raises(RuntimeError, match="Forward-only"):
        module.downgrade()


def test_migration_0008_strips_postgres_rows_when_fixture_present(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    if engine.dialect.name != "postgresql":
        pytest.fail("The retention migration test requires PostgreSQL.")
    module = load_revision_0008()
    job_id = str(uuid4())
    plain_id = str(uuid4())
    null_id = str(uuid4())
    payload = {"request": {"meals": []}}
    result = stored_result()
    unrelated = {"budget": {"available_cents": 1}}
    with Session(engine) as session:
        evidence_before = session.scalar(text("SELECT count(*) FROM grocery_evidence"))
        session.add(
            Job(
                id=job_id,
                user_id=user_id,
                kind="agent",
                request_key=f"retain-{job_id}",
                payload=payload,
                result=result,
                status="succeeded",
                attempts=0,
            )
        )
        session.add(
            Job(
                id=plain_id,
                user_id=user_id,
                kind="agent",
                request_key=f"plain-{job_id}",
                payload=payload,
                result=unrelated,
                status="succeeded",
                attempts=0,
            )
        )
        session.add(
            Job(
                id=null_id,
                user_id=user_id,
                kind="agent",
                request_key=f"null-{job_id}",
                payload=payload,
                result=None,
                status="failed",
                attempts=0,
            )
        )
        session.commit()
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
    with Session(engine) as session:
        stored = session.get(Job, job_id)
        plain = session.get(Job, plain_id)
        missing = session.get(Job, null_id)
        evidence_after = session.scalar(text("SELECT count(*) FROM grocery_evidence"))
        assert stored is not None and plain is not None and missing is not None
        assert stored.result is not None
        assert "supermarket_estimate" not in stored.result
        assert stored.result["budget"] == result["budget"]
        assert stored.result["nutrition"] == result["nutrition"]
        assert stored.result["plan"] == result["plan"]
        assert plain.result == unrelated
        assert missing.result is None
        assert evidence_after == evidence_before
        assert session.scalar(select(Job.id).where(Job.id == job_id)) == job_id
