import json
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import worker
from app.job_models import Job
from app.services.job_delivery import JobHandler, JobQueue
from app.services.outbox_publisher import JobSender, PublicationError

ENDPOINT = "http://127.0.0.1:4566"
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
SECRET = "Authorization: Bearer secret-token"
ZERO_COUNTS = {
    "busy": 0,
    "empty": 0,
    "exhausted": 0,
    "handler_failed": 0,
    "invalid": 0,
    "lease_lost": 0,
    "retry": 0,
    "succeeded": 0,
    "terminal": 0,
}
VALID_PAYLOAD: dict[str, object] = {
    "request": {
        "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
        "budget_period": "2026-09-01",
    },
    "monthly_limit_cents": 10_000,
    "spending": {
        "period": "2026-09-01",
        "posted_cents": 2500,
        "pending_cents": 400,
        "refreshed_at": "2026-09-02T11:00:00+00:00",
    },
    "spending_source": "fixture",
}


class DummySender:
    def send(self, kind: str, job_id: str) -> None:
        del kind, job_id


def dummy_factory() -> sessionmaker[Session]:
    return cast(sessionmaker[Session], object())


def dummy_queue() -> JobQueue:
    return cast(JobQueue, object())


def dummy_handler(
    payload: dict[str, object], heartbeat: Callable[[], None]
) -> dict[str, object]:
    del payload, heartbeat
    return {}


def frozen_now() -> datetime:
    return NOW


def make_job(*, kind: str, payload: dict[str, object]) -> Job:
    return Job(
        id="00000000-0000-0000-0000-000000000001",
        user_id=1,
        kind=kind,
        request_key="key",
        status="queued",
        payload=payload,
        attempts=0,
    )


def noop_recover(*args: object, **kwargs: object) -> int:
    return 0


def noop_publish(*args: object, **kwargs: object) -> int:
    return 0


def stub_cycle(
    monkeypatch: pytest.MonkeyPatch,
    recover: Callable[..., int] = noop_recover,
    publish: Callable[..., int] = noop_publish,
) -> None:
    monkeypatch.setattr(worker, "recover_jobs", recover)
    monkeypatch.setattr(worker, "publish_pending", publish)


def invoke_main(
    monkeypatch: pytest.MonkeyPatch,
    *,
    processor: worker.Processor,
    recover: Callable[..., int] = noop_recover,
    publish: Callable[..., int] = noop_publish,
    consumer_factory: worker.QueueFactory | None = None,
    sender_factory: worker.SenderFactory | None = None,
    stop: threading.Event | None = None,
    wait: worker.WaitFn | None = None,
) -> int:
    stub_cycle(monkeypatch, recover=recover, publish=publish)
    queue = dummy_queue()
    sender: JobSender = DummySender()

    def make_consumer(endpoint: str, kind: str) -> JobQueue:
        assert endpoint == ENDPOINT
        assert kind == "agent"
        return queue

    def make_sender(endpoint: str) -> JobSender:
        assert endpoint == ENDPOINT
        return sender

    return worker.main(
        ["--endpoint", ENDPOINT],
        factory=dummy_factory(),
        consumer_factory=consumer_factory or make_consumer,
        sender_factory=sender_factory or make_sender,
        processor=processor,
        handler=dummy_handler,
        stop=stop,
        now=frozen_now,
        wait=wait,
    )


def test_empty_then_work_then_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_cycle(monkeypatch)
    stop = threading.Event()
    waits: list[float] = []
    outcomes = ["empty", "succeeded"]

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, handler
        assert kind == "agent"
        outcome = outcomes.pop(0)
        if outcome == "succeeded":
            stop.set()
        return outcome

    def wait(seconds: float) -> None:
        waits.append(seconds)

    counts = worker.run_worker(
        dummy_factory(),
        dummy_queue(),
        DummySender(),
        dummy_handler,
        stop,
        processor=processor,
        now=frozen_now,
        wait=wait,
    )

    assert outcomes == []
    assert waits == [1]
    assert counts["empty"] == 1
    assert counts["succeeded"] == 1


