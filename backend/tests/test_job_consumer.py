"""Test durable job execution and acknowledgment ordering."""

import json
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.job_models import Job
from app.providers.local_sqs_consumer import QueueMessage
from app.services import job_consumer
from app.services.heartbeat import Heartbeat
from app.services.job_consumer import (
    LeaseLost,
    RetryableJobError,
    process_one,
)
from app.services.job_delivery import JobFailure
from app.services.job_leases import claim_job
from app.services.job_submission import create_job
from app.services.plan_job import plan_job

pytest_plugins = ["test_job_submission"]

T0 = datetime(2026, 1, 1, tzinfo=UTC)


class FakeQueue:
    def __init__(self, body: str) -> None:
        self.message = QueueMessage(body=body, receipt_handle="receipt")
        self.events: list[str] = []
        self.extensions = 0
        self.acknowledgments = 0
        self.fail_ack = False
        self.fail_extension_on: int | None = None

    def receive(self) -> QueueMessage:
        self.events.append("receive")
        return self.message

    def acknowledge(self, message: QueueMessage) -> None:
        assert message == self.message
        self.events.append("ack")
        self.acknowledgments += 1
        if self.fail_ack:
            raise RuntimeError("ack failed")

    def extend(self, message: QueueMessage, seconds: int) -> None:
        assert message == self.message
        assert seconds == 120
        self.extensions += 1
        self.events.append("extend")
        if self.fail_extension_on == self.extensions:
            raise RuntimeError("visibility failed")


@pytest.fixture()
def factory(job_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=job_engine, expire_on_commit=False)


def seed_job(
    factory: sessionmaker[Session],
    *,
    kind: str = "agent",
    payload: dict[str, object] | None = None,
) -> str:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="User 1"))
        session.flush()
        job, created = create_job(
            session, 1, kind, str(uuid4()), payload or {"value": "safe"}
        )
        assert created is True
        return job.id


def body(job_id: str) -> str:
    return json.dumps({"job_id": job_id})


def stored_job(factory: sessionmaker[Session], job_id: str) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


def test_success_claims_before_handler_and_acknowledges_after_finish(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory, payload={"value": "safe"})
    queue = FakeQueue(body(job_id))
    observed: dict[str, object] = {}

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        heartbeat()
        observed.update(payload)
        running = stored_job(factory, job_id)
        assert running.status == "running"
        return {"answer": "safe"}

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "succeeded"
    finished = stored_job(factory, job_id)
    assert finished.status == "succeeded"
    assert finished.result == {"answer": "safe"}
    assert observed == {"value": "safe"}
    assert queue.events == ["receive", "extend", "extend", "extend", "ack"]


