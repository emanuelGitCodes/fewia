import json
import traceback
from typing import cast
from unittest.mock import Mock

import pytest

from app.providers import aws_sqs_sender
from app.providers.aws_sqs_sender import AwsSqsSender, SqsClient, validate_queue_url
from app.services.job_delivery import _job_id
from app.services.outbox_publisher import JobSender

_REGION = "us-east-1"
_ROOT = "https://sqs.us-east-1.amazonaws.com/123456789012/"
_AGENT_URL = _ROOT + "fewia-agent"
_SYNC_URL = _ROOT + "fewia-sync"
_JOB_ID = "12345678-1234-5678-9abc-123456789abc"
_ERROR_DETAIL = "untrusted-provider-detail"


class StringSubclass(str):
    pass


class FakeSqsClient:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.failure = failure

    def __bool__(self) -> bool:
        return False

    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, object]:
        self.calls.append((QueueUrl, MessageBody))
        if self.failure is not None:
            raise self.failure
        return {"MessageId": "sample-message-id"}


@pytest.mark.parametrize(
    ("kind", "queue_url"), [("agent", _AGENT_URL), ("sync", _SYNC_URL)]
)
def test_typed_fake_routes_only_the_durable_job_envelope(
    monkeypatch: pytest.MonkeyPatch, kind: str, queue_url: str
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", session_factory)
    fake = FakeSqsClient()
    client: SqsClient = fake
    sender: JobSender = AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL, client=client)

    assert sender.send(kind, _JOB_ID) is None

    session_factory.assert_not_called()
    assert fake.calls == [(queue_url, json.dumps({"job_id": _JOB_ID}))]
    assert _job_id(fake.calls[0][1]) == _JOB_ID


