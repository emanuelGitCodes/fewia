"""Tests for handoff snapshot helpers without the HTTP router."""

import copy
import json
import sqlite3
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from test_evidence_contract import genuine_planning, inputs

from app import models
from app.api.handoff_models import (
    DENIED,
    JOB_MISSING,
    NO_ITEMS,
    PLANNING_KEYS,
    REBUILD,
    HandoffRouteError,
    job_shopping_payload,
    may_retry,
    planning_fields,
    revision_id,
)
from app.db import Base
from app.evidence_models import GroceryEvidence
from app.job_models import Job
from app.services.evidence_contract import canonical_json
from app.services.evidence_store import load_evidence, save_plan_evidence
from app.services.handoff_intents import HandoffView

SECRET = "sk-test-not-for-models"
CHAT_EXTRA: dict[str, object] = {
    "status": "planned",
    "answer": "Here is an estimated plan.",
    "tool_trace": [{"marker": SECRET}],
    "model_turns": 2,
    "planner_revisions": 1,
    "usage": {"inputTokens": 9, "outputTokens": 4},
}
BEAN_PANTRY = [
    "black_beans",
    "cumin",
    "olive_oil",
    "onion",
    "salsa",
    "salt",
    "tortillas",
]
PAYLOAD_KEYS = {"expires_in", "line_items", "link_type", "title"}
HEX_REVISION = "ab" * 32


@pytest.fixture()
def handoff_engine(tmp_path: Path) -> Iterator[Engine]:
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'handoff-api-models.db'}",
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

    tables = [models.User.__table__, Job.__table__, GroceryEvidence.__table__]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def factory(handoff_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=handoff_engine, expire_on_commit=False)


@pytest.fixture()
def owners(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))
        session.add(models.User(id=2, display_name="Other"))


def planning_result(
    planning: dict[str, object],
    revision: str,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    result = {key: planning[key] for key in PLANNING_KEYS}
    result["evidence_revision_id"] = revision
    if extra is not None:
        result.update(extra)
    return result


def add_job(
    factory: sessionmaker[Session],
    planning: dict[str, object],
    revision: str,
    *,
    extra: dict[str, object] | None = None,
    user_id: int = 1,
    status: str = "succeeded",
    kind: str = "agent",
) -> str:
    job = Job(
        user_id=user_id,
        kind=kind,
        request_key=str(uuid4()),
        status=status,
        payload={"marker": SECRET},
        result=planning_result(planning, revision, extra),
    )
    with factory.begin() as session:
        session.add(job)
        session.flush()
        return job.id


def accepted_job(
    factory: sessionmaker[Session],
    extra: dict[str, object] | None = None,
    **request_overrides: object,
) -> str:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed, **request_overrides)
    revision = save_plan_evidence(factory, 1, planning, parsed)
    return add_job(factory, planning, revision, extra=extra)


def catch_route_error(factory: sessionmaker[Session], job_id: str) -> HandoffRouteError:
    caught: HandoffRouteError | None = None
    try:
        job_shopping_payload(factory, job_id)
    except HandoffRouteError as exc:
        caught = exc
    assert caught is not None
    assert caught.__cause__ is None
    assert caught.__context__ is None
    assert SECRET not in str(caught)
    assert SECRET not in caught.detail
    return caught


def sample_view(
    *,
    state: str,
    attempts: int = 1,
    retry_allowed: bool = False,
) -> HandoffView:
    return HandoffView(
        id="00000000-0000-0000-0000-000000000001",
        state=state,
        attempts=attempts,
        url=None,
        error_code=None,
        expires_at=None,
        retry_allowed=retry_allowed,
    )


def test_planning_fields_keep_plan_keys_and_drop_chat_extras() -> None:
    result = {key: key for key in PLANNING_KEYS}
    result.update(CHAT_EXTRA)
    fields = planning_fields(result)

    assert fields == {key: key for key in PLANNING_KEYS}
    assert planning_fields({"request": 1, "plan": 2}) is None


def test_revision_id_accepts_lowercase_hex_only() -> None:
    assert revision_id(HEX_REVISION) == HEX_REVISION
    assert revision_id("AB" * 32) is None
    assert revision_id("a" * 63) is None
    assert revision_id("g" * 64) is None
    assert revision_id(1) is None
    assert revision_id(None) is None


