import json
import signal
import threading
from collections.abc import Callable
from typing import NoReturn

import pytest
from sqlalchemy.orm import Session, sessionmaker
from test_worker import ZERO_COUNTS, dummy_factory, dummy_handler

from app import worker
from app.providers.job_transport_settings import (
    JobTransportSettings,
    load_job_transport,
)
from app.providers.local_sqs_consumer import QueueMessage
from app.services.job_delivery import JobHandler, JobQueue
from app.services.outbox_publisher import JobSender

ENDPOINT = "http://127.0.0.1:4566"
MARKER = "PRIVATE_TEST_MARKER"
AWS_QUEUE_ORIGIN = "https://sqs.us-east-1.amazonaws.com/123456789012"
AWS_ENV = {
    "AWS_REGION": "us-east-1",
    "FEWIA_AWS_AGENT_QUEUE_URL": f"{AWS_QUEUE_ORIGIN}/agent",
    "FEWIA_AWS_SYNC_QUEUE_URL": f"{AWS_QUEUE_ORIGIN}/sync",
}


class FakeQueue:
    def receive(self) -> QueueMessage | None:
        raise AssertionError("loop spy MUST handle the queue")

    def acknowledge(self, message: QueueMessage) -> None:
        raise AssertionError("loop spy MUST handle the queue")

    def extend(self, message: QueueMessage, seconds: int) -> None:
        raise AssertionError("loop spy MUST handle the queue")


class FakeSender:
    def send(self, kind: str, job_id: str) -> None:
        raise AssertionError("loop spy MUST handle the sender")


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env: dict[str, str] = {}

    def load(
        *, mode: str | None = None, endpoint: str | None = None
    ) -> JobTransportSettings:
        return load_job_transport(mode=mode, endpoint=endpoint, environ=env)

    monkeypatch.setattr(worker, "load_job_transport", load)
    return env


@pytest.fixture
def effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        calls.append("effect")
        raise RuntimeError(MARKER)

    for name in (
        "_default_handler",
        "build_job_queue",
        "build_job_sender",
        "build_bedrock",
        "build_plaid",
        "make_agent_handler",
        "make_sync_handler",
        "run_worker",
        "recover_jobs",
        "publish_pending",
        "SessionLocal",
    ):
        monkeypatch.setattr(worker, name, forbidden)
    monkeypatch.setattr(worker.signal, "signal", forbidden)
    return calls


def assert_failed(code: int, capsys: pytest.CaptureFixture[str]) -> None:
    output = capsys.readouterr()
    assert code == 1
    assert json.loads(output.out) == {
        "status": "worker_failed",
        "counts": ZERO_COUNTS,
    }
    assert output.err == ""
    assert MARKER not in output.out