def test_replay_preserves_the_durable_job_envelope() -> None:
    fake = FakeSqsClient()
    sender = AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL, client=fake)

    sender.send("agent", _JOB_ID)
    sender.send("agent", _JOB_ID)

    assert fake.calls == [(_AGENT_URL, json.dumps({"job_id": _JOB_ID}))] * 2


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
def test_ambient_credentials_and_pinned_aws_client_settings(
    monkeypatch: pytest.MonkeyPatch, region: str
) -> None:
    fake = FakeSqsClient()
    session = Mock()
    session.client.return_value = fake
    session_factory = Mock(return_value=session)
    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", session_factory)
    root = f"https://sqs.{region}.amazonaws.com/123456789012/"

    sender = AwsSqsSender(region, root + "agent", root + "sync")
    sender.send("sync", _JOB_ID)

    session_factory.assert_called_once_with()
    session.client.assert_called_once()
    assert session.client.call_args.args == ("sqs",)
    kwargs = session.client.call_args.kwargs
    assert set(kwargs) == {"region_name", "endpoint_url", "config"}
    assert kwargs["region_name"] == region
    assert kwargs["endpoint_url"] == f"https://sqs.{region}.amazonaws.com"
    config = kwargs["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries == {"total_max_attempts": 1}
    assert config.proxies is None
    assert fake.calls == [(root + "sync", json.dumps({"job_id": _JOB_ID}))]


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
@pytest.mark.parametrize("name", ["a", "A0_-", "a" * 80])
def test_validate_queue_url_preserves_canonical_urls(region: str, name: str) -> None:
    url = f"https://sqs.{region}.amazonaws.com/000000000000/{name}"

    assert validate_queue_url(region, url) == url


@pytest.mark.parametrize(
    "region",
    [None, 1, [], "eu-west-1", "us-east-1 ", StringSubclass(_REGION)],
)
def test_invalid_region_precedes_session_creation(
    monkeypatch: pytest.MonkeyPatch, region: object
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", session_factory)

    with pytest.raises(ValueError) as error:
        AwsSqsSender(cast(str, region), _AGENT_URL, _SYNC_URL)

    assert str(error.value) == "region MUST be us-east-1 or us-west-2"
    session_factory.assert_not_called()


@pytest.mark.parametrize("field", ["agent", "sync"])
@pytest.mark.parametrize(
    "queue_url",
    [
        None,
        1,
        [],
        StringSubclass(_AGENT_URL),
        "",
        _ROOT,
        _ROOT + "a" * 81,
        _ROOT + "queue.fifo",
        _ROOT + "queue.name",
        _ROOT + "caf\u00e9",
        _ROOT + "queue/name",
        _ROOT + "queue:other",
        _ROOT + "%61gent",
        _ROOT + "agent%2Fother",
        _AGENT_URL + "?token=" + _ERROR_DETAIL,
        _AGENT_URL + "#" + _ERROR_DETAIL,
        _AGENT_URL + "?",
        _AGENT_URL + "#",
        _AGENT_URL + "/",
        _AGENT_URL + " ",
        " " + _AGENT_URL,
        _AGENT_URL + "\n",
        _AGENT_URL + "\r",
        _ROOT + "\tagent",
        _ROOT + "\x00agent",
        _ROOT + "\x1fagent",
        _ROOT + "agent\x7f",
        _ROOT + "agent\\other",
        _ROOT + "agent\u00a0",
        _AGENT_URL.replace("https://", "http://"),
        _AGENT_URL.replace("https://", "HTTPS://"),
        _AGENT_URL.replace("sqs.", "SQS."),
        _AGENT_URL.replace("sqs.", _ERROR_DETAIL + "@sqs."),
        _AGENT_URL.replace("sqs.", "user:" + _ERROR_DETAIL + "@sqs."),
        _AGENT_URL.replace(".com/", ".com:443/"),
        _AGENT_URL.replace(".com/", ".com./"),
        _AGENT_URL.replace(".com/", ".com.evil.invalid/"),
        _AGENT_URL.replace("amazonaws.com", "amazonaws.com.cn"),
        _AGENT_URL.replace("sqs.us-east-1", "sqs.us-west-2"),
        _AGENT_URL.replace("sqs.us-east-1", "sqs-fips.us-east-1"),
        _AGENT_URL.replace("sqs.us-east-1", "sqs.eu-west-1"),
        _AGENT_URL.replace("sqs.us-east-1", "queue.amazonaws.com"),
        _AGENT_URL.replace("123456789012", "12345678901"),
        _AGENT_URL.replace("123456789012", "1234567890123"),
        _AGENT_URL.replace("123456789012", "\u0661" * 12),
        _AGENT_URL.replace("/123456789012/", "//123456789012/"),
        _AGENT_URL.replace("/123456789012/", "/123456789012/../"),
    ],
)
def test_invalid_queue_configuration_precedes_session_creation(
    monkeypatch: pytest.MonkeyPatch, field: str, queue_url: object
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", session_factory)
    agent_url = cast(str, queue_url) if field == "agent" else _AGENT_URL
    sync_url = cast(str, queue_url) if field == "sync" else _SYNC_URL

    with pytest.raises(ValueError) as error:
        AwsSqsSender(_REGION, agent_url, sync_url)

    assert str(error.value) == "queue_url MUST be a canonical standard SQS URL"
    assert _ERROR_DETAIL not in str(error.value)
    session_factory.assert_not_called()


@pytest.mark.parametrize(
    "sync_url",
    [_AGENT_URL, _SYNC_URL.replace("123456789012", "210987654321")],
)
def test_queue_pair_validation_precedes_session_creation(
    monkeypatch: pytest.MonkeyPatch, sync_url: str
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", session_factory)

    with pytest.raises(ValueError) as error:
        AwsSqsSender(_REGION, _AGENT_URL, sync_url)

    assert str(error.value) == "queues MUST differ and use the same account"
    session_factory.assert_not_called()


def test_injected_client_does_not_bypass_configuration_validation() -> None:
    fake = FakeSqsClient()

    with pytest.raises(ValueError):
        AwsSqsSender(_REGION, _AGENT_URL, _AGENT_URL, client=fake)
    with pytest.raises(ValueError):
        AwsSqsSender(_REGION, _AGENT_URL, "invalid", client=fake)

    assert fake.calls == []


@pytest.mark.parametrize(
    "kind", [None, 1, [], {}, "AGENT", "agent ", _ERROR_DETAIL, StringSubclass("agent")]
)
def test_invalid_kind_precedes_client_send(kind: object) -> None:
    fake = FakeSqsClient()
    sender = AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL, client=fake)

    with pytest.raises(ValueError) as error:
        sender.send(cast(str, kind), _JOB_ID)

    assert str(error.value) == "kind MUST be agent or sync"
    assert fake.calls == []


@pytest.mark.parametrize(
    "job_id",
    [
        None,
        1,
        [],
        {},
        StringSubclass(_JOB_ID),
        "",
        _ERROR_DETAIL,
        _JOB_ID.upper(),
        _JOB_ID.replace("-", ""),
        "{" + _JOB_ID + "}",
        "urn:uuid:" + _JOB_ID,
        _JOB_ID + "\n",
        " " + _JOB_ID,
        _JOB_ID.replace("1", "z"),
        _JOB_ID.replace("-", "_"),
    ],
)
def test_invalid_job_id_precedes_client_send(job_id: object) -> None:
    fake = FakeSqsClient()
    sender = AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL, client=fake)

    with pytest.raises(ValueError) as error:
        sender.send("sync", cast(str, job_id))

    assert str(error.value) == "job_id MUST be a canonical UUID"
    assert fake.calls == []


@pytest.mark.parametrize("stage", ["session", "client"])
@pytest.mark.parametrize("exception_type", [ValueError, RuntimeError, TimeoutError])
def test_initialization_errors_hide_provider_details(
    monkeypatch: pytest.MonkeyPatch, stage: str, exception_type: type[Exception]
) -> None:
    failure = exception_type(_ERROR_DETAIL)
    session = Mock()
    session.client.side_effect = failure
    factory = Mock(return_value=session)
    if stage == "session":
        factory.side_effect = failure
    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", factory)

    with pytest.raises(RuntimeError) as error:
        AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL)

    assert str(error.value) == "SQS client initialization failed"
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
    assert _ERROR_DETAIL not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("exception_type", [ValueError, RuntimeError, TimeoutError])
def test_send_errors_hide_provider_details_without_retry(
    exception_type: type[Exception],
) -> None:
    fake = FakeSqsClient(exception_type(_ERROR_DETAIL))
    sender = AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL, client=fake)

    with pytest.raises(RuntimeError) as error:
        sender.send("agent", _JOB_ID)

    assert str(error.value) == "SQS send failed"
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
    assert _ERROR_DETAIL not in "".join(traceback.format_exception(error.value))
    assert len(fake.calls) == 1


@pytest.mark.parametrize("stage", ["session", "client"])
@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_initialization_interrupts_propagate(
    monkeypatch: pytest.MonkeyPatch, stage: str, exception_type: type[BaseException]
) -> None:
    failure = exception_type()
    session = Mock()
    session.client.side_effect = failure
    factory = Mock(return_value=session)
    if stage == "session":
        factory.side_effect = failure
    monkeypatch.setattr(aws_sqs_sender.boto3, "Session", factory)

    with pytest.raises(exception_type) as error:
        AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL)

    assert error.value is failure


@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_send_interrupts_propagate(exception_type: type[BaseException]) -> None:
    failure = exception_type()
    fake = FakeSqsClient(failure)
    sender = AwsSqsSender(_REGION, _AGENT_URL, _SYNC_URL, client=fake)

    with pytest.raises(exception_type) as error:
        sender.send("sync", _JOB_ID)

    assert error.value is failure
    assert len(fake.calls) == 1