def test_accepted_plain_plan_rebuilds_shopping_payload(
    factory: sessionmaker[Session], owners: None
) -> None:
    job_id = accepted_job(factory)
    payload = job_shopping_payload(factory, job_id)
    rendered = json.dumps(payload)

    assert set(payload) == PAYLOAD_KEYS
    assert payload["title"] == "FEWIA grocery plan"
    assert payload["link_type"] == "shopping_list"
    assert payload["expires_in"] == 7
    assert isinstance(payload["line_items"], list)
    assert payload["line_items"]
    assert SECRET not in rendered
    assert "attempt_token" not in rendered


def test_chat_result_extra_fields_do_not_change_payload(
    factory: sessionmaker[Session], owners: None
) -> None:
    job_id = accepted_job(factory, extra=CHAT_EXTRA)
    payload = job_shopping_payload(factory, job_id)
    plain = job_shopping_payload(factory, accepted_job(factory))

    assert payload == plain
    assert SECRET not in json.dumps(payload)


def test_tampered_job_rebuilds_while_snapshot_stays(
    factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    revision = save_plan_evidence(factory, 1, planning, parsed)
    job_id = add_job(factory, planning, revision)
    with factory.begin() as session:
        job = session.get(Job, job_id)
        assert job is not None
        result = dict(cast(dict[str, object], job.result))
        plan = copy.deepcopy(cast(dict[str, object], result["plan"]))
        plan["accepted"] = not bool(plan["accepted"])
        result["plan"] = plan
        job.result = result
    snapshot = load_evidence(factory, 1, revision)
    assert snapshot is not None
    stored = snapshot["planning"]
    assert isinstance(stored, dict)
    stored_plan = stored["plan"]
    assert isinstance(stored_plan, dict)
    assert stored_plan["accepted"] is True
    error = catch_route_error(factory, job_id)

    assert error.status == 409
    assert error.detail == REBUILD


def test_missing_and_foreign_jobs_are_static_404(
    factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    revision = save_plan_evidence(factory, 1, planning, parsed)
    foreign = add_job(factory, planning, revision, user_id=2)
    queued = add_job(factory, planning, revision, status="queued")
    sync = add_job(factory, planning, revision, kind="sync")
    missing = catch_route_error(factory, str(uuid4()))
    other = catch_route_error(factory, foreign)
    inactive = catch_route_error(factory, queued)
    wrong_kind = catch_route_error(factory, sync)

    assert missing.status == 404
    assert other.status == 404
    assert inactive.status == 404
    assert wrong_kind.status == 404
    assert missing.detail == JOB_MISSING
    assert other.detail == JOB_MISSING
    assert inactive.detail == JOB_MISSING
    assert wrong_kind.detail == JOB_MISSING


def test_missing_and_foreign_evidence_require_rebuild(
    factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs()
    other_plan = genuine_planning(user_id=2, evidence_inputs=parsed)
    other_rev = save_plan_evidence(factory, 2, other_plan, parsed)
    foreign = add_job(factory, other_plan, other_rev)
    planning = genuine_planning(evidence_inputs=parsed)
    missing = add_job(factory, planning, HEX_REVISION)
    foreign_error = catch_route_error(factory, foreign)
    missing_error = catch_route_error(factory, missing)

    assert load_evidence(factory, 1, other_rev) is None
    assert load_evidence(factory, 1, HEX_REVISION) is None
    assert foreign_error.status == 409
    assert missing_error.status == 409
    assert foreign_error.detail == REBUILD
    assert missing_error.detail == REBUILD


def test_malformed_revision_requires_rebuild(
    factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs()
    planning = genuine_planning(evidence_inputs=parsed)
    revision = save_plan_evidence(factory, 1, planning, parsed)
    dropped_id = add_job(factory, planning, revision)
    with factory.begin() as session:
        job = session.get(Job, dropped_id)
        assert job is not None
        job.result = {key: planning[key] for key in PLANNING_KEYS}
    numeric_id = add_job(factory, planning, revision)
    with factory.begin() as session:
        job = session.get(Job, numeric_id)
        assert job is not None
        result = dict(cast(dict[str, object], job.result))
        result["evidence_revision_id"] = 1
        job.result = result
    uppercase = add_job(factory, planning, "AB" * 32)
    short = add_job(factory, planning, "a" * 63)
    none_result = Job(
        user_id=1,
        kind="agent",
        request_key=str(uuid4()),
        status="succeeded",
        payload={"marker": SECRET},
        result=None,
    )
    with factory.begin() as session:
        session.add(none_result)
        session.flush()
        none_id = none_result.id
    dropped = catch_route_error(factory, dropped_id)
    numeric = catch_route_error(factory, numeric_id)
    bad_hex = catch_route_error(factory, uppercase)
    truncated = catch_route_error(factory, short)
    empty = catch_route_error(factory, none_id)

    assert dropped.status == 409
    assert numeric.status == 409
    assert bad_hex.status == 409
    assert truncated.status == 409
    assert empty.status == 409
    assert dropped.detail == REBUILD
    assert numeric.detail == REBUILD
    assert bad_hex.detail == REBUILD
    assert truncated.detail == REBUILD
    assert empty.detail == REBUILD


def test_incomplete_denied_and_all_pantry_plans(
    factory: sessionmaker[Session], owners: None
) -> None:
    parsed = inputs(plan_cap_cents=1)
    rejected_plan = genuine_planning(evidence_inputs=parsed, plan_cap_cents=1)
    rejected_rev = save_plan_evidence(factory, 1, rejected_plan, parsed)
    rejected_id = add_job(factory, rejected_plan, rejected_rev)
    pantry_id = accepted_job(factory, pantry_ingredients=BEAN_PANTRY)
    incomplete = copy.deepcopy(genuine_planning())
    plan = cast(dict[str, object], incomplete["plan"])
    plan["total_cents"] = None
    plan["accepted"] = True
    incomplete["plan"] = plan
    snapshot = {
        "planning": incomplete,
        "budget_inputs": inputs().model_dump(mode="json"),
    }
    evidence_id = sha256(
        canonical_json({"user_id": 1, "snapshot": snapshot}).encode("utf-8")
    ).hexdigest()
    with factory.begin() as session:
        session.add(GroceryEvidence(id=evidence_id, user_id=1, snapshot=snapshot))
    incomplete_id = add_job(factory, incomplete, evidence_id)
    rejected = catch_route_error(factory, rejected_id)
    pantry = catch_route_error(factory, pantry_id)
    missing_total = catch_route_error(factory, incomplete_id)

    assert rejected.status == 409
    assert pantry.status == 409
    assert missing_total.status == 409
    assert rejected.detail == DENIED
    assert pantry.detail == NO_ITEMS
    assert missing_total.detail == DENIED


def test_route_error_status_and_detail_are_static() -> None:
    missing = HandoffRouteError(404, JOB_MISSING)
    rebuild = HandoffRouteError(409, REBUILD)
    denied = HandoffRouteError(409, DENIED)
    empty = HandoffRouteError(409, NO_ITEMS)

    assert missing.status == 404
    assert missing.detail == JOB_MISSING
    assert rebuild.status == 409
    assert rebuild.detail == REBUILD
    assert denied.detail == DENIED
    assert empty.detail == NO_ITEMS
    assert missing.__context__ is None
    assert rebuild.__context__ is None
    assert denied.__context__ is None
    assert empty.__context__ is None
    assert missing.__cause__ is None


@pytest.mark.parametrize(
    ("state", "attempts", "expected_attempt", "retry_allowed", "allowed"),
    [
        ("uncertain", 1, 1, False, True),
        ("failed", 2, 2, False, True),
        ("succeeded", 1, 1, True, True),
        ("succeeded", 1, 1, False, False),
        ("uncertain", 1, 9, True, False),
        ("failed", 1, 2, False, False),
        ("prepared", 1, 1, False, False),
        ("dispatching", 1, 1, False, False),
    ],
)
def test_may_retry_fences_stale_and_cached_states(
    state: str,
    attempts: int,
    expected_attempt: int,
    retry_allowed: bool,
    allowed: bool,
) -> None:
    view = sample_view(state=state, attempts=attempts, retry_allowed=retry_allowed)

    assert may_retry(view, expected_attempt) is allowed