@pytest.mark.parametrize(
    ("argv", "mode", "kind", "endpoint"),
    [
        ([], "local", "agent", ENDPOINT),
        (["--transport", "local", "--kind", "sync"], "local", "sync", ENDPOINT),
        (
            ["--endpoint", "http://localhost:4566"],
            "local",
            "agent",
            "http://localhost:4566",
        ),
        (["--transport", "aws"], "aws", "agent", None),
        (["--transport", "aws", "--kind", "sync"], "aws", "sync", None),
        (["--kind", "sync"], "aws", "sync", None),
    ],
)
def test_default_builders_and_loop_arguments(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    mode: str,
    kind: str,
    endpoint: str | None,
) -> None:
    if mode == "aws":
        environment.update(AWS_ENV)
        if "--transport" not in argv:
            environment["FEWIA_TRANSPORT_MODE"] = "aws"
    queue = FakeQueue()
    sender = FakeSender()
    factory = dummy_factory()
    stop = threading.Event()
    events: list[str] = []
    loaded: list[JobTransportSettings] = []

    def make_handler(db: sessionmaker[Session], selected_kind: str) -> JobHandler:
        assert db is factory
        assert selected_kind == kind
        events.append("handler")
        return dummy_handler

    def make_queue(settings: JobTransportSettings, selected_kind: str) -> JobQueue:
        assert selected_kind == kind
        events.append("queue")
        loaded.append(settings)
        return queue

    def make_sender(settings: JobTransportSettings) -> JobSender:
        assert settings is loaded[0]
        events.append("sender")
        return sender

    def processor(
        db: sessionmaker[Session],
        selected_queue: JobQueue,
        selected_kind: str,
        handler: JobHandler,
    ) -> str:
        raise AssertionError("loop spy MUST handle processing")

    def wait(seconds: float) -> None:
        raise AssertionError("loop spy MUST handle waiting")

    def loop(
        db: sessionmaker[Session],
        selected_queue: JobQueue,
        selected_sender: JobSender,
        handler: JobHandler,
        selected_stop: threading.Event,
        **kwargs: object,
    ) -> dict[str, int]:
        assert db is factory
        assert selected_queue is queue
        assert selected_sender is sender
        assert handler is dummy_handler
        assert selected_stop is stop
        assert kwargs["kind"] == kind
        assert kwargs["processor"] is processor
        assert kwargs["wait"] is wait
        assert kwargs["now"] is worker._utc_now
        counts = kwargs["counts"]
        assert isinstance(counts, dict)
        assert counts == ZERO_COUNTS
        counts["succeeded"] += 1
        events.append("loop")
        return counts

    monkeypatch.setattr(worker, "_default_handler", make_handler)
    monkeypatch.setattr(worker, "build_job_queue", make_queue)
    monkeypatch.setattr(worker, "build_job_sender", make_sender)
    monkeypatch.setattr(worker, "run_worker", loop)
    code = worker.main(
        argv,
        factory=factory,
        stop=stop,
        processor=processor,
        wait=wait,
        now=worker._utc_now,
    )
    assert code == 0
    assert events == ["handler", "queue", "sender", "loop"]
    assert loaded[0].mode == mode
    assert loaded[0].endpoint == endpoint
    if mode == "aws":
        assert loaded[0].region == AWS_ENV["AWS_REGION"]
        assert loaded[0].agent_queue_url == AWS_ENV["FEWIA_AWS_AGENT_QUEUE_URL"]
        assert loaded[0].sync_queue_url == AWS_ENV["FEWIA_AWS_SYNC_QUEUE_URL"]
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "stopped"
    assert result["counts"] == {**ZERO_COUNTS, "succeeded": 1}


@pytest.mark.parametrize("injection", ["queue", "sender", "both"])
def test_local_legacy_factories_receive_validated_arguments(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    injection: str,
) -> None:
    environment["FEWIA_LOCAL_ENDPOINT_URL"] = "http://floci:4566"
    calls: list[str] = []
    stop = threading.Event()
    stop.set()

    def make_queue(endpoint: str, kind: str) -> JobQueue:
        assert endpoint == "http://floci:4566"
        assert kind == "sync"
        calls.append("legacy_queue")
        return FakeQueue()

    def make_sender(endpoint: str) -> JobSender:
        assert endpoint == "http://floci:4566"
        calls.append("legacy_sender")
        return FakeSender()

    def build_queue(settings: JobTransportSettings, kind: str) -> JobQueue:
        assert settings.mode == "local"
        calls.append("builder_queue")
        return make_queue(str(settings.endpoint), kind)

    def build_sender(settings: JobTransportSettings) -> JobSender:
        assert settings.mode == "local"
        calls.append("builder_sender")
        return make_sender(str(settings.endpoint))

    monkeypatch.setattr(worker, "build_job_queue", build_queue)
    monkeypatch.setattr(worker, "build_job_sender", build_sender)
    code = worker.main(
        ["--endpoint", "http://floci:4566", "--kind", "sync"],
        factory=dummy_factory(),
        handler=dummy_handler,
        stop=stop,
        consumer_factory=make_queue if injection in ("queue", "both") else None,
        sender_factory=make_sender if injection in ("sender", "both") else None,
    )
    assert code == 0
    assert calls.count("legacy_queue") == 1
    assert calls.count("legacy_sender") == 1
    assert ("builder_queue" in calls) == (injection == "sender")
    assert ("builder_sender" in calls) == (injection == "queue")
    assert json.loads(capsys.readouterr().out) == {
        "status": "stopped",
        "counts": ZERO_COUNTS,
    }


