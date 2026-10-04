"""Test job transport boundaries with fake environments."""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from typing import NoReturn, cast

import pytest

from app.providers import aws_sqs_sender, job_transport_settings
from app.providers.job_transport_settings import (
    JobTransportSettings,
    load_job_transport,
)

REGION = "us-east-1"
AGENT_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/fewia-agent"
SYNC_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/fewia-sync"
FORBIDDEN_KEYS = (
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
)


def _aws_env(region: str = REGION) -> dict[str, str]:
    return {
        "FEWIA_TRANSPORT_MODE": "aws",
        "AWS_REGION": region,
        "FEWIA_AWS_AGENT_QUEUE_URL": AGENT_URL.replace(REGION, region),
        "FEWIA_AWS_SYNC_QUEUE_URL": SYNC_URL.replace(REGION, region),
    }


def _assert_invalid(action: Callable[[], object]) -> None:
    with pytest.raises(ValueError) as exc_info:
        action()
    error = exc_info.value
    assert error.args == ("Job transport configuration is invalid",)
    assert error.__cause__ is None
    assert error.__context__ is None


@pytest.fixture(autouse=True)
def _reject_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Settings MUST NOT construct AWS sessions")

    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", reject)


def test_default_local_uses_fake_environment_without_mutation() -> None:
    env: dict[str, str] = {}
    settings = load_job_transport(environ=env)
    assert settings == JobTransportSettings("local", "http://127.0.0.1:4566")
    assert env == {}


def test_default_environment_is_read_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env = {"FEWIA_LOCAL_ENDPOINT_URL": "http://floci:4566"}
    monkeypatch.setattr(job_transport_settings, "os", SimpleNamespace(environ=env))
    assert load_job_transport().endpoint == "http://floci:4566"
    assert env == {"FEWIA_LOCAL_ENDPOINT_URL": "http://floci:4566"}


@pytest.mark.parametrize(
    "endpoint",
    ["http://127.0.0.1:4566", "http://localhost:4566", "http://floci:4566"],
)
def test_explicit_local_and_matching_environment(endpoint: str) -> None:
    settings = load_job_transport(mode="local", endpoint=endpoint, environ={})
    assert settings.endpoint == endpoint
    env = {"FEWIA_TRANSPORT_MODE": "local", "FEWIA_LOCAL_ENDPOINT_URL": endpoint}
    assert load_job_transport(environ=env).endpoint == endpoint
    assert load_job_transport(mode="local", endpoint=endpoint, environ=env) == (
        JobTransportSettings("local", endpoint)
    )


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
def test_aws_from_environment_and_matching_cli(region: str) -> None:
    env = _aws_env(region)
    before = env.copy()
    expected = JobTransportSettings(
        "aws",
        region=region,
        agent_queue_url=env["FEWIA_AWS_AGENT_QUEUE_URL"],
        sync_queue_url=env["FEWIA_AWS_SYNC_QUEUE_URL"],
    )
    assert load_job_transport(environ=env) == expected
    assert load_job_transport(mode="aws", environ=env) == expected
    assert env == before
    del env["FEWIA_TRANSPORT_MODE"]
    before = env.copy()
    assert load_job_transport(mode="aws", environ=env) == expected
    assert env == before


@pytest.mark.parametrize("mode", ["", "LOCAL", "AWS", "aws ", " local", "cloud"])
def test_modes_are_exact(mode: str) -> None:
    _assert_invalid(lambda: load_job_transport(mode=mode, environ={}))
    _assert_invalid(lambda: load_job_transport(environ={"FEWIA_TRANSPORT_MODE": mode}))
    _assert_invalid(
        lambda: load_job_transport(mode="local", environ={"FEWIA_TRANSPORT_MODE": mode})
    )


