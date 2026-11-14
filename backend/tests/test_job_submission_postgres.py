"""Opt-in PostgreSQL concurrency checks for job submission."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier, Event
from typing import cast
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import require_test_database_url
from sqlalchemy import (
    Connection,
    Engine,
    Table,
    create_engine,
    delete,
    event,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.job_models import Job, JobOutbox
from app.models import User
from app.plan_models import PlanRevision
from app.security_models import QuotaCounter
from app.services import job_leases, job_submission
from app.services.job_leases import claim_job, finish_job, renew_lease
from app.services.job_submission import (
    JobConflict,
    JobInputInvalid,
    create_job,
    find_job,
    reuse_job,
    submit_job,
)
from app.services.security_admission import (
    AdmissionLimitError,
    database_utc_now,
    lock_owner,
)


@pytest.fixture()
def postgres_user() -> Iterator[tuple[Engine, int]]:
    url = require_test_database_url()
    engine = create_engine(
        url,
        connect_args={"options": "-c statement_timeout=15000 -c lock_timeout=10000"},
    )
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("The job concurrency test requires PostgreSQL.")
    user_id = uuid4().int % 2_000_000_000 + 1
    with Session(engine) as session:
        session.add(User(id=user_id, display_name="job-concurrency-fixture"))
        session.commit()
    try:
        yield engine, user_id
    finally:
        with Session(engine) as session:
            jobs = select(Job.id).where(Job.user_id == user_id)
            session.execute(delete(JobOutbox).where(JobOutbox.job_id.in_(jobs)))
            session.execute(delete(Job).where(Job.user_id == user_id))
            session.execute(
                delete(QuotaCounter).where(QuotaCounter.scope_key == user_id)
            )
            session.execute(delete(User).where(User.id == user_id))
            session.commit()
        engine.dispose()


@pytest.fixture()
def isolated_postgres_user() -> Iterator[tuple[Engine, int]]:
    url = require_test_database_url()
    options = "-c statement_timeout=15000 -c lock_timeout=10000"
    admin = create_engine(url, connect_args={"options": options})
    if admin.dialect.name != "postgresql":
        admin.dispose()
        pytest.fail("The job concurrency test requires PostgreSQL.")
    schema = "job_retention_" + uuid4().hex
    engine = create_engine(
        url, connect_args={"options": f"{options} -c search_path={schema}"}
    )
    try:
        with admin.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        with engine.begin() as connection:
            for model in (User, Job, JobOutbox, PlanRevision, QuotaCounter):
                cast(Table, model.__table__).create(connection)
        with Session(engine) as session:
            session.add(User(id=1, display_name="job-retention-fixture"))
            session.commit()
        yield engine, 1
    finally:
        engine.dispose()
        try:
            with admin.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            admin.dispose()


def test_concurrent_requests_create_one_job_and_one_outbox(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    start = Barrier(2)

    def synchronize_inserts(
        mapper: object, connection: Connection, target: Job
    ) -> None:
        if target.user_id == user_id:
            start.wait(timeout=10)

    def submit() -> tuple[str, bool]:
        with Session(engine) as session:
            job, created = create_job(
                session, user_id, "agent", "same", {"meal": "tacos"}
            )
            job_id = job.id
            session.commit()
            return job_id, created

    event.listen(Job, "before_insert", synchronize_inserts)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(Job, "before_insert", synchronize_inserts)
    assert results[0][0] == results[1][0]
    assert sorted(created for _, created in results) == [False, True]
    with Session(engine) as session:
        jobs = select(Job.id).where(Job.user_id == user_id)
        assert (
            session.scalar(
                select(func.count()).select_from(Job).where(Job.user_id == user_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(JobOutbox)
                .where(JobOutbox.job_id.in_(jobs))
            )
            == 1
        )


def test_concurrent_submissions_commit_matching_winner(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    start = Barrier(2)

    def matches(payload: dict[str, object]) -> bool:
        return payload.get("meal") == "tacos"

    def submit(snapshot: int) -> tuple[str, dict[str, object]]:
        with Session(engine) as session:
            start.wait(timeout=10)
            job = submit_job(
                session,
                user_id,
                "agent",
                "service-race",
                {"meal": "tacos", "snapshot": snapshot},
                matches,
            )
            return job.id, job.payload

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(submit, snapshot) for snapshot in range(2)]
        results = [future.result(timeout=20) for future in futures]

    assert results[0] == results[1]
    with Session(engine) as observer:
        jobs = observer.scalars(select(Job).where(Job.user_id == user_id)).all()
        assert len(jobs) == 1
        assert jobs[0].id == results[0][0]
        assert jobs[0].payload == results[0][1]
        outboxes = observer.scalars(
            select(JobOutbox).where(JobOutbox.job_id == jobs[0].id)
        ).all()
        assert len(outboxes) == 1
        assert (
            observer.scalar(
                select(func.sum(QuotaCounter.count)).where(
                    QuotaCounter.action == "mutation", QuotaCounter.scope_key == user_id
                )
            )
            == 1
        )


def test_caller_rollback_removes_job_and_outbox(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        job, created = create_job(session, user_id, "sync", "rollback", {})
        assert created
        job_id = job.id
        session.rollback()
    with Session(engine) as observer:
        assert observer.get(Job, job_id) is None
        assert (
            observer.scalar(select(JobOutbox.id).where(JobOutbox.job_id == job_id))
            is None
        )


def test_retention_deletes_job_before_reuse_acquires_owner_lock(
    postgres_user: tuple[Engine, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        previous, _ = create_job(session, user_id, "agent", "retained", {})
        previous.status = "succeeded"
        previous_id = previous.id
        session.commit()
    waiting = Event()
    require_owner = job_submission.require_active_owner

    def wait_for_owner(session: Session, owner_id: int) -> None:
        waiting.set()
        require_owner(session, owner_id)

    monkeypatch.setattr(job_submission, "require_active_owner", wait_for_owner)

    def retry() -> str:
        with Session(engine) as session:
            reused = reuse_job(session, user_id, "agent", "retained", lambda _: True)
            assert reused is None
            assert not session.in_transaction()
            job = submit_job(session, user_id, "sync", "after-miss", {}, lambda _: True)
            return job.id

    with ThreadPoolExecutor(max_workers=1) as executor, Session(engine) as retention:
        lock_owner(retention, user_id)
        future = executor.submit(retry)
        try:
            assert waiting.wait(timeout=10)
            retention.execute(delete(JobOutbox).where(JobOutbox.job_id == previous_id))
            retention.execute(delete(Job).where(Job.id == previous_id))
            retention.commit()
            replacement_id = future.result(timeout=20)
        finally:
            retention.rollback()
    with Session(engine) as session:
        assert session.get(Job, previous_id) is None
        assert session.get(Job, replacement_id) is not None
        assert (
            session.scalar(
                select(func.sum(QuotaCounter.count)).where(
                    QuotaCounter.scope_key == user_id
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    "reference", ["previous_job_id", "plan_revision_id", "plan_revision"]
)
def test_retention_deletes_chat_reference_before_submit_lock(
    isolated_postgres_user: tuple[Engine, int],
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
) -> None:
    engine, user_id = isolated_postgres_user
    revision_id = uuid4()
    snapshot: dict[str, object] = {"meals": [], "pantry_ingredient_ids": []}
    with Session(engine) as session:
        previous, _ = create_job(session, user_id, "agent", "previous", {})
        previous.status = "succeeded"
        previous_id = previous.id
        session.add(PlanRevision(id=revision_id, user_id=user_id, snapshot=snapshot))
        session.commit()
    payload: dict[str, object] = {
        "operation": "chat",
        "message": "Plan dinner",
        "monthly_limit_cents": 10000,
        "spending": {
            "period": "2026-11-01",
            "posted_cents": 0,
            "pending_cents": 0,
            "refreshed_at": "2026-11-12T12:00:00+00:00",
        },
        "spending_source": "manual",
    }
    if reference == "previous_job_id":
        payload[reference] = previous_id
    elif reference == "plan_revision":
        payload[reference] = {"id": str(revision_id), "snapshot": snapshot}
    else:
        payload[reference] = str(revision_id)
    waiting = Event()
    require_owner = job_submission.require_active_owner

    def wait_for_owner(session: Session, owner_id: int) -> None:
        waiting.set()
        require_owner(session, owner_id)

    monkeypatch.setattr(job_submission, "require_active_owner", wait_for_owner)

    def submit() -> None:
        with Session(engine) as session:
            assert session.scalar(select(func.pg_backend_pid())) != retention_pid
            assert session.get(Job, previous_id) is not None
            assert session.get(PlanRevision, revision_id) is not None
            with pytest.raises(JobInputInvalid):
                submit_job(
                    session, user_id, "agent", "new-chat", payload, lambda _: True
                )
            session.commit()
            assert (
                find_job(
                    session, user_id, "agent", "new-chat", request_namespace="chat"
                )
                is None
            )
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(QuotaCounter)
                    .where(QuotaCounter.scope_key == user_id)
                )
                == 0
            )

    with ThreadPoolExecutor(max_workers=1) as executor, Session(engine) as retention:
        lock_owner(retention, user_id)
        retention_pid = retention.scalar(select(func.pg_backend_pid()))
        future = executor.submit(submit)
        try:
            assert waiting.wait(timeout=10)
            if reference == "previous_job_id":
                retention.execute(
                    delete(JobOutbox).where(JobOutbox.job_id == previous_id)
                )
                retention.execute(delete(Job).where(Job.id == previous_id))
            else:
                retention.execute(
                    delete(PlanRevision).where(PlanRevision.id == revision_id)
                )
            retention.commit()
            future.result(timeout=20)
        finally:
            retention.rollback()
    with Session(engine) as observer:
        expected = 0 if reference == "previous_job_id" else 1
        for model in (Job, JobOutbox):
            assert observer.scalar(select(func.count()).select_from(model)) == expected
        assert observer.scalar(select(func.count()).select_from(QuotaCounter)) == 0


@pytest.mark.parametrize("operation", ["claim", "renew", "finish"])
@pytest.mark.parametrize("disable_owner", [False, True])
def test_lease_checks_use_wall_time_after_waiting_for_owner(
    postgres_user: tuple[Engine, int],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    disable_owner: bool,
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        job, _ = create_job(session, user_id, "agent", "blocked-lease", {})
        job.status = "running"
        job.lease_token = "held"
        job.lease_expires_at = database_utc_now(session) + timedelta(minutes=5)
        job.attempts = 1
        job_id = job.id
        session.commit()
    waiting = Event()
    require_owner = job_leases.require_active_owner

    def wait_for_owner(session: Session, owner_id: int) -> None:
        waiting.set()
        require_owner(session, owner_id)

    monkeypatch.setattr(job_leases, "require_active_owner", wait_for_owner)

    def apply_lease() -> str | bool | None:
        with Session(engine) as session:
            outcome: str | bool | None
            if operation == "claim":
                outcome = claim_job(session, job_id)
            elif operation == "renew":
                outcome = renew_lease(session, job_id, "held")
            else:
                outcome = finish_job(session, job_id, "held", result={"value": "safe"})
            session.commit()
            return outcome

    with ThreadPoolExecutor(max_workers=1) as executor, Session(engine) as maintenance:
        lock_owner(maintenance, user_id)
        future = executor.submit(apply_lease)
        try:
            assert waiting.wait(timeout=10)
            cutoff = database_utc_now(maintenance)
            maintenance.execute(
                update(Job).where(Job.id == job_id).values(lease_expires_at=cutoff)
            )
            if disable_owner:
                maintenance.execute(
                    update(User).where(User.id == user_id).values(status="disabled")
                )
            maintenance.commit()
            outcome = future.result(timeout=20)
        finally:
            maintenance.rollback()
    with Session(engine) as session:
        stored = session.get(Job, job_id)
        assert stored is not None and stored.status == "running"
        assert stored.result is None
        if operation == "claim" and not disable_owner:
            assert isinstance(outcome, str) and outcome != "held"
            assert stored.attempts == 2
            assert stored.lease_expires_at is not None
            assert stored.lease_expires_at >= cutoff + timedelta(seconds=60)
        else:
            assert outcome is (None if operation == "claim" else False)
            assert stored.lease_token == "held"
            assert stored.attempts == 1
            assert stored.lease_expires_at == cutoff


@pytest.fixture()
def second_owner(postgres_user: tuple[Engine, int]) -> Iterator[int]:
    engine, first_id = postgres_user
    owner_id = uuid4().int % 2_000_000_000 + 1
    assert owner_id != first_id
    with Session(engine) as session:
        session.add(User(id=owner_id, display_name="job-global-cap-fixture"))
        session.commit()
    try:
        yield owner_id
    finally:
        with Session(engine) as session:
            jobs = select(Job.id).where(Job.user_id == owner_id)
            session.execute(delete(JobOutbox).where(JobOutbox.job_id.in_(jobs)))
            session.execute(delete(Job).where(Job.user_id == owner_id))
            session.execute(
                delete(QuotaCounter).where(QuotaCounter.scope_key == owner_id)
            )
            session.execute(delete(User).where(User.id == owner_id))
            session.commit()


@pytest.mark.parametrize("boundary", ["user", "global"])
def test_concurrent_distinct_keys_enforce_capacity_atomically(
    postgres_user: tuple[Engine, int], second_owner: int, boundary: str
) -> None:
    engine, user_id = postgres_user
    initial = 199 if boundary == "global" else 0
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.status.in_(("queued", "running")))
            )
            == 0
        )
        for index in range(initial):
            create_job(session, second_owner, "sync", f"global-{index}", {})
        session.commit()
    start = Barrier(4)

    def submit(index: int) -> bool:
        with Session(engine) as session:
            start.wait(timeout=10)
            try:
                submit_job(
                    session,
                    user_id,
                    "sync" if index % 2 else "agent",
                    f"contender-{index}",
                    {},
                    lambda _: True,
                )
            except AdmissionLimitError as exc:
                assert 1 <= exc.retry_after <= 60
                session.commit()
                return False
            return True

    with ThreadPoolExecutor(max_workers=4) as executor:
        admitted = list(executor.map(submit, range(4)))
    accepted = 1 if boundary == "global" else 3
    assert sum(admitted) == accepted
    with Session(engine) as observer:
        jobs = select(Job.id).where(Job.user_id.in_((user_id, second_owner)))
        assert (
            observer.scalar(
                select(func.count()).select_from(Job).where(Job.id.in_(jobs))
            )
            == initial + accepted
        )
        assert (
            observer.scalar(
                select(func.count())
                .select_from(JobOutbox)
                .where(JobOutbox.job_id.in_(jobs))
            )
            == initial + accepted
        )
        assert (
            observer.scalar(
                select(func.sum(QuotaCounter.count)).where(
                    QuotaCounter.action == "mutation", QuotaCounter.scope_key == user_id
                )
            )
            == accepted
        )


def test_service_replays_internal_race_without_consuming_mutation(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    start = Barrier(2)
    internal_committed = Event()

    def synchronize_inserts(
        mapper: object, connection: Connection, target: Job
    ) -> None:
        if target.user_id == user_id:
            start.wait(timeout=10)
            if target.payload.get("snapshot") == 2:
                assert internal_committed.wait(timeout=10)

    def internal() -> str:
        with Session(engine) as session:
            job, _ = create_job(
                session,
                user_id,
                "agent",
                "internal-race",
                {"meal": "tacos", "snapshot": 1},
            )
            session.commit()
            internal_committed.set()
            return job.id

    def service() -> str:
        with Session(engine) as session:
            job = submit_job(
                session,
                user_id,
                "agent",
                "internal-race",
                {"meal": "tacos", "snapshot": 2},
                lambda p: p.get("meal") == "tacos",
            )
            return job.id

    event.listen(Job, "before_insert", synchronize_inserts)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            internal_future = executor.submit(internal)
            service_future = executor.submit(service)
            service_id = service_future.result(timeout=20)
            internal_id = internal_future.result(timeout=20)
    finally:
        event.remove(Job, "before_insert", synchronize_inserts)
    assert internal_id == service_id
    with Session(engine) as observer:
        jobs = observer.scalars(select(Job).where(Job.user_id == user_id)).all()
        assert len(jobs) == 1
        assert (
            observer.scalar(
                select(func.count())
                .select_from(JobOutbox)
                .where(JobOutbox.job_id == service_id)
            )
            == 1
        )
        assert jobs[0].payload.get("snapshot") == 1
        usage = observer.scalar(
            select(func.sum(QuotaCounter.count)).where(
                QuotaCounter.scope_key == user_id
            )
        )
        assert (usage or 0) == 0


def test_concurrent_agent_operations_share_rolling_limit(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        for index in range(19):
            job, _ = create_job(
                session,
                user_id,
                "agent",
                f"recent-{index}",
                {"operation": "chat" if index % 2 else "plan"},
            )
            job.status = "succeeded"
        session.commit()
    start = Barrier(4)

    def submit(index: int) -> bool:
        with Session(engine) as session:
            start.wait(timeout=10)
            try:
                submit_job(
                    session,
                    user_id,
                    "agent",
                    f"new-{index}",
                    {"operation": "chat" if index % 2 else "plan"},
                    lambda _: True,
                )
            except AdmissionLimitError:
                session.commit()
                return False
            return True

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(submit, range(4))) == 1
    with Session(engine) as observer:
        assert (
            observer.scalar(
                select(func.count()).select_from(Job).where(Job.user_id == user_id)
            )
            == 20
        )
        assert (
            observer.scalar(
                select(func.sum(QuotaCounter.count)).where(
                    QuotaCounter.scope_key == user_id
                )
            )
            == 1
        )


def test_service_replay_at_all_limits_preserves_jobs_and_quota(
    postgres_user: tuple[Engine, int], second_owner: int
) -> None:
    engine, user_id = postgres_user
    with Session(engine) as session:
        first = submit_job(
            session, user_id, "agent", "replay", {"value": 1}, lambda _: True
        )
        first_id = first.id
        for index in range(2):
            create_job(session, user_id, "sync", f"active-{index}", {})
        for index in range(19):
            job, _ = create_job(
                session,
                user_id,
                "agent",
                f"done-{index}",
                {"operation": "chat" if index % 2 else "plan"},
            )
            job.status = "succeeded"
        for index in range(197):
            create_job(session, second_owner, "sync", f"other-{index}", {})
        counter = session.scalar(
            select(QuotaCounter).where(QuotaCounter.scope_key == user_id)
        )
        assert counter is not None
        counter.count = 60
        session.commit()
        before = session.scalar(
            select(func.sum(QuotaCounter.count)).where(
                QuotaCounter.scope_key == user_id
            )
        )
        replay = submit_job(
            session,
            user_id,
            "agent",
            "replay",
            {"value": 1, "snapshot": 2},
            lambda p: p.get("value") == 1,
        )
        assert replay.id == first_id
        with pytest.raises(JobConflict):
            submit_job(session, user_id, "agent", "replay", {}, lambda _: False)
        with pytest.raises(AdmissionLimitError):
            submit_job(session, user_id, "agent", "rejected", {}, lambda _: True)
        session.commit()
        assert (
            session.scalar(
                select(func.sum(QuotaCounter.count)).where(
                    QuotaCounter.scope_key == user_id
                )
            )
            == before
        )
        jobs = select(Job.id).where(Job.user_id.in_((user_id, second_owner)))
        assert (
            session.scalar(
                select(func.count()).select_from(Job).where(Job.id.in_(jobs))
            )
            == 219
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(JobOutbox)
                .where(JobOutbox.job_id.in_(jobs))
            )
            == 219
        )


@pytest.mark.parametrize("legacy_rows", [False, True])
def test_namespace_migration_preserves_legacy_keys_and_outboxes(
    postgres_user: tuple[Engine, int],
    monkeypatch: pytest.MonkeyPatch,
    legacy_rows: bool,
) -> None:
    engine, _ = postgres_user
    path = (
        Path(__file__).resolve().parents[1] / "alembic/versions/0015_job_admission.py"
    )
    spec = spec_from_file_location("job_admission_migration", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    schema = "job_admission_" + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            connection.exec_driver_sql("CREATE TABLE users (id bigint PRIMARY KEY)")
            connection.exec_driver_sql("INSERT INTO users VALUES (1)")
            connection.exec_driver_sql(
                "CREATE TABLE jobs (id varchar(36) PRIMARY KEY, "
                "user_id bigint NOT NULL REFERENCES users(id), kind text NOT NULL, "
                "request_key text NOT NULL, status text NOT NULL DEFAULT 'queued', "
                "payload json NOT NULL, result json, error_code text, "
                "attempts integer NOT NULL DEFAULT 0, lease_token text, "
                "lease_expires_at timestamptz, "
                "created_at timestamptz NOT NULL DEFAULT now(), "
                "CONSTRAINT uq_jobs_user_kind_request_key "
                "UNIQUE(user_id, kind, request_key))"
            )
            connection.exec_driver_sql(
                "CREATE TABLE job_outbox (id varchar(36) PRIMARY KEY, "
                "job_id varchar(36) NOT NULL UNIQUE REFERENCES jobs(id), "
                "published_at timestamptz, "
                "created_at timestamptz NOT NULL DEFAULT now())"
            )
            if legacy_rows:
                connection.exec_driver_sql(
                    "INSERT INTO jobs(id,user_id,kind,request_key,payload) VALUES "
                    "('legacy-plan',1,'agent','chat:same','{}'), "
                    "('legacy-chat',1,'agent','chat:old','{\"operation\":\"chat\"}'), "
                    "('legacy-sync',1,'sync','unchanged-sync',"
                    '\'{"operation":"chat"}\')'
                )
                connection.exec_driver_sql(
                    "INSERT INTO job_outbox(id,job_id) "
                    "SELECT 'outbox-' || id,id FROM jobs"
                )
            before_jobs = connection.exec_driver_sql(
                "SELECT to_jsonb(j) FROM jobs j ORDER BY id"
            ).all()
            before_outbox = connection.exec_driver_sql(
                "SELECT to_jsonb(o) FROM job_outbox o ORDER BY id"
            ).all()
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )
            migration.upgrade()
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.exec_driver_sql(
                    "INSERT INTO jobs "
                    "(id,user_id,kind,request_key,payload,request_namespace) "
                    "VALUES ('wrong-namespace',1,'agent','wrong',"
                    "'{\"operation\":\"chat\"}','plan')"
                )
            assert (
                connection.exec_driver_sql(
                    "SELECT to_jsonb(j) - 'request_namespace' FROM jobs j ORDER BY id"
                ).all()
                == before_jobs
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT to_jsonb(o) FROM job_outbox o ORDER BY id"
                ).all()
                == before_outbox
            )
            if legacy_rows:
                assert connection.exec_driver_sql(
                    "SELECT id, request_namespace FROM jobs ORDER BY id"
                ).all() == [
                    ("legacy-chat", "chat"),
                    ("legacy-plan", "plan"),
                    ("legacy-sync", "sync"),
                ]
            with Session(
                bind=connection, join_transaction_mode="create_savepoint"
            ) as session:
                chat, created = create_job(
                    session, 1, "agent", "chat:same", {"operation": "chat"}
                )
                assert created
                assert chat.request_key == "chat:same"
                assert (
                    find_job(session, 1, "agent", "chat:same", request_namespace="chat")
                    is chat
                )
                if legacy_rows:
                    plan = find_job(session, 1, "agent", "chat:same")
                    assert plan is not None and plan.id == "legacy-plan"
                    replay, created = create_job(session, 1, "agent", "chat:same", {})
                    assert not created and replay.id == plan.id
                    sync = find_job(session, 1, "sync", "unchanged-sync")
                    assert sync is not None and sync.id == "legacy-sync"
                replay, created = create_job(
                    session, 1, "agent", "chat:same", {"operation": "chat"}
                )
                assert not created and replay.id == chat.id
                session.commit()
            with pytest.raises(NotImplementedError, match="forward-only"):
                migration.downgrade()
        finally:
            transaction.rollback()
