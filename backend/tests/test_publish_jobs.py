import json
from typing import NoReturn, cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app import publish_jobs
from app.providers.job_transport_settings import (
    JobTransportSettings,
    load_job_transport,
)
from app.services.outbox_publisher import JobSender, PublicationError

ENDPOINT = "http://127.0.0.1:4566"
MARKER = "PRIVATE_TEST_MARKER"
AWS_ORIGIN = "https://sqs.us-east-1.amazonaws.com/123456789012"
AWS_ENV = {
    "AWS_REGION": "us-east-1",
    "FEWIA_AWS_AGENT_QUEUE_URL": f"{AWS_ORIGIN}/agent",
    "FEWIA_AWS_SYNC_QUEUE_URL": f"{AWS_ORIGIN}/sync",
}


@pytest.fixture
def environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    env: dict[str, str] = {}

    def load(
        *, mode: str | None = None, endpoint: str | None = None
    ) -> JobTransportSettings:
        return load_job_transport(mode=mode, endpoint=endpoint, environ=env)

    monkeypatch.setattr(publish_jobs, "load_job_transport", load)
    return env


@pytest.fixture
def effects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> NoReturn:
        calls.append("effect")
        raise RuntimeError(MARKER)

    for name in ("build_job_sender", "publish_pending", "SessionLocal"):
        monkeypatch.setattr(publish_jobs, name, forbidden)
    return calls


def assert_failed(code: int, capsys: pytest.CaptureFixture[str]) -> None:
    output = capsys.readouterr()
    assert code == 1
    assert json.loads(output.out) == {"status": "publish_failed"}
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
@pytest.mark.parametrize("limit", [None, 1, 100])
def test_selected_builder_and_bounded_publication(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
    mode: str,
    endpoint: str | None,
    limit: int | None,
) -> None:
    environment.update(env)
    factory = cast(sessionmaker[Session], object())
    sender = cast(JobSender, object())
    calls: list[str] = []

    def build(settings: JobTransportSettings) -> JobSender:
        assert settings.mode == mode
        assert settings.endpoint == endpoint
        if mode == "aws":
            assert settings.region == AWS_ENV["AWS_REGION"]
            assert settings.agent_queue_url == AWS_ENV["FEWIA_AWS_AGENT_QUEUE_URL"]
            assert settings.sync_queue_url == AWS_ENV["FEWIA_AWS_SYNC_QUEUE_URL"]
        calls.append("build")
        return sender

    def publish(
        db: sessionmaker[Session], selected: JobSender, selected_limit: int
    ) -> int:
        assert db is factory
        assert selected is sender
        assert selected_limit == (20 if limit is None else limit)
        calls.append("publish")
        return 1

    monkeypatch.setattr(publish_jobs, "SessionLocal", factory)
    monkeypatch.setattr(publish_jobs, "build_job_sender", build)
    monkeypatch.setattr(publish_jobs, "publish_pending", publish)
    selected_argv = argv if limit is None else [*argv, "--limit", str(limit)]
    assert publish_jobs.main(selected_argv) == 0
    assert calls == ["build", "publish"]
    output = capsys.readouterr()
    assert output.out == "published=1\n"
    assert output.err == ""


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
def test_invalid_configuration_has_no_effects(
    environment: dict[str, str],
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
) -> None:
    environment.update(env)
    assert_failed(publish_jobs.main(argv), capsys)
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
    assert_failed(publish_jobs.main(["--transport", "aws"]), capsys)
    assert effects == []


@pytest.mark.parametrize(
    "argv",
    [
        ["--limit", "0"],
        ["--limit", "101"],
        ["--limit", "-1"],
        ["--limit", MARKER],
        ["--limit", "1.5"],
        ["--limit"],
        ["--transport", MARKER],
        ["--transport"],
        ["--endpoint"],
        ["--unknown", MARKER],
        [MARKER],
    ],
)
def test_invalid_arguments_and_limits_precede_loading(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    def forbidden(**kwargs: object) -> NoReturn:
        effects.append("load")
        raise RuntimeError(MARKER)

    monkeypatch.setattr(publish_jobs, "load_job_transport", forbidden)
    assert_failed(publish_jobs.main(argv), capsys)
    assert effects == []


def test_help_has_no_effects(
    monkeypatch: pytest.MonkeyPatch,
    effects: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(**kwargs: object) -> NoReturn:
        effects.append("load")
        raise RuntimeError(MARKER)

    monkeypatch.setattr(publish_jobs, "load_job_transport", forbidden)
    assert publish_jobs.main(["--help"]) == 0
    output = capsys.readouterr()
    assert "--transport" in output.out
    assert "--limit" in output.out
    assert output.err == ""
    assert effects == []


@pytest.mark.parametrize("mode", ["local", "aws"])
@pytest.mark.parametrize("stage", ["loader", "constructor", "publication", "partial"])
def test_failures_are_static_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    mode: str,
    stage: str,
) -> None:
    if mode == "aws":
        environment.update(AWS_ENV)
    calls: list[str] = []

    def fail_load(**kwargs: object) -> NoReturn:
        raise RuntimeError(MARKER)

    def build(settings: JobTransportSettings) -> JobSender:
        assert settings.mode == mode
        calls.append("build")
        if stage == "constructor":
            raise RuntimeError(MARKER)
        return cast(JobSender, object())

    def publish(db: sessionmaker[Session], sender: JobSender, limit: int) -> NoReturn:
        calls.append("publish")
        if stage == "partial":
            raise PublicationError(1, 1)
        raise RuntimeError(MARKER)

    if stage == "loader":
        monkeypatch.setattr(publish_jobs, "load_job_transport", fail_load)
    monkeypatch.setattr(publish_jobs, "build_job_sender", build)
    monkeypatch.setattr(publish_jobs, "publish_pending", publish)
    assert_failed(publish_jobs.main(["--transport", mode]), capsys)
    expected = [] if stage == "loader" else ["build"]
    if stage in ("publication", "partial"):
        expected.append("publish")
    assert calls == expected


@pytest.mark.parametrize("stage", ["parser", "loader", "constructor", "publication"])
def test_keyboard_interrupt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str],
    capsys: pytest.CaptureFixture[str],
    stage: str,
) -> None:
    calls: list[str] = []

    def interrupt(*args: object, **kwargs: object) -> NoReturn:
        calls.append("interrupt")
        raise KeyboardInterrupt

    def build(settings: JobTransportSettings) -> JobSender:
        calls.append("build")
        return cast(JobSender, object())

    def publish(db: sessionmaker[Session], sender: JobSender, limit: int) -> NoReturn:
        calls.append("publish")
        raise AssertionError("publication MUST NOT continue")

    monkeypatch.setattr(publish_jobs, "build_job_sender", build)
    monkeypatch.setattr(publish_jobs, "publish_pending", publish)
    if stage == "parser":
        monkeypatch.setattr(
            publish_jobs.argparse.ArgumentParser, "parse_args", interrupt
        )
    else:
        target = {
            "loader": "load_job_transport",
            "constructor": "build_job_sender",
            "publication": "publish_pending",
        }[stage]
        monkeypatch.setattr(publish_jobs, target, interrupt)
    assert publish_jobs.main([]) == 130
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "interrupted"}
    assert output.err == ""
    expected = ["build", "interrupt"] if stage == "publication" else ["interrupt"]
    assert calls == expected