@pytest.mark.parametrize("cli_mode,env_mode", [("local", "aws"), ("aws", "local")])
def test_conflicting_modes_fail(cli_mode: str, env_mode: str) -> None:
    _assert_invalid(
        lambda: load_job_transport(
            mode=cli_mode, environ={"FEWIA_TRANSPORT_MODE": env_mode}
        )
    )


def test_conflicting_local_endpoints_fail() -> None:
    _assert_invalid(
        lambda: load_job_transport(
            endpoint="http://localhost:4566",
            environ={"FEWIA_LOCAL_ENDPOINT_URL": "http://floci:4566"},
        )
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        " http://localhost:4566",
        "HTTP://localhost:4566",
        "http://localhost:4566/",
        "http://localhost:4566.evil.invalid",
        "http://user:password@localhost:4566",
        "https://localhost:4566",
        "http://localhost:4566?secret=marker",
        "http://169.254.169.254",
    ],
)
def test_local_endpoint_allowlist(endpoint: str) -> None:
    _assert_invalid(lambda: load_job_transport(endpoint=endpoint, environ={}))
    _assert_invalid(
        lambda: load_job_transport(environ={"FEWIA_LOCAL_ENDPOINT_URL": endpoint})
    )


@pytest.mark.parametrize(
    "key", ["FEWIA_AWS_AGENT_QUEUE_URL", "FEWIA_AWS_SYNC_QUEUE_URL"]
)
@pytest.mark.parametrize("value", ["", AGENT_URL])
def test_local_rejects_cloud_queue_key_presence(key: str, value: str) -> None:
    _assert_invalid(lambda: load_job_transport(environ={key: value}))


def test_local_ignores_bedrock_region_and_credentials() -> None:
    env = {key: "unused-marker" for key in FORBIDDEN_KEYS}
    env.update(
        {
            "AWS_REGION": "eu-west-1",
            "FEWIA_BEDROCK_REGION": "us-west-2",
            "FEWIA_BEDROCK_MODEL_ID": "model",
        }
    )
    before = env.copy()
    assert load_job_transport(environ=env).mode == "local"
    assert env == before


@pytest.mark.parametrize("endpoint", ["", "http://localhost:4566"])
def test_aws_rejects_local_endpoint_presence(endpoint: str) -> None:
    _assert_invalid(lambda: load_job_transport(endpoint=endpoint, environ=_aws_env()))
    env = _aws_env()
    env["FEWIA_LOCAL_ENDPOINT_URL"] = endpoint
    _assert_invalid(lambda: load_job_transport(environ=env))


@pytest.mark.parametrize(
    "key", ["AWS_REGION", "FEWIA_AWS_AGENT_QUEUE_URL", "FEWIA_AWS_SYNC_QUEUE_URL"]
)
def test_aws_requires_each_field(key: str) -> None:
    env = _aws_env()
    del env[key]
    _assert_invalid(lambda: load_job_transport(environ=env))
    env[key] = ""
    _assert_invalid(lambda: load_job_transport(environ=env))


@pytest.mark.parametrize("region", ["", "eu-west-1", "US-EAST-1", "us-east-1 "])
def test_aws_region_allowlist(region: str) -> None:
    _assert_invalid(lambda: load_job_transport(environ=_aws_env(region)))


@pytest.mark.parametrize(
    "url",
    [
        AGENT_URL,
        SYNC_URL.replace("123456789012", "999999999999"),
        SYNC_URL.replace("us-east-1", "us-west-2"),
        SYNC_URL.replace("https://", "http://"),
        SYNC_URL.replace("amazonaws.com", "amazonaws.com.evil.invalid"),
        SYNC_URL.replace("sqs.", "user:password@sqs."),
        SYNC_URL.replace("123456789012", "123"),
        SYNC_URL.replace("fewia-sync", "a" * 81),
        SYNC_URL + ".fifo",
        SYNC_URL + "/",
        SYNC_URL + "?secret=marker",
        SYNC_URL + "#marker",
        SYNC_URL + "\n",
        " " + SYNC_URL,
    ],
)
def test_aws_rejects_unsafe_mismatched_or_identical_queues(url: str) -> None:
    env = _aws_env()
    env["FEWIA_AWS_SYNC_QUEUE_URL"] = url
    _assert_invalid(lambda: load_job_transport(environ=env))


