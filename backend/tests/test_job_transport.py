import os
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import NoReturn, cast

import pytest

from app.providers import aws_sqs_sender, job_transport
from app.providers.job_transport_settings import JobTransportSettings
from app.providers.local_sqs_consumer import QueueMessage
from app.services.job_delivery import JobQueue
from app.services.outbox_publisher import JobSender

ENDPOINTS = (
    "http://127.0.0.1:4566",
    "http://localhost:4566",
    "http://floci:4566",
)
REGION = "us-east-1"
AGENT_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/custom-agent_07"
SYNC_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/custom-sync_08"


class _Sender:
    def send(self, kind: str, job_id: str) -> None:
        pass


class _Queue:
    def receive(self) -> QueueMessage | None:
        return None

    def acknowledge(self, message: QueueMessage) -> None:
        pass

    def extend(self, message: QueueMessage, seconds: int) -> None:
        pass


@dataclass
class _Providers:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = field(
        default_factory=list
    )
    sender: JobSender = field(default_factory=_Sender)
    queue: JobQueue = field(default_factory=_Queue)


@pytest.fixture(autouse=True)
def providers(monkeypatch: pytest.MonkeyPatch) -> _Providers:
    recorded = _Providers()

    def sender_constructor(name: str) -> Callable[..., JobSender]:
        def construct(*args: object, **kwargs: object) -> JobSender:
            recorded.calls.append((name, args, kwargs))
            return recorded.sender

        return construct

    def queue_constructor(name: str) -> Callable[..., JobQueue]:
        def construct(*args: object, **kwargs: object) -> JobQueue:
            recorded.calls.append((name, args, kwargs))
            return recorded.queue

        return construct

    for name in ("LocalSqsSender", "AwsSqsSender"):
        monkeypatch.setattr(job_transport, name, sender_constructor(name))
    for name in ("LocalSqsConsumer", "AwsSqsConsumer"):
        monkeypatch.setattr(job_transport, name, queue_constructor(name))

    def reject_session(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Factories MUST NOT create unpatched clients")

    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", reject_session)
    return recorded


def _settings(cloud: bool, region: str = REGION) -> JobTransportSettings:
    if not cloud:
        return JobTransportSettings("local", endpoint=ENDPOINTS[0])
    return JobTransportSettings(
        "aws",
        region=region,
        agent_queue_url=AGENT_URL.replace(REGION, region),
        sync_queue_url=SYNC_URL.replace(REGION, region),
    )


def _assert_invalid(settings: object, providers: _Providers) -> None:
    value = cast(JobTransportSettings, settings)
    actions: tuple[Callable[[], object], ...] = (
        lambda: job_transport.build_job_sender(value),
        lambda: job_transport.build_job_queue(value, "agent"),
        lambda: job_transport.build_job_queue(value, "sync"),
    )
    for action in actions:
        with pytest.raises(ValueError) as error:
            action()
        assert error.value.args == ("Job transport configuration is invalid",)
        assert error.value.__cause__ is None
        assert error.value.__context__ is None
        assert providers.calls == []


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("kind", ["agent", "sync"])
def test_local_passes_only_exact_endpoint_and_kind(
    endpoint: str, kind: str, providers: _Providers
) -> None:
    settings = JobTransportSettings("local", endpoint=endpoint)
    assert job_transport.build_job_sender(settings) is providers.sender
    assert job_transport.build_job_queue(settings, kind) is providers.queue
    assert providers.calls == [
        ("LocalSqsSender", (), {"endpoint_url": endpoint}),
        ("LocalSqsConsumer", (), {"endpoint_url": endpoint, "kind": kind}),
    ]


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
@pytest.mark.parametrize("kind", ["agent", "sync"])
def test_aws_passes_exact_configured_urls(
    region: str, kind: str, providers: _Providers
) -> None:
    settings = _settings(True, region)
    assert job_transport.build_job_sender(settings) is providers.sender
    assert job_transport.build_job_queue(settings, kind) is providers.queue
    queue_url = settings.agent_queue_url if kind == "agent" else settings.sync_queue_url
    assert providers.calls == [
        (
            "AwsSqsSender",
            (),
            {
                "region": region,
                "agent_queue_url": settings.agent_queue_url,
                "sync_queue_url": settings.sync_queue_url,
            },
        ),
        ("AwsSqsConsumer", (), {"region": region, "queue_url": queue_url}),
    ]


class _String(str):
    pass


@pytest.mark.parametrize(
    "value",
    [None, False, 1, "local", {}, [], SimpleNamespace(mode="local")],
)
def test_rejects_wrong_settings_types(value: object, providers: _Providers) -> None:
    _assert_invalid(value, providers)


def test_rejects_settings_subclass_with_bypassed_validation(
    providers: _Providers,
) -> None:
    class UnvalidatedSettings(JobTransportSettings):
        def __post_init__(self) -> None:
            pass

    _assert_invalid(UnvalidatedSettings("local"), providers)


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("mode", [None, [], False, "cloud", _String("local")])
def test_revalidates_forged_mode(
    cloud: bool, mode: object, providers: _Providers
) -> None:
    settings = _settings(cloud)
    object.__setattr__(settings, "mode", mode)
    _assert_invalid(settings, providers)


@pytest.mark.parametrize(
    "name,value",
    [
        ("mode", "aws"),
        ("endpoint", None),
        ("endpoint", []),
        ("endpoint", _String(ENDPOINTS[0])),
        ("endpoint", "http://169.254.169.254"),
        ("endpoint", ENDPOINTS[0] + "/"),
        ("region", REGION),
        ("region", ""),
        ("agent_queue_url", AGENT_URL),
        ("agent_queue_url", ""),
        ("sync_queue_url", SYNC_URL),
        ("sync_queue_url", ""),
    ],
)
def test_revalidates_all_forged_local_fields(
    name: str, value: object, providers: _Providers
) -> None:
    settings = _settings(False)
    object.__setattr__(settings, name, value)
    _assert_invalid(settings, providers)


@pytest.mark.parametrize(
    "name,value",
    [
        ("mode", "local"),
        ("endpoint", ENDPOINTS[0]),
        ("endpoint", ""),
        ("endpoint", []),
        ("region", None),
        ("region", []),
        ("region", _String(REGION)),
        ("region", "eu-west-1"),
        ("region", "us-west-2"),
        ("agent_queue_url", None),
        ("agent_queue_url", []),
        ("agent_queue_url", _String(AGENT_URL)),
        ("agent_queue_url", SYNC_URL),
        ("agent_queue_url", AGENT_URL + "?marker=invalid"),
        ("agent_queue_url", AGENT_URL.replace("https:", "http:")),
        ("agent_queue_url", AGENT_URL.replace("123456789012", "999999999999")),
        ("sync_queue_url", None),
        ("sync_queue_url", []),
        ("sync_queue_url", _String(SYNC_URL)),
        ("sync_queue_url", AGENT_URL),
        ("sync_queue_url", SYNC_URL.replace("us-east-1", "us-west-2")),
        ("sync_queue_url", SYNC_URL.replace("123456789012", "999999999999")),
        ("sync_queue_url", SYNC_URL.replace("amazonaws.com", "evil.invalid")),
        ("sync_queue_url", SYNC_URL + ".fifo"),
        ("sync_queue_url", SYNC_URL + "#marker"),
    ],
)
def test_revalidates_all_forged_aws_fields(
    name: str, value: object, providers: _Providers
) -> None:
    settings = _settings(True)
    object.__setattr__(settings, name, value)
    _assert_invalid(settings, providers)


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize(
    "kind", [None, False, 1, [], {}, "", "AGENT", "sync ", "other", _String("agent")]
)
def test_rejects_invalid_kinds_before_construction(
    cloud: bool, kind: object, providers: _Providers
) -> None:
    settings = _settings(cloud)
    with pytest.raises(ValueError) as error:
        job_transport.build_job_queue(settings, cast(str, kind))
    assert error.value.args == ("kind MUST be agent or sync",)
    assert providers.calls == []


@pytest.mark.parametrize("cloud", [False, True])
@pytest.mark.parametrize("kind", [None, "agent", "sync"])
def test_constructor_failure_propagates_without_fallback(
    cloud: bool,
    kind: str | None,
    providers: _Providers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(cloud)
    prefix = "Aws" if cloud else "Local"
    symbol = prefix + ("SqsSender" if kind is None else "SqsConsumer")
    failure = RuntimeError("SQS client initialization failed")

    def fail(*args: object, **kwargs: object) -> NoReturn:
        providers.calls.append((symbol, args, kwargs))
        raise failure

    monkeypatch.setattr(job_transport, symbol, fail)
    with pytest.raises(RuntimeError) as error:
        if kind is None:
            job_transport.build_job_sender(settings)
        else:
            job_transport.build_job_queue(settings, kind)
    assert error.value is failure
    assert len(providers.calls) == 1
    assert providers.calls[0][0] == symbol


class _UnreadableEnvironment(Mapping[str, str]):
    def __getitem__(self, key: str) -> str:
        raise AssertionError("Factories MUST NOT read the environment")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("Factories MUST NOT read the environment")

    def __len__(self) -> int:
        raise AssertionError("Factories MUST NOT read the environment")


@pytest.mark.parametrize("cloud", [False, True])
def test_factories_do_not_read_environment(
    cloud: bool, providers: _Providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(cloud)
    with monkeypatch.context() as guarded:
        guarded.setattr(os, "environ", _UnreadableEnvironment())
        sender = job_transport.build_job_sender(settings)
        agent_queue = job_transport.build_job_queue(settings, "agent")
        sync_queue = job_transport.build_job_queue(settings, "sync")
    assert sender is providers.sender
    assert agent_queue is providers.queue
    assert sync_queue is providers.queue
    assert len(providers.calls) == 3
