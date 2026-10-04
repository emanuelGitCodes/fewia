import json
import signal
from typing import NoReturn, cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import consume_jobs
from app.providers.job_transport_settings import (
    JobTransportSettings,
    load_job_transport,
)
from app.services.job_delivery import JobHandler, JobQueue

ENDPOINT = "http://127.0.0.1:4566"
MARKER = "PRIVATE_TEST_MARKER"
AWS_ORIGIN = "https://sqs.us-east-1.amazonaws.com/123456789012"
AWS_ENV = {
    "AWS_REGION": "us-east-1",
    "FEWIA_AWS_AGENT_QUEUE_URL": f"{AWS_ORIGIN}/agent",
    "FEWIA_AWS_SYNC_QUEUE_URL": f"{AWS_ORIGIN}/sync",
}
ZERO_COUNTS = {
    "empty": 0,
    "invalid": 0,
    "busy": 0,
    "retry": 0,
    "lease_lost": 0,
    "handler_failed": 0,
    "succeeded": 0,
    "terminal": 0,
    "exhausted": 0,
}


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env: dict[str, str] = {}

    def load(
        *, mode: str | None = None, endpoint: str | None = None
    ) -> JobTransportSettings:
        return load_job_transport(mode=mode, endpoint=endpoint, environ=env)

    monkeypatch.setattr(consume_jobs, "load_job_transport", load)
    return env


@pytest.fixture
def effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        calls.append("effect")
        raise RuntimeError(MARKER)

    for name in ("build_job_queue", "process_one", "plan_job", "SessionLocal"):
        monkeypatch.setattr(consume_jobs, name, forbidden)
    monkeypatch.setattr(consume_jobs.signal, "signal", forbidden)
    return calls


def assert_failed(code: int, capsys: pytest.CaptureFixture[str]) -> None:
    output = capsys.readouterr()
    assert code == 1
    assert json.loads(output.out) == {"status": "worker_failed", "counts": ZERO_COUNTS}
    assert output.err == ""
    assert MARKER not in output.out


@pytest.mark.parametrize(
    ("argv", "env", "mode", "endpoint"),
    [
        ([], {}, "local", ENDPOINT),
        (["--transport", "local"], {}, "local", ENDPOINT),
        (
            ["--endpoint", "http://localhost:4566"],
            {},
            "local",
            "http://localhost:4566",
        ),
        (
            [],
            {"FEWIA_LOCAL_ENDPOINT_URL": "http://floci:4566"},
            "local",
            "http://floci:4566",
        ),
        (["--transport", "aws"], AWS_ENV, "aws", None),
        ([], {"FEWIA_TRANSPORT_MODE": "aws", **AWS_ENV}, "aws", None),
    ],
)
def test_selected_builder_and_processor_arguments(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
    mode: str,
    endpoint: str | None,
) -> None:
    environment.update(env)
    queue = cast(JobQueue, object())
    factory = cast(sessionmaker[Session], object())
    handler = cast(JobHandler, object())
    calls: list[str] = []

    def build(settings: JobTransportSettings, kind: str) -> JobQueue:
        assert settings.mode == mode
        assert settings.endpoint == endpoint
        assert kind == "agent"
        if mode == "aws":
            assert settings.region == AWS_ENV["AWS_REGION"]
            assert settings.agent_queue_url == AWS_ENV["FEWIA_AWS_AGENT_QUEUE_URL"]
            assert settings.sync_queue_url == AWS_ENV["FEWIA_AWS_SYNC_QUEUE_URL"]
        calls.append("build")
        return queue

    def process(
        db: sessionmaker[Session],
        selected: JobQueue,
        kind: str,
        selected_handler: JobHandler,
    ) -> str:
        assert db is factory
        assert selected is queue
        assert kind == "agent"
        assert selected_handler is handler
        calls.append("process")
        return "empty"

    monkeypatch.setattr(consume_jobs, "build_job_queue", build)
    monkeypatch.setattr(consume_jobs, "process_one", process)
    assert consume_jobs.main(argv, factory=factory, handler=handler) == 0
    assert calls == ["build", "process"]
    assert json.loads(capsys.readouterr().out) == {
        "status": "empty",
        "counts": {**ZERO_COUNTS, "empty": 1},
    }


@pytest.mark.parametrize("limit", [None, 1, 2, 10000])
def test_message_bounds_and_default(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    limit: int | None,
) -> None:
    calls = 0

    def build(settings: JobTransportSettings, kind: str) -> JobQueue:
        return cast(JobQueue, object())

    def process(
        db: sessionmaker[Session], queue: JobQueue, kind: str, handler: JobHandler
    ) -> str:
        nonlocal calls
        calls += 1
        return "succeeded"

    monkeypatch.setattr(consume_jobs, "build_job_queue", build)
    monkeypatch.setattr(consume_jobs, "process_one", process)
    argv = [] if limit is None else ["--max-messages", str(limit)]
    assert consume_jobs.main(argv) == 0
    assert calls == (20 if limit is None else limit)
    assert json.loads(capsys.readouterr().out) == {
        "status": "max_messages",
        "counts": {**ZERO_COUNTS, "succeeded": calls},
    }