@pytest.mark.parametrize(
    ("argv", "env"),
    [
        (["--endpoint", MARKER], {}),
        ([], {"FEWIA_LOCAL_ENDPOINT_URL": MARKER}),
        ([], {"FEWIA_TRANSPORT_MODE": MARKER}),
        (["--transport", "aws"], {}),
        (["--transport", "local"], {"FEWIA_TRANSPORT_MODE": "aws", **AWS_ENV}),
        (["--transport", "aws"], {"FEWIA_TRANSPORT_MODE": "local", **AWS_ENV}),
        (["--transport", "aws", "--endpoint", ENDPOINT], AWS_ENV),
        (["--transport", "aws"], {**AWS_ENV, "FEWIA_LOCAL_ENDPOINT_URL": ENDPOINT}),
        ([], {"FEWIA_AWS_AGENT_QUEUE_URL": MARKER}),
        ([], {"FEWIA_AWS_SYNC_QUEUE_URL": MARKER}),
        (["--endpoint", ENDPOINT], {"FEWIA_LOCAL_ENDPOINT_URL": "http://floci:4566"}),
        (["--transport", "aws"], {**AWS_ENV, "AWS_REGION": MARKER}),
        (["--transport", "aws"], {**AWS_ENV, "FEWIA_AWS_SYNC_QUEUE_URL": MARKER}),
    ],
)
@pytest.mark.parametrize("legacy", [False, True])
def test_invalid_configuration_precedes_all_effects(
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
    legacy: bool,
) -> None:
    environment.update(env)

    def legacy_queue(endpoint: str, kind: str) -> JobQueue:
        effects.append("legacy_queue")
        raise RuntimeError(MARKER)

    def legacy_sender(endpoint: str) -> JobSender:
        effects.append("legacy_sender")
        raise RuntimeError(MARKER)

    code = worker.main(
        argv,
        consumer_factory=legacy_queue if legacy else None,
        sender_factory=legacy_sender if legacy else None,
    )
    assert_failed(code, capsys)
    assert effects == []


@pytest.mark.parametrize(
    "key",
    [
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CONFIG_FILE",
        "FEWIA_AWS_PROFILE",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_SQS",
    ],
)
def test_aws_credential_configuration_precedes_all_effects(
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    key: str,
) -> None:
    environment.update(AWS_ENV)
    environment[key] = MARKER
    assert_failed(worker.main(["--transport", "aws"]), capsys)
    assert effects == []