def test_initial_stop_has_zero_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> int:
        raise AssertionError("effect")

    stub_cycle(monkeypatch, recover=boom, publish=boom)
    stop = threading.Event()
    stop.set()

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        raise AssertionError("effect")

    counts = worker.run_worker(
        dummy_factory(),
        dummy_queue(),
        DummySender(),
        dummy_handler,
        stop,
        processor=processor,
        now=frozen_now,
        wait=boom,
    )

    assert counts == ZERO_COUNTS


def test_recover_then_publish_then_process_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[object] = []
    stop = threading.Event()

    def recover(*args: object, **kwargs: object) -> int:
        order.append("recover")
        assert kwargs["now"] == NOW
        assert args[1] is worker.agent_plan_replay_safe
        return 0

    def publish(*args: object, **kwargs: object) -> int:
        order.append(("publish", kwargs.get("limit", 20)))
        return 0

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        order.append("process")
        stop.set()
        return "succeeded"

    stub_cycle(monkeypatch, recover=recover, publish=publish)
    worker.run_worker(
        dummy_factory(),
        dummy_queue(),
        DummySender(),
        dummy_handler,
        stop,
        processor=processor,
        now=frozen_now,
    )

    assert order == ["recover", ("publish", 1), "process"]


def test_max_publisher_batch_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    limits: list[int] = []
    stop = threading.Event()

    def publish(*args: object, **kwargs: object) -> int:
        limit = kwargs.get("limit")
        assert isinstance(limit, int)
        limits.append(limit)
        return 0

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        stop.set()
        return "succeeded"

    stub_cycle(monkeypatch, publish=publish)
    worker.run_worker(
        dummy_factory(),
        dummy_queue(),
        DummySender(),
        dummy_handler,
        stop,
        processor=processor,
        now=frozen_now,
    )

    assert limits == [1]


def test_publication_error_retries_without_raw_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop = threading.Event()
    attempts = {"n": 0}
    waits: list[float] = []
    process_calls = {"n": 0}

    def publish(*args: object, **kwargs: object) -> int:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise PublicationError(0, 1)
        return 1

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        process_calls["n"] += 1
        stop.set()
        return "succeeded"

    def wait(seconds: float) -> None:
        waits.append(seconds)

    code = invoke_main(
        monkeypatch,
        processor=processor,
        publish=publish,
        stop=stop,
        wait=wait,
    )
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 0
    assert result["status"] == "stopped"
    assert result["counts"]["succeeded"] == 1
    assert attempts["n"] == 2
    assert process_calls["n"] == 1
    assert waits == [1]
    assert SECRET not in output.out
    assert SECRET not in output.err
    assert output.err == ""
    assert "Traceback" not in output.out


def test_publication_error_does_not_print_payloads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop = threading.Event()

    def publish(*args: object, **kwargs: object) -> int:
        raise PublicationError(0, 1)

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        raise AssertionError("process must not run")

    def wait(seconds: float) -> None:
        del seconds
        stop.set()

    code = invoke_main(
        monkeypatch,
        processor=processor,
        publish=publish,
        stop=stop,
        wait=wait,
    )
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 0
    assert result == {"counts": ZERO_COUNTS, "status": "stopped"}
    assert output.err == ""
    assert "published=" not in output.out


def test_unsafe_job_classification() -> None:
    valid = make_job(kind="agent", payload=VALID_PAYLOAD)
    sync_job = make_job(kind="sync", payload=VALID_PAYLOAD)
    empty_job = make_job(kind="agent", payload={})
    extra = dict(VALID_PAYLOAD)
    extra["token"] = "secret-token"
    extra_job = make_job(kind="agent", payload=extra)

    assert worker.agent_plan_replay_safe(valid) is True
    assert worker.agent_plan_replay_safe(sync_job) is False
    assert worker.agent_plan_replay_safe(empty_job) is False
    assert worker.agent_plan_replay_safe(extra_job) is False


def test_unknown_outcome_is_fatal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        return "mystery"

    code = invoke_main(monkeypatch, processor=processor)
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 1
    assert result == {"counts": ZERO_COUNTS, "status": "worker_failed"}
    assert "mystery" not in output.out
    assert output.err == ""