def test_local_legacy_factory_receives_validated_endpoint(
    environment: dict[str, str],
    effects: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment["FEWIA_LOCAL_ENDPOINT_URL"] = "http://floci:4566"
    calls: list[tuple[str, str]] = []

    def legacy(endpoint: str, kind: str) -> JobQueue:
        calls.append((endpoint, kind))
        return cast(JobQueue, object())

    def process(
        db: sessionmaker[Session], queue: JobQueue, kind: str, handler: JobHandler
    ) -> str:
        return "empty"

    def set_signal(signum: int, handler: object) -> None:
        pass

    monkeypatch.setattr(consume_jobs.signal, "signal", set_signal)
    assert consume_jobs.main([], consumer_factory=legacy, processor=process) == 0
    assert calls == [("http://floci:4566", "agent")]
    assert effects == []
    assert json.loads(capsys.readouterr().out)["status"] == "empty"


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
def test_invalid_configuration_has_no_effects(
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
    legacy: bool,
) -> None:
    environment.update(env)

    def make_queue(endpoint: str, kind: str) -> NoReturn:
        effects.append("legacy")
        raise RuntimeError(MARKER)

    assert_failed(
        consume_jobs.main(argv, consumer_factory=make_queue if legacy else None), capsys
    )
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
def test_aws_credential_configuration_has_no_effects(
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    key: str,
) -> None:
    environment.update(AWS_ENV)
    environment[key] = MARKER
    assert_failed(consume_jobs.main(["--transport", "aws"]), capsys)
    assert effects == []


def test_aws_rejects_legacy_injection_before_effects(
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment.update(AWS_ENV)

    def legacy(endpoint: str, kind: str) -> NoReturn:
        effects.append("legacy")
        raise RuntimeError(MARKER)

    assert_failed(
        consume_jobs.main(["--transport", "aws"], consumer_factory=legacy), capsys
    )
    assert effects == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--max-messages", "0"],
        ["--max-messages", "10001"],
        ["--max-messages", "-1"],
        ["--max-messages", MARKER],
        ["--max-messages"],
        ["--transport", MARKER],
        ["--transport"],
        ["--endpoint"],
        ["--unknown", MARKER],
        [MARKER],
    ],
)
def test_parser_errors_precede_loading(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    def forbidden(**kwargs: object) -> NoReturn:
        effects.append("load")
        raise RuntimeError(MARKER)

    monkeypatch.setattr(consume_jobs, "load_job_transport", forbidden)
    assert_failed(consume_jobs.main(argv), capsys)
    assert effects == []


def test_help_has_no_effects(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(**kwargs: object) -> NoReturn:
        effects.append("load")
        raise RuntimeError(MARKER)

    monkeypatch.setattr(consume_jobs, "load_job_transport", forbidden)
    assert consume_jobs.main(["--help"]) == 0
    output = capsys.readouterr()
    assert "--transport" in output.out
    assert output.err == ""
    assert effects == []


@pytest.mark.parametrize("interrupted", [False, True])
def test_loader_failure_precedes_effects(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    interrupted: bool,
) -> None:
    def fail_load(**kwargs: object) -> NoReturn:
        if interrupted:
            raise KeyboardInterrupt
        raise RuntimeError(MARKER)

    monkeypatch.setattr(consume_jobs, "load_job_transport", fail_load)
    code = consume_jobs.main([])
    assert effects == []
    if interrupted:
        output = capsys.readouterr()
        assert code == 0
        assert json.loads(output.out) == {"status": "stopped", "counts": ZERO_COUNTS}
        assert output.err == ""
    else:
        assert_failed(code, capsys)


@pytest.mark.parametrize("mode", ["local", "aws"])
@pytest.mark.parametrize("failure", ["constructor", "processor", "interrupt", "signal"])
def test_failures_and_stops_restore_signals_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    mode: str,
    failure: str,
) -> None:
    if mode == "aws":
        environment.update(AWS_ENV)
    calls: list[str] = []
    signals: list[tuple[int, object]] = []
    previous = {
        signum: consume_jobs.signal.getsignal(signum)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }

    def set_signal(signum: int, handler: object) -> None:
        signals.append((signum, handler))

    def build(settings: JobTransportSettings, kind: str) -> JobQueue:
        assert settings.mode == mode
        calls.append("build")
        if failure == "constructor":
            raise RuntimeError(MARKER)
        return cast(JobQueue, object())

    def process(
        db: sessionmaker[Session], queue: JobQueue, kind: str, handler: JobHandler
    ) -> str:
        calls.append("process")
        if failure == "interrupt":
            raise KeyboardInterrupt
        if failure == "signal":
            installed = signals[0][1]
            assert callable(installed)
            installed(signal.SIGTERM, None)
            return "succeeded"
        raise RuntimeError(MARKER)

    monkeypatch.setattr(consume_jobs.signal, "signal", set_signal)
    monkeypatch.setattr(consume_jobs, "build_job_queue", build)
    monkeypatch.setattr(consume_jobs, "process_one", process)
    code = consume_jobs.main(["--transport", mode])
    assert signals[2:] == list(previous.items())
    assert calls == (["build"] if failure == "constructor" else ["build", "process"])
    if failure in ("constructor", "processor"):
        assert_failed(code, capsys)
    else:
        output = capsys.readouterr()
        assert code == 0
        assert output.err == ""
        assert json.loads(output.out) == {
            "status": "stopped",
            "counts": {**ZERO_COUNTS, "succeeded": int(failure == "signal")},
        }