class _UnreadableValues(Mapping[str, str]):
    def __init__(self, env: dict[str, str], unreadable: set[str]) -> None:
        self._env = env
        self._unreadable = unreadable

    def __getitem__(self, key: str) -> str:
        if key in self._unreadable:
            raise AssertionError("Credential values MUST NOT be read")
        return self._env[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._env)

    def __len__(self) -> int:
        return len(self._env)


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
@pytest.mark.parametrize("value", ["", "unreadable-marker"])
def test_aws_rejects_forbidden_keys_without_reading_values(
    key: str,
    value: str,
) -> None:
    env = _aws_env()
    env[key] = value
    _assert_invalid(lambda: load_job_transport(environ=_UnreadableValues(env, {key})))


def test_local_does_not_read_credential_values() -> None:
    env = {key: "unreadable-marker" for key in FORBIDDEN_KEYS}
    guarded_env = _UnreadableValues(env, set(FORBIDDEN_KEYS))
    settings = load_job_transport(environ=guarded_env)
    assert settings.mode == "local"


def test_aws_allows_unread_container_metadata() -> None:
    env = _aws_env()
    metadata = {
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
    }
    env.update({key: "unreadable-marker" for key in metadata})
    assert load_job_transport(environ=_UnreadableValues(env, metadata)).mode == "aws"


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": ""},
        {"mode": "LOCAL"},
        {"mode": "aws"},
        {"endpoint": None},
        {"endpoint": "https://evil.invalid"},
        {"endpoint": []},
        {"region": REGION},
        {"agent_queue_url": ""},
        {"sync_queue_url": SYNC_URL},
    ],
)
def test_direct_local_construction_rejects_inconsistent_fields(
    changes: dict[str, object],
) -> None:
    settings = JobTransportSettings("local", "http://localhost:4566")
    _assert_invalid(lambda: replace(settings, **changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "local"},
        {"mode": []},
        {"endpoint": "http://localhost:4566"},
        {"endpoint": ""},
        {"region": None},
        {"region": "eu-west-1"},
        {"region": []},
        {"agent_queue_url": None},
        {"agent_queue_url": []},
        {"agent_queue_url": SYNC_URL + "#marker"},
        {"sync_queue_url": None},
        {"sync_queue_url": []},
        {"sync_queue_url": AGENT_URL},
        {"sync_queue_url": SYNC_URL.replace("123456789012", "999999999999")},
        {"sync_queue_url": SYNC_URL + "?secret=marker"},
    ],
)
def test_direct_aws_construction_rejects_inconsistent_fields(
    changes: dict[str, object],
) -> None:
    settings = load_job_transport(environ=_aws_env())
    _assert_invalid(lambda: replace(settings, **changes))


@pytest.mark.parametrize("value", [[], 1, False])
def test_loader_rejects_nonstring_cli_values(value: object) -> None:
    _assert_invalid(lambda: load_job_transport(mode=cast(str, value), environ={}))
    _assert_invalid(lambda: load_job_transport(endpoint=cast(str, value), environ={}))


@pytest.mark.parametrize("cloud", [False, True])
def test_settings_hide_urls_and_are_frozen(cloud: bool) -> None:
    settings = load_job_transport(environ=_aws_env() if cloud else {})
    rendered = f"{settings!s}{settings!r}"
    for url in (settings.endpoint, settings.agent_queue_url, settings.sync_queue_url):
        if url is not None:
            assert url not in rendered
    for name in ("mode", "endpoint", "region", "agent_queue_url", "sync_queue_url"):
        with pytest.raises(FrozenInstanceError):
            setattr(settings, name, "replacement")
