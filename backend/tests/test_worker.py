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
from test_chat_job import chat_payload

from app import worker
from app.job_models import Job
from app.provider_settings import GroceryProviderSettings, ProviderConfigurationError
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
SYNC_PAYLOAD: dict[str, object] = {
    "operation": "plaid_sync",
    "item_id": "item-1",
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
    handler: JobHandler | None = dummy_handler,
    kind: str = "agent",
) -> int:
    stub_cycle(monkeypatch, recover=recover, publish=publish)
    queue = dummy_queue()
    sender: JobSender = DummySender()

    def make_consumer(endpoint: str, queue_kind: str) -> JobQueue:
        assert endpoint == ENDPOINT
        assert queue_kind == kind
        return queue

    def make_sender(endpoint: str) -> JobSender:
        assert endpoint == ENDPOINT
        return sender

    return worker.main(
        ["--endpoint", ENDPOINT, "--kind", kind],
        factory=dummy_factory(),
        consumer_factory=consumer_factory or make_consumer,
        sender_factory=sender_factory or make_sender,
        processor=processor,
        handler=handler,
        stop=stop,
        now=frozen_now,
        wait=wait,
    )


def clear_fewia(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("FEWIA_"):
            monkeypatch.delenv(name, raising=False)


def forbid_provider_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(name: str) -> Callable[..., object]:
        def fail(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise AssertionError(name)

        return fail

    monkeypatch.setattr(worker, "build_bedrock", boom("bedrock"))
    monkeypatch.setattr(worker, "build_plaid", boom("plaid"))
    monkeypatch.setattr("app.provider_runtime.build_instacart", boom("instacart"))


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


def test_recover_then_process_order(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []
    stop = threading.Event()

    def recover(*args: object, **kwargs: object) -> int:
        order.append("recover")
        assert kwargs["now"] == NOW
        assert args[1] is worker.job_replay_safe
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

    stub_cycle(monkeypatch, recover=recover)
    worker.run_worker(
        dummy_factory(),
        dummy_queue(),
        DummySender(),
        dummy_handler,
        stop,
        processor=processor,
        now=frozen_now,
    )

    assert order == ["recover", "process"]


def test_publisher_batch_limit_is_twenty(monkeypatch: pytest.MonkeyPatch) -> None:
    limits: list[int] = []
    stop = threading.Event()
    published = threading.Event()

    def publish(*args: object, **kwargs: object) -> int:
        limit = kwargs.get("limit")
        assert isinstance(limit, int)
        limits.append(limit)
        published.set()
        return 0

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        assert published.wait(2)
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

    assert limits
    assert all(limit == 20 for limit in limits)


def test_run_publisher_idle_wait_uses_idle_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = threading.Event()
    waits: list[float | None] = []
    calls = {"n": 0}

    def publish(*args: object, **kwargs: object) -> int:
        assert kwargs.get("limit") == 20
        calls["n"] += 1
        if calls["n"] >= 3:
            stop.set()
        return 0

    def tracked_wait(timeout: float | None = None) -> bool:
        waits.append(timeout)
        stop.set()
        return True

    monkeypatch.setattr(worker, "publish_pending", publish)
    monkeypatch.setattr(stop, "wait", tracked_wait)
    worker.run_publisher(
        dummy_factory(),
        DummySender(),
        stop,
        idle_seconds=0.5,
    )

    assert waits == [0.5]


def test_run_publisher_publication_error_waits_backoff(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop = threading.Event()
    waits: list[float | None] = []
    calls = {"n": 0}

    def publish(*args: object, **kwargs: object) -> int:
        calls["n"] += 1
        if calls["n"] >= 3:
            stop.set()
        raise PublicationError(0, 1)

    def tracked_wait(timeout: float | None = None) -> bool:
        waits.append(timeout)
        stop.set()
        return True

    monkeypatch.setattr(worker, "publish_pending", publish)
    monkeypatch.setattr(stop, "wait", tracked_wait)
    worker.run_publisher(dummy_factory(), DummySender(), stop)
    output = capsys.readouterr()

    assert waits == [worker._BACKOFF_SECONDS]
    assert output.out == ""
    assert output.err == ""
    assert "published=" not in output.out
    assert "Traceback" not in output.out
    assert SECRET not in output.out
    assert SECRET not in output.err


def test_run_publisher_positive_count_loops_without_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = threading.Event()
    waits: list[float | None] = []
    calls = {"n": 0}

    def publish(*args: object, **kwargs: object) -> int:
        calls["n"] += 1
        if calls["n"] >= 3:
            stop.set()
        return 2

    def tracked_wait(timeout: float | None = None) -> bool:
        waits.append(timeout)
        raise AssertionError("wait")

    monkeypatch.setattr(worker, "publish_pending", publish)
    monkeypatch.setattr(stop, "wait", tracked_wait)
    worker.run_publisher(dummy_factory(), DummySender(), stop)

    assert calls["n"] == 3
    assert waits == []


def test_run_publisher_other_exceptions_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = threading.Event()

    def publish(*args: object, **kwargs: object) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr(worker, "publish_pending", publish)
    with pytest.raises(RuntimeError, match="db down"):
        worker.run_publisher(dummy_factory(), DummySender(), stop)


def test_run_worker_publishes_while_processor_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = threading.Event()
    published = threading.Event()
    entered = threading.Event()

    def publish(*args: object, **kwargs: object) -> int:
        published.set()
        return 1

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        entered.set()
        assert published.wait(2)
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

    assert entered.is_set()
    assert published.is_set()


def test_run_worker_publisher_failure_raises(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop = threading.Event()

    def publish(*args: object, **kwargs: object) -> int:
        raise RuntimeError(SECRET)

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        assert stop.wait(2)
        return "succeeded"

    stub_cycle(monkeypatch, publish=publish)
    with pytest.raises(RuntimeError, match="outbox publisher failed"):
        worker.run_worker(
            dummy_factory(),
            dummy_queue(),
            DummySender(),
            dummy_handler,
            stop,
            processor=processor,
            now=frozen_now,
        )
    output = capsys.readouterr()

    assert SECRET not in output.out
    assert SECRET not in output.err
    assert "Traceback" not in output.out
    assert "Traceback" not in output.err


def test_publisher_failure_emits_static_worker_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stop = threading.Event()

    def publish(*args: object, **kwargs: object) -> int:
        raise RuntimeError(SECRET)

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        return "empty"

    code = invoke_main(
        monkeypatch,
        processor=processor,
        publish=publish,
        stop=stop,
    )
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 1
    assert result["status"] == "worker_failed"
    assert SECRET not in output.out
    assert SECRET not in output.err
    assert output.err == ""
    assert "Traceback" not in output.out
    assert "outbox publisher failed" not in output.out


def test_strict_replay_classification() -> None:
    valid = make_job(kind="agent", payload=VALID_PAYLOAD)
    chat = make_job(kind="agent", payload=chat_payload())
    sync_ok = make_job(kind="sync", payload=SYNC_PAYLOAD)
    sync_job = make_job(kind="sync", payload=VALID_PAYLOAD)
    empty_job = make_job(kind="agent", payload={})
    extra = dict(VALID_PAYLOAD)
    extra["token"] = "secret-token"
    extra_job = make_job(kind="agent", payload=extra)
    unknown = make_job(kind="agent", payload={"operation": "purchase"})
    chat_on_sync = make_job(kind="sync", payload=chat_payload())
    sync_on_agent = make_job(kind="agent", payload=SYNC_PAYLOAD)
    cursor = dict(SYNC_PAYLOAD)
    cursor["cursor"] = "c1"
    sync_cursor = make_job(kind="sync", payload=cursor)

    assert worker.job_replay_safe(valid) is True
    assert worker.job_replay_safe(chat) is True
    assert worker.job_replay_safe(sync_ok) is True
    assert worker.job_replay_safe(sync_job) is False
    assert worker.job_replay_safe(empty_job) is False
    assert worker.job_replay_safe(extra_job) is False
    assert worker.job_replay_safe(unknown) is False
    assert worker.job_replay_safe(chat_on_sync) is False
    assert worker.job_replay_safe(sync_on_agent) is False
    assert worker.job_replay_safe(sync_cursor) is False


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


def test_default_agent_has_zero_external_effects(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clear_fewia(monkeypatch)
    forbid_provider_builds(monkeypatch)
    captured: list[object] = []

    def fake_agent(
        factory: sessionmaker[Session], provider: object, **kwargs: object
    ) -> JobHandler:
        del factory, kwargs
        captured.append(provider)
        return dummy_handler

    def fake_sync(factory: sessionmaker[Session], provider: object) -> JobHandler:
        del factory, provider
        raise AssertionError("sync handler")

    monkeypatch.setattr(worker, "make_agent_handler", fake_agent)
    monkeypatch.setattr(worker, "make_sync_handler", fake_sync)
    stop = threading.Event()

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue
        assert kind == "agent"
        assert handler is dummy_handler
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
    assert captured == [None]
    assert result["status"] == "stopped"
    assert result["counts"]["succeeded"] == 1
    assert SECRET not in output.out
    assert SECRET not in output.err
    assert "Traceback" not in output.out


def test_default_agent_routes_plan_and_chat_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_fewia(monkeypatch)
    forbid_provider_builds(monkeypatch)
    seen: list[str] = []

    def fake_agent(
        factory: sessionmaker[Session], provider: object, **kwargs: object
    ) -> JobHandler:
        del factory, provider, kwargs

        def handle(
            payload: dict[str, object], heartbeat: Callable[[], None]
        ) -> dict[str, object]:
            del heartbeat
            if payload.get("operation") == "chat":
                seen.append("chat")
            elif "operation" in payload:
                raise ValueError("operation is invalid")
            else:
                seen.append("plan")
            return {}

        return handle

    monkeypatch.setattr(worker, "make_agent_handler", fake_agent)
    stop = threading.Event()
    routed: list[str] = []

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue
        assert kind == "agent"
        handler(VALID_PAYLOAD, lambda: None)
        handler(chat_payload(), lambda: None)
        routed.extend(seen)
        stop.set()
        return "succeeded"

    code = invoke_main(
        monkeypatch,
        processor=processor,
        handler=None,
        stop=stop,
    )
    assert code == 0
    assert routed == ["plan", "chat"]


def test_sync_kind_uses_sync_queue_and_handler(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clear_fewia(monkeypatch)
    forbid_provider_builds(monkeypatch)
    captured: list[object] = []
    process_kinds: list[str] = []

    def fake_sync(factory: sessionmaker[Session], provider: object) -> JobHandler:
        del factory
        captured.append(provider)
        return dummy_handler

    def fake_agent(
        factory: sessionmaker[Session], provider: object, **kwargs: object
    ) -> JobHandler:
        del factory, provider, kwargs
        raise AssertionError("agent handler")

    def no_plaid(settings: GroceryProviderSettings) -> None:
        del settings
        return None

    monkeypatch.setattr(worker, "make_sync_handler", fake_sync)
    monkeypatch.setattr(worker, "make_agent_handler", fake_agent)
    monkeypatch.setattr(worker, "build_plaid", no_plaid)
    stop = threading.Event()

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, handler
        process_kinds.append(kind)
        stop.set()
        return "succeeded"

    def recover(*args: object, **kwargs: object) -> int:
        assert args[1] is worker.job_replay_safe
        return 0

    code = invoke_main(
        monkeypatch,
        processor=processor,
        recover=recover,
        handler=None,
        kind="sync",
        stop=stop,
    )
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 0
    assert captured == [None]
    assert process_kinds == ["sync"]
    assert result["status"] == "stopped"
    assert SECRET not in output.out
    assert SECRET not in output.err


def test_bedrock_constructor_failure_degrades_without_fake(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = GroceryProviderSettings(bedrock_model_id="anthropic.model")

    def loaded() -> GroceryProviderSettings:
        return settings

    def fail_build(loaded_settings: GroceryProviderSettings) -> None:
        del loaded_settings
        raise ProviderConfigurationError()

    def forbid_plaid(loaded_settings: GroceryProviderSettings) -> None:
        del loaded_settings
        raise AssertionError("plaid")

    monkeypatch.setattr(worker, "load_provider_settings", loaded)
    monkeypatch.setattr(worker, "build_bedrock", fail_build)
    monkeypatch.setattr(worker, "build_plaid", forbid_plaid)
    captured: list[object] = []

    def fake_agent(
        factory: sessionmaker[Session], provider: object, **kwargs: object
    ) -> JobHandler:
        del factory, kwargs
        captured.append(provider)
        return dummy_handler

    monkeypatch.setattr(worker, "make_agent_handler", fake_agent)
    stop = threading.Event()

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, handler
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
    notice = json.loads(output.err)

    assert code == 0
    assert captured == [None]
    assert notice == {"status": "bedrock_unavailable"}
    assert result["status"] == "stopped"
    assert SECRET not in output.out
    assert SECRET not in output.err


def test_invalid_settings_fail_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom() -> GroceryProviderSettings:
        raise ProviderConfigurationError()

    monkeypatch.setattr(worker, "load_provider_settings", boom)

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, kind, handler
        raise AssertionError("process must not run")

    code = invoke_main(monkeypatch, processor=processor, handler=None)
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 1
    assert result == {"counts": ZERO_COUNTS, "status": "worker_failed"}
    assert SECRET not in output.out
    assert SECRET not in output.err
    assert output.err == ""
    assert "Traceback" not in output.out


def test_default_agent_gets_no_extra_options_without_provider_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    clear_fewia(monkeypatch)
    forbid_provider_builds(monkeypatch)
    captured: list[object] = []

    def fake_agent(
        factory: sessionmaker[Session], provider: object, **kwargs: object
    ) -> JobHandler:
        del factory, provider
        captured.append(kwargs)
        return dummy_handler

    monkeypatch.setattr(worker, "make_agent_handler", fake_agent)
    stop = threading.Event()

    def processor(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, queue, handler
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
    assert captured == [{}]
    assert result["status"] == "stopped"
    assert result["counts"]["succeeded"] == 1
    assert SECRET not in output.out
    assert SECRET not in output.err
    assert "Traceback" not in output.out