def test_operational_errors_emit_static_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_consumer(endpoint: str, kind: str) -> JobQueue:
        del endpoint, kind
        raise RuntimeError(SECRET)

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        return "empty"

    code = invoke_main(monkeypatch, processor=processor, consumer_factory=fail_consumer)
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 1
    assert result == {"counts": ZERO_COUNTS, "status": "worker_failed"}
    assert SECRET not in output.out
    assert SECRET not in output.err
    assert output.err == ""


def test_signal_restore_on_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[signal.Signals, object]] = []
    previous = {
        signum: worker.signal.getsignal(signum)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }

    def fake_signal(signum: signal.Signals, handler: object) -> None:
        calls.append((signum, handler))

    def fail_consumer(endpoint: str, kind: str) -> JobQueue:
        del endpoint, kind
        raise RuntimeError("queue unavailable")

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        return "empty"

    monkeypatch.setattr(worker.signal, "signal", fake_signal)
    code = invoke_main(monkeypatch, processor=processor, consumer_factory=fail_consumer)
    capsys.readouterr()

    assert code == 1
    assert calls[2:] == [
        (signal.SIGINT, previous[signal.SIGINT]),
        (signal.SIGTERM, previous[signal.SIGTERM]),
    ]


def test_signal_restore_on_normal_stop(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[signal.Signals, object]] = []

    def fake_signal(signum: signal.Signals, handler: object) -> None:
        calls.append((signum, handler))

    monkeypatch.setattr(worker.signal, "signal", fake_signal)
    processor_calls = 0

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        nonlocal processor_calls
        processor_calls += 1
        installed = calls[0][1]
        assert callable(installed)
        installed(signal.SIGINT, None)
        return "succeeded"

    code = invoke_main(monkeypatch, processor=processor)
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert processor_calls == 1
    assert result["status"] == "stopped"
    assert result["counts"]["succeeded"] == 1
    assert [signum for signum, _ in calls] == [
        signal.SIGINT,
        signal.SIGTERM,
        signal.SIGINT,
        signal.SIGTERM,
    ]


def test_empty_queue_does_not_busy_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    recoveries = {"n": 0}
    stop = threading.Event()

    def recover(*args: object, **kwargs: object) -> int:
        recoveries["n"] += 1
        if recoveries["n"] > 3:
            raise AssertionError("busy loop")
        return 0

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        return "empty"

    def wait(seconds: float) -> None:
        assert seconds == 1
        stop.set()

    stub_cycle(monkeypatch, recover=recover)
    worker.run_worker(
        dummy_factory(),
        dummy_queue(),
        DummySender(),
        dummy_handler,
        stop,
        processor=processor,
        now=frozen_now,
        wait=wait,
    )

    assert recoveries["n"] == 1


def test_main_keeps_counts_after_later_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = {"n": 0}

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        calls["n"] += 1
        if calls["n"] == 1:
            return "succeeded"
        raise RuntimeError(SECRET)

    code = invoke_main(monkeypatch, processor=processor)
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 1
    assert result["status"] == "worker_failed"
    assert result["counts"]["succeeded"] == 1
    assert SECRET not in output.out
    assert SECRET not in output.err
    assert output.err == ""
    assert "Traceback" not in output.out


def test_standalone_worker_import_registers_user() -> None:
    script = (
        "import app.worker\n"
        "from app.db import Base\n"
        "from app.job_models import Job\n"
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import Session\n"
        "assert 'users' in Base.metadata.tables\n"
        "from app.models import User\n"
        "assert Base.metadata.tables['users'] is User.__table__\n"
        "engine = create_engine('sqlite://')\n"
        "Base.metadata.create_all(engine, tables=[User.__table__, Job.__table__])\n"
        "try:\n"
        "    with Session(engine) as session:\n"
        "        session.add(User(id=1, display_name='Worker'))\n"
        "        session.flush()\n"
        "        session.add(Job(\n"
        "            id='00000000-0000-0000-0000-000000000001',\n"
        "            user_id=1,\n"
        "            kind='agent',\n"
        "            request_key='key',\n"
        "            status='queued',\n"
        "            payload={},\n"
        "            attempts=0,\n"
        "        ))\n"
        "        session.flush()\n"
        "finally:\n"
        "    engine.dispose()\n"
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite://"
    pythonpath = [str(Path(__file__).resolve().parents[1])]
    existing = env.get("PYTHONPATH")
    if existing:
        pythonpath.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
