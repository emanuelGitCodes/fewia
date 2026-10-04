import json
import signal
from collections.abc import Sequence
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import consume_jobs
from app.services.job_delivery import JobHandler, JobQueue

ENDPOINT = "http://127.0.0.1:4566"


def invoke(
    outcomes: Sequence[str],
    *,
    max_messages: int = 20,
    consumer_factory: consume_jobs.QueueFactory | None = None,
    processor: consume_jobs.Processor | None = None,
) -> tuple[int, dict[str, object], list[tuple[str, str]]]:
    queue = cast(JobQueue, object())
    seen: list[tuple[str, str]] = []
    index = 0

    def make_consumer(endpoint: str, kind: str) -> JobQueue:
        seen.append((endpoint, kind))
        return queue

    def process(
        factory: sessionmaker[Session],
        selected_queue: JobQueue,
        kind: str,
        handler: JobHandler,
    ) -> str:
        del factory, selected_queue, handler
        nonlocal index
        seen.append(("process", kind))
        outcome = outcomes[index]
        index += 1
        return outcome

    code = consume_jobs.main(
        ["--endpoint", ENDPOINT, "--max-messages", str(max_messages)],
        factory=cast(sessionmaker[Session], object()),
        consumer_factory=consumer_factory or make_consumer,
        processor=processor or process,
    )
    return code, {}, seen


def test_empty_stops_and_consumes_only_the_agent_queue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, seen = invoke(["empty"], max_messages=20)
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["status"] == "empty"
    assert result["counts"]["empty"] == 1
    assert seen == [(ENDPOINT, "agent"), ("process", "agent")]


def test_max_messages_bounds_processing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, seen = invoke(["succeeded", "succeeded", "succeeded"], max_messages=3)
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["status"] == "max_messages"
    assert result["counts"]["succeeded"] == 3
    assert seen.count(("process", "agent")) == 3


@pytest.mark.parametrize("value", ["0", "10001", "-1", "not-an-int"])
def test_max_messages_rejects_invalid_bounds(
    value: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("effect")
        raise AssertionError("Invalid bounds triggered an effect")

    monkeypatch.setattr(consume_jobs, "build_job_queue", forbidden)
    monkeypatch.setattr(consume_jobs, "process_one", forbidden)
    code = consume_jobs.main(["--endpoint", ENDPOINT, "--max-messages", value])
    output = capsys.readouterr()

    assert code == 1
    assert json.loads(output.out) == {
        "counts": {
            "busy": 0,
            "empty": 0,
            "exhausted": 0,
            "handler_failed": 0,
            "invalid": 0,
            "lease_lost": 0,
            "retry": 0,
            "succeeded": 0,
            "terminal": 0,
        },
        "status": "worker_failed",
    }
    assert output.err == ""
    assert calls == []


def test_operational_errors_emit_only_static_sanitized_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_consumer(endpoint: str, kind: str) -> JobQueue:
        del endpoint, kind
        raise RuntimeError("Authorization: Bearer secret-token")

    code, _, _ = invoke(["empty"], consumer_factory=fail_consumer)
    output = capsys.readouterr()
    result = json.loads(output.out)

    assert code == 1
    assert result == {
        "counts": {
            "busy": 0,
            "empty": 0,
            "exhausted": 0,
            "handler_failed": 0,
            "invalid": 0,
            "lease_lost": 0,
            "retry": 0,
            "succeeded": 0,
            "terminal": 0,
        },
        "status": "worker_failed",
    }
    assert "secret-token" not in output.out
    assert output.err == ""


def test_operational_errors_restore_signal_handlers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[signal.Signals, object]] = []
    previous = {
        signum: consume_jobs.signal.getsignal(signum)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }

    def fake_signal(signum: signal.Signals, handler: object) -> None:
        calls.append((signum, handler))

    def fail_consumer(endpoint: str, kind: str) -> JobQueue:
        del endpoint, kind
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(consume_jobs.signal, "signal", fake_signal)
    code, _, _ = invoke(["empty"], consumer_factory=fail_consumer)
    capsys.readouterr()

    assert code == 1
    assert calls[2:] == [
        (signal.SIGINT, previous[signal.SIGINT]),
        (signal.SIGTERM, previous[signal.SIGTERM]),
    ]


def test_signal_stops_after_current_job_and_restores_handlers(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[signal.Signals, object]] = []

    def fake_signal(signum: signal.Signals, handler: object) -> None:
        calls.append((signum, handler))

    monkeypatch.setattr(consume_jobs.signal, "signal", fake_signal)
    processor_calls = 0

    def process(
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

    code, _, _ = invoke(["succeeded", "succeeded"], processor=process)
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