def test_terminal_duplicate_acknowledges_without_handler(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    with factory.begin() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "succeeded"

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        raise AssertionError("terminal jobs do not invoke handlers")

    queue = FakeQueue(body(job_id))
    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "terminal"
    assert queue.acknowledgments == 1
    assert queue.extensions == 0


def test_active_duplicate_extends_without_acknowledgment(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    with factory.begin() as session:
        token = claim_job(session, job_id, now=T0)
        assert token is not None

    called = False

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    queue = FakeQueue(body(job_id))
    assert (
        process_one(
            factory, queue, "agent", handler, now=lambda: T0 + timedelta(seconds=30)
        )
        == "busy"
    )
    assert called is False
    assert queue.acknowledgments == 0
    assert queue.extensions == 1


def test_running_without_lease_expiry_is_busy_without_acknowledgment(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    with factory.begin() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "running"
        job.lease_token = "other-worker"
        job.lease_expires_at = None

    queue = FakeQueue(body(job_id))

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        raise AssertionError("unclaimed running jobs do not invoke handlers")

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "busy"
    held = stored_job(factory, job_id)
    assert held.status == "running"
    assert held.lease_token == "other-worker"
    assert held.lease_expires_at is None
    assert queue.acknowledgments == 0
    assert queue.extensions == 1


def test_raced_queued_job_is_invalid_without_acknowledgment(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = seed_job(factory)

    def raced_claim(
        session: Session, claimed_job_id: str, *, now: datetime
    ) -> str | None:
        return None

    monkeypatch.setattr(job_consumer, "claim_job", raced_claim)
    queue = FakeQueue(body(job_id))

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        raise AssertionError("unclaimed jobs do not invoke handlers")

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "invalid"
    queued = stored_job(factory, job_id)
    assert queued.status == "queued"
    assert queued.attempts == 0
    assert queue.acknowledgments == 0
    assert queue.extensions == 0


@pytest.mark.parametrize(
    "message_body",
    ["", "not-json", json.dumps({"job_id": "not-a-uuid"}), json.dumps({})],
)
def test_malformed_envelopes_are_not_deleted(
    factory: sessionmaker[Session], message_body: str
) -> None:
    queue = FakeQueue(message_body)

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        return {}

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "invalid"
    assert queue.acknowledgments == 0
    assert queue.extensions == 0


@pytest.mark.parametrize("conflicting", [True, False])
def test_duplicate_envelopes_are_rejected_without_handler_or_mutation(
    factory: sessionmaker[Session], conflicting: bool
) -> None:
    job_id = seed_job(factory)
    duplicate_id = str(uuid4()) if conflicting else job_id
    duplicate_body = f'{{"job_id":"{job_id}","job_id":"{duplicate_id}"}}'
    queue = FakeQueue(duplicate_body)
    called = False

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "invalid"
    queued = stored_job(factory, job_id)
    assert called is False
    assert queued.status == "queued"
    assert queued.attempts == 0
    assert queued.lease_token is None
    assert queue.acknowledgments == 0
    assert queue.extensions == 0


@pytest.mark.parametrize("extra_body", [" " * 240, "[" * 200 + "]" * 200])
def test_oversized_and_deep_envelopes_are_rejected_before_mutation(
    factory: sessionmaker[Session], extra_body: str
) -> None:
    job_id = seed_job(factory)
    oversized_body = body(job_id) + extra_body
    queue = FakeQueue(oversized_body)
    called = False

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "invalid"
    queued = stored_job(factory, job_id)
    assert called is False
    assert queued.status == "queued"
    assert queued.attempts == 0
    assert queued.lease_token is None
    assert queue.acknowledgments == 0
    assert queue.extensions == 0


def test_missing_job_and_wrong_kind_are_invalid(factory: sessionmaker[Session]) -> None:
    missing = FakeQueue(body(str(uuid4())))
    wrong_kind_id = seed_job(factory, kind="sync")

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        return {}

    assert process_one(factory, missing, "agent", handler, now=lambda: T0) == "invalid"
    wrong_kind = FakeQueue(body(wrong_kind_id))
    assert (
        process_one(factory, wrong_kind, "agent", handler, now=lambda: T0) == "invalid"
    )
    assert missing.acknowledgments == wrong_kind.acknowledgments == 0


def test_kind_is_validated_before_receive(factory: sessionmaker[Session]) -> None:
    queue = FakeQueue(body(str(uuid4())))

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        return {}

    with pytest.raises(ValueError):
        process_one(factory, queue, "other", handler)
    assert queue.events == []


def test_exhausted_eligible_claim_is_failed_then_acknowledged(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    with factory.begin() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "running"
        job.attempts = 3
        job.lease_token = "stale"
        job.lease_expires_at = T0 - timedelta(seconds=1)

    queue = FakeQueue(body(job_id))

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        return {}

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "exhausted"
    failed = stored_job(factory, job_id)
    assert failed.status == "failed"
    assert failed.error_code == "attempts_exhausted"
    assert queue.acknowledgments == 1


def test_retry_extends_without_finishing(factory: sessionmaker[Session]) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        heartbeat()
        raise RetryableJobError("provider payload must not persist")

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "retry"
    retried = stored_job(factory, job_id)
    assert retried.status == "running"
    assert retried.result is None
    assert retried.error_code is None
    assert retried.attempts == 1
    assert queue.acknowledgments == 0
    assert queue.extensions == 3


def test_handler_exception_persists_static_error_code(
    factory: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        heartbeat()
        raise RuntimeError("Authorization: Bearer secret-token")

    assert (
        process_one(factory, queue, "agent", handler, now=lambda: T0)
        == "handler_failed"
    )
    failed = stored_job(factory, job_id)
    assert failed.status == "failed"
    assert failed.error_code == "handler_failed"
    assert failed.result is None
    assert "secret-token" not in str(failed.error_code)
    assert queue.acknowledgments == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "secret-token" not in captured.err
    assert captured.err.splitlines() == [
        json.dumps(
            {
                "event": "job_failed",
                "job_id": job_id,
                "error_code": "handler_failed",
                "exception": "RuntimeError",
            },
            sort_keys=True,
        )
    ]


def test_job_failure_persists_detail_and_logs_once(
    factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))
    detail = {"recipe_id": "vegetable_pasta", "ingredient_id": "onion"}

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        heartbeat()
        raise JobFailure("exclusion_reject", detail)

    assert (
        process_one(factory, queue, "agent", handler, now=lambda: T0)
        == "handler_failed"
    )
    failed = stored_job(factory, job_id)
    assert failed.status == "failed"
    assert failed.error_code == "exclusion_reject"
    assert failed.result == {"error_detail": detail}
    assert queue.acknowledgments == 1
    assert queue.events == ["receive", "extend", "extend", "extend", "ack"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == [
        json.dumps(
            {
                "event": "job_failed",
                "job_id": job_id,
                "error_code": "exclusion_reject",
                "exception": "JobFailure",
            },
            sort_keys=True,
        )
    ]


def test_diet_conflict_job_persists_failure_detail(
    factory: sessionmaker[Session],
) -> None:
    period = (
        datetime.now(ZoneInfo("America/New_York")).date().replace(day=1).isoformat()
    )
    job_id = seed_job(
        factory,
        payload={
            "request": {
                "meals": [{"recipe_id": "chicken_tacos", "servings": 2}],
                "diet": "vegan",
                "budget_period": period,
            },
            "monthly_limit_cents": 10_000,
            "spending": {
                "period": period,
                "posted_cents": 0,
                "pending_cents": 0,
                "refreshed_at": datetime.now(UTC).isoformat(),
            },
            "spending_source": "manual",
        },
    )
    queue = FakeQueue(body(job_id))
    assert (
        process_one(factory, queue, "agent", plan_job, now=lambda: T0)
        == "handler_failed"
    )
    failed = stored_job(factory, job_id)
    assert failed.status == "failed"
    assert failed.error_code == "diet_conflict"
    assert failed.result == {
        "error_detail": {
            "recipe_id": "chicken_tacos",
            "ingredient_id": "chicken_breast",
            "diet": "vegan",
        }
    }
    assert queue.acknowledgments == 1


def test_heartbeat_loss_prevents_completion_and_acknowledgment(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))
    queue.fail_extension_on = 2

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        heartbeat()
        return {"answer": "safe"}

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "lease_lost"
    held = stored_job(factory, job_id)
    assert held.status == "running"
    assert held.result is None
    assert queue.acknowledgments == 0


def test_swallowed_lease_loss_stays_sticky_for_retry(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))
    queue.fail_extension_on = 2

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        try:
            heartbeat()
        except LeaseLost:
            pass
        raise RetryableJobError("do not retry after lease loss")

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "lease_lost"
    assert queue.extensions == 2
    assert queue.acknowledgments == 0


def test_stale_token_cannot_finish_with_deterministic_clock(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))
    clock_values: Iterator[datetime] = iter((T0, T0, T0 + timedelta(seconds=61)))

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        return {"answer": "safe"}

    assert (
        process_one(factory, queue, "agent", handler, now=lambda: next(clock_values))
        == "lease_lost"
    )
    held = stored_job(factory, job_id)
    assert held.status == "running"
    assert held.result is None
    assert queue.acknowledgments == 0


def test_ack_failure_leaves_terminal_state_for_safe_replay(
    factory: sessionmaker[Session],
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))
    queue.fail_ack = True
    calls = 0

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"answer": "safe"}

    with pytest.raises(RuntimeError, match="ack failed"):
        process_one(factory, queue, "agent", handler, now=lambda: T0)
    assert stored_job(factory, job_id).status == "succeeded"
    queue.fail_ack = False
    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "terminal"
    assert calls == 1
    assert queue.acknowledgments == 2


def test_late_background_failure_prevents_completion_and_ack(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))
    calls = 0
    in_second = threading.Event()
    handler_done = threading.Event()

    def fake_renew() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        in_second.set()
        assert handler_done.wait(timeout=2)
        raise RuntimeError("late failure")

    def fast_heartbeat(_renew: Callable[[], None], **_kwargs: object) -> Heartbeat:
        return Heartbeat(fake_renew, interval_seconds=0.02)

    monkeypatch.setattr(job_consumer, "Heartbeat", fast_heartbeat)

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        assert in_second.wait(timeout=2)
        handler_done.set()
        return {"answer": "safe"}

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "lease_lost"
    held = stored_job(factory, job_id)
    assert held.status == "running"
    assert held.result is None
    assert queue.acknowledgments == 0


def test_retryable_error_with_background_loss_is_lease_lost(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = seed_job(factory)
    queue = FakeQueue(body(job_id))
    calls = 0
    lost = threading.Event()

    def fake_renew() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return
        lost.set()
        raise RuntimeError("visibility failed")

    def fast_heartbeat(_renew: Callable[[], None], **_kwargs: object) -> Heartbeat:
        return Heartbeat(fake_renew, interval_seconds=0.02)

    monkeypatch.setattr(job_consumer, "Heartbeat", fast_heartbeat)

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        assert lost.wait(timeout=2)
        raise RetryableJobError("do not retry after lease loss")

    assert process_one(factory, queue, "agent", handler, now=lambda: T0) == "lease_lost"
    held = stored_job(factory, job_id)
    assert held.status == "running"
    assert held.result is None
    assert queue.acknowledgments == 0
    assert queue.events == ["receive"]