@pytest.mark.parametrize("injection", ["queue", "sender", "both"])
def test_aws_rejects_legacy_factories_before_all_effects(
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    injection: str,
) -> None:
    environment.update(AWS_ENV)
    environment["FEWIA_TRANSPORT_MODE"] = "aws"

    def legacy_queue(endpoint: str, kind: str) -> JobQueue:
        effects.append("legacy_queue")
        raise RuntimeError(MARKER)

    def legacy_sender(endpoint: str) -> JobSender:
        effects.append("legacy_sender")
        raise RuntimeError(MARKER)

    code = worker.main(
        [],
        consumer_factory=legacy_queue if injection in ("queue", "both") else None,
        sender_factory=legacy_sender if injection in ("sender", "both") else None,
    )
    assert_failed(code, capsys)
    assert effects == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--transport", MARKER],
        ["--kind", MARKER],
        ["--endpoint"],
        ["--transport"],
        ["--kind"],
        ["--unknown", MARKER],
        [MARKER],
    ],
)
def test_parser_errors_are_static_and_precede_loading(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    def forbid_load(**kwargs: object) -> NoReturn:
        effects.append("load")
        raise RuntimeError(MARKER)

    monkeypatch.setattr(worker, "load_job_transport", forbid_load)
    assert_failed(worker.main(argv), capsys)
    assert effects == []


def test_loader_failure_is_static_and_precedes_all_effects(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_load(**kwargs: object) -> NoReturn:
        raise RuntimeError(MARKER)

    monkeypatch.setattr(worker, "load_job_transport", fail_load)
    assert_failed(worker.main([]), capsys)
    assert effects == []


def test_help_returns_zero_without_effects(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbid_load(**kwargs: object) -> NoReturn:
        effects.append("load")
        raise RuntimeError(MARKER)

    monkeypatch.setattr(worker, "load_job_transport", forbid_load)
    assert worker.main(["--help"]) == 0
    output = capsys.readouterr()
    assert "--transport" in output.out
    assert output.err == ""
    assert effects == []


@pytest.mark.parametrize("mode", ["local", "aws"])
@pytest.mark.parametrize("failed_builder", ["queue", "sender"])
def test_constructor_failure_is_static_and_restores_signals(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    mode: str,
    failed_builder: str,
) -> None:
    if mode == "aws":
        environment.update(AWS_ENV)
    builds: list[str] = []
    signals: list[tuple[signal.Signals, object]] = []
    previous = {
        signum: worker.signal.getsignal(signum)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }

    def set_signal(signum: signal.Signals, handler: object) -> None:
        signals.append((signum, handler))

    def make_queue(settings: JobTransportSettings, kind: str) -> JobQueue:
        assert settings.mode == mode
        assert kind == "sync"
        builds.append("queue")
        if failed_builder == "queue":
            raise RuntimeError(MARKER)
        return FakeQueue()

    def make_sender(settings: JobTransportSettings) -> JobSender:
        assert settings.mode == mode
        builds.append("sender")
        raise RuntimeError(MARKER)

    monkeypatch.setattr(worker.signal, "signal", set_signal)
    monkeypatch.setattr(worker, "build_job_queue", make_queue)
    monkeypatch.setattr(worker, "build_job_sender", make_sender)
    code = worker.main(
        ["--transport", mode, "--kind", "sync"],
        factory=dummy_factory(),
        handler=dummy_handler,
    )
    assert_failed(code, capsys)
    assert effects == []
    assert builds == (["queue"] if failed_builder == "queue" else ["queue", "sender"])
    assert signals[2:] == list(previous.items())


def test_aws_signal_stop_restores_previous_handlers(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment.update(AWS_ENV)
    previous = {
        signum: worker.signal.getsignal(signum)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    restored: list[tuple[signal.Signals, object]] = []
    installed: list[Callable[[int, object], None]] = []

    def set_signal(signum: signal.Signals, handler: object) -> None:
        if len(installed) < 2:
            assert callable(handler)
            installed.append(handler)
        else:
            restored.append((signum, handler))

    def make_queue(settings: JobTransportSettings, kind: str) -> JobQueue:
        return FakeQueue()

    def make_sender(settings: JobTransportSettings) -> JobSender:
        return FakeSender()

    def recover(*args: object, **kwargs: object) -> int:
        installed[0](signal.SIGTERM, None)
        return 0

    def forbid_publish(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("publish after stop")

    monkeypatch.setattr(worker.signal, "signal", set_signal)
    monkeypatch.setattr(worker, "build_job_queue", make_queue)
    monkeypatch.setattr(worker, "build_job_sender", make_sender)
    monkeypatch.setattr(worker, "recover_jobs", recover)
    monkeypatch.setattr(worker, "publish_pending", forbid_publish)
    code = worker.main(
        ["--transport", "aws"],
        factory=dummy_factory(),
        handler=dummy_handler,
    )
    assert code == 0
    assert restored == list(previous.items())
    assert json.loads(capsys.readouterr().out) == {
        "status": "stopped",
        "counts": ZERO_COUNTS,
    }
