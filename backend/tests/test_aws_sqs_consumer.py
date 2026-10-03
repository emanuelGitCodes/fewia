import importlib
import traceback
from typing import cast
from unittest.mock import Mock

import pytest

from app.providers import aws_sqs_consumer
from app.providers.aws_sqs_consumer import AwsSqsConsumer, SqsConsumerClient
from app.providers.local_sqs_consumer import QueueMessage
from app.services.job_delivery import JobQueue

_REGION = "us-east-1"
_QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/fewia-agent"
_ERROR_DETAIL = "untrusted-provider-detail"
_MESSAGE = QueueMessage("raw-job", "sample-receipt")


class StringSubclass(str):
    pass


class IntSubclass(int):
    pass


class FakeSqsClient:
    def __init__(
        self, response: object = None, failure: BaseException | None = None
    ) -> None:
        self.response = response
        self.failure = failure
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __bool__(self) -> bool:
        return False

    def _request(self, operation: str, arguments: dict[str, object]) -> None:
        self.calls.append((operation, arguments))
        if self.failure is not None:
            raise self.failure

    def receive_message(
        self,
        *,
        QueueUrl: str,
        MaxNumberOfMessages: int,
        WaitTimeSeconds: int,
        VisibilityTimeout: int,
    ) -> dict[str, object]:
        self._request(
            "receive",
            {
                "QueueUrl": QueueUrl,
                "MaxNumberOfMessages": MaxNumberOfMessages,
                "WaitTimeSeconds": WaitTimeSeconds,
                "VisibilityTimeout": VisibilityTimeout,
            },
        )
        return cast(dict[str, object], self.response)

    def delete_message(
        self, *, QueueUrl: str, ReceiptHandle: str
    ) -> dict[str, object]:
        self._request(
            "acknowledge", {"QueueUrl": QueueUrl, "ReceiptHandle": ReceiptHandle}
        )
        return {}

    def change_message_visibility(
        self, *, QueueUrl: str, ReceiptHandle: str, VisibilityTimeout: int
    ) -> dict[str, object]:
        self._request(
            "extend",
            {
                "QueueUrl": QueueUrl,
                "ReceiptHandle": ReceiptHandle,
                "VisibilityTimeout": VisibilityTimeout,
            },
        )
        return {}


def _operate(consumer: JobQueue, operation: str) -> None:
    if operation == "receive":
        consumer.receive()
    elif operation == "acknowledge":
        consumer.acknowledge(_MESSAGE)
    else:
        consumer.extend(_MESSAGE, 120)


def test_import_does_not_construct_a_session(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = Mock()
    monkeypatch.setattr(aws_sqs_consumer.boto3, "Session", factory)

    importlib.reload(aws_sqs_consumer)

    factory.assert_not_called()


@pytest.mark.parametrize("body", ["raw-job", "", "{malformed-json", _ERROR_DETAIL])
def test_typed_fake_and_job_queue_preserve_raw_body_without_discovery(
    monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    factory = Mock()
    monkeypatch.setattr(aws_sqs_consumer.boto3, "Session", factory)
    fake = FakeSqsClient({"Messages": [{"Body": body, "ReceiptHandle": "receipt-1"}]})
    client: SqsConsumerClient = fake
    consumer: JobQueue = AwsSqsConsumer(_REGION, _QUEUE_URL, client=client)

    assert consumer.receive() == QueueMessage(body, "receipt-1")

    assert fake.calls == [
        (
            "receive",
            {
                "QueueUrl": _QUEUE_URL,
                "MaxNumberOfMessages": 1,
                "WaitTimeSeconds": 10,
                "VisibilityTimeout": 120,
            },
        )
    ]
    factory.assert_not_called()


@pytest.mark.parametrize("response", [{}, {"Messages": []}])
def test_empty_receive_returns_none(response: dict[str, object]) -> None:
    fake = FakeSqsClient(response)
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    assert consumer.receive() is None
    assert [operation for operation, _ in fake.calls] == ["receive"]


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        "invalid-response",
        {"Messages": None},
        {"Messages": {}},
        {"Messages": ()},
        {"Messages": "invalid-list"},
        {
            "Messages": [
                {"Body": "a", "ReceiptHandle": "receipt-1"},
                {"Body": "b", "ReceiptHandle": "receipt-2"},
            ],
        },
        {"Messages": [None]},
        {"Messages": ["invalid-message"]},
        {"Messages": [{}]},
        {"Messages": [{"ReceiptHandle": "receipt"}]},
        {"Messages": [{"Body": "body"}]},
        {"Messages": [{"Body": None, "ReceiptHandle": "receipt"}]},
        {"Messages": [{"Body": 1, "ReceiptHandle": "receipt"}]},
        {"Messages": [{"Body": "body", "ReceiptHandle": None}]},
        {"Messages": [{"Body": "body", "ReceiptHandle": 1}]},
        {"Messages": [{"Body": "body", "ReceiptHandle": ""}]},
        {"Messages": [{"Body": _ERROR_DETAIL, "ReceiptHandle": ""}]},
        {"Messages": [{"Body": "body", "ReceiptHandle": StringSubclass("r")}]},
    ],
)
def test_invalid_receive_response_is_static_and_does_not_mutate(
    response: object,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeSqsClient(response)
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    with pytest.raises(RuntimeError) as error:
        consumer.receive()

    assert str(error.value) == "SQS receive response is invalid"
    assert error.value.__cause__ is None
    assert [operation for operation, _ in fake.calls] == ["receive"]
    assert capsys.readouterr() == ("", "")
    assert caplog.text == ""


def test_redelivery_uses_the_current_receipt_for_each_mutation() -> None:
    fake = FakeSqsClient()
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    for receipt in ("receipt-1", "receipt-2"):
        fake.response = {"Messages": [{"Body": "same-body", "ReceiptHandle": receipt}]}
        message = consumer.receive()
        assert message is not None
        assert message == QueueMessage("same-body", receipt)
        consumer.extend(message, 30)
        consumer.acknowledge(message)

    assert fake.calls[1::3] == [
        (
            "extend",
            {"QueueUrl": _QUEUE_URL, "ReceiptHandle": receipt, "VisibilityTimeout": 30},
        )
        for receipt in ("receipt-1", "receipt-2")
    ]
    assert fake.calls[2::3] == [
        ("acknowledge", {"QueueUrl": _QUEUE_URL, "ReceiptHandle": receipt})
        for receipt in ("receipt-1", "receipt-2")
    ]


@pytest.mark.parametrize("seconds", [0, 43200])
def test_extend_accepts_visibility_bounds(seconds: int) -> None:
    fake = FakeSqsClient()
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    assert consumer.extend(_MESSAGE, seconds) is None

    assert fake.calls == [
        (
            "extend",
            {
                "QueueUrl": _QUEUE_URL,
                "ReceiptHandle": _MESSAGE.receipt_handle,
                "VisibilityTimeout": seconds,
            },
        )
    ]


@pytest.mark.parametrize(
    "message", [None, 1, "invalid-message", {}, {"receipt_handle": "receipt"}]
)
def test_invalid_message_type_precedes_mutation(message: object) -> None:
    fake = FakeSqsClient()
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    with pytest.raises(ValueError) as acknowledge_error:
        consumer.acknowledge(cast(QueueMessage, message))
    with pytest.raises(ValueError) as extend_error:
        consumer.extend(cast(QueueMessage, message), 30)

    expected = "message MUST be a QueueMessage with a nonempty string receipt"
    assert str(acknowledge_error.value) == expected
    assert str(extend_error.value) == expected
    assert fake.calls == []


@pytest.mark.parametrize("receipt", [None, 1, [], True, "", StringSubclass("r")])
def test_invalid_receipt_precedes_mutation(receipt: object) -> None:
    fake = FakeSqsClient()
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)
    message = QueueMessage(_ERROR_DETAIL, cast(str, receipt))

    with pytest.raises(ValueError) as acknowledge_error:
        consumer.acknowledge(message)
    with pytest.raises(ValueError) as extend_error:
        consumer.extend(message, 30)

    expected = "message MUST be a QueueMessage with a nonempty string receipt"
    assert str(acknowledge_error.value) == expected
    assert str(extend_error.value) == expected
    assert fake.calls == []


@pytest.mark.parametrize(
    "seconds", [None, True, False, -1, 43201, 1.0, "30", [], IntSubclass(30)]
)
def test_invalid_seconds_precedes_mutation(seconds: object) -> None:
    fake = FakeSqsClient()
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    with pytest.raises(ValueError) as error:
        consumer.extend(_MESSAGE, cast(int, seconds))

    assert str(error.value) == "seconds MUST be an integer from 0 to 43200"
    assert fake.calls == []


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
def test_ambient_session_pins_endpoint_timeouts_and_retry_limit(
    monkeypatch: pytest.MonkeyPatch, region: str
) -> None:
    fake = FakeSqsClient({})
    session = Mock()
    session.client.return_value = fake
    factory = Mock(return_value=session)
    monkeypatch.setattr(aws_sqs_consumer.boto3, "Session", factory)
    queue_url = f"https://sqs.{region}.amazonaws.com/123456789012/fewia-agent"

    consumer = AwsSqsConsumer(region, queue_url)
    assert consumer.receive() is None

    factory.assert_called_once_with()
    session.client.assert_called_once()
    assert session.client.call_args.args == ("sqs",)
    kwargs = session.client.call_args.kwargs
    assert set(kwargs) == {"region_name", "endpoint_url", "config"}
    assert kwargs["region_name"] == region
    assert kwargs["endpoint_url"] == f"https://sqs.{region}.amazonaws.com"
    config = kwargs["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 20
    assert config.retries == {"total_max_attempts": 1}
    assert config.proxies is None
    assert fake.calls[0][1]["QueueUrl"] == queue_url


@pytest.mark.parametrize("inject_client", [True, False])
@pytest.mark.parametrize(
    "region", [None, 1, [], "eu-west-1", "us-east-1 ", StringSubclass(_REGION)]
)
def test_invalid_region_precedes_client_creation(
    monkeypatch: pytest.MonkeyPatch, region: object, inject_client: bool
) -> None:
    factory = Mock()
    monkeypatch.setattr(aws_sqs_consumer.boto3, "Session", factory)
    fake = FakeSqsClient()

    with pytest.raises(ValueError) as error:
        AwsSqsConsumer(
            cast(str, region), _QUEUE_URL, client=fake if inject_client else None
        )

    assert str(error.value) == "region MUST be us-east-1 or us-west-2"
    factory.assert_not_called()
    assert fake.calls == []


@pytest.mark.parametrize("inject_client", [True, False])
@pytest.mark.parametrize(
    "queue_url",
    [
        None,
        1,
        [],
        "",
        StringSubclass(_QUEUE_URL),
        _QUEUE_URL + ".fifo",
        _QUEUE_URL + "/",
        _QUEUE_URL + "?" + _ERROR_DETAIL,
        _QUEUE_URL + "#" + _ERROR_DETAIL,
        _QUEUE_URL + "\n",
        _QUEUE_URL.replace("https:", "http:"),
        _QUEUE_URL.replace("us-east-1", "us-west-2"),
        _QUEUE_URL.replace("sqs.us-east-1", "sqs-fips.us-east-1"),
        _QUEUE_URL.replace("amazonaws.com", "amazonaws.com.evil.invalid"),
        _QUEUE_URL.replace("amazonaws.com", "amazonaws.com:443"),
        _QUEUE_URL.replace("sqs.", "user@" + "sqs."),
        _QUEUE_URL.replace("123456789012", "123"),
        "http://127.0.0.1:4566/000000000000/fewia-agent",
    ],
)
def test_invalid_url_precedes_client_creation(
    monkeypatch: pytest.MonkeyPatch, queue_url: object, inject_client: bool
) -> None:
    factory = Mock()
    monkeypatch.setattr(aws_sqs_consumer.boto3, "Session", factory)
    fake = FakeSqsClient()

    with pytest.raises(ValueError) as error:
        AwsSqsConsumer(
            _REGION, cast(str, queue_url), client=fake if inject_client else None
        )

    assert str(error.value) == "queue_url MUST be a canonical standard SQS URL"
    factory.assert_not_called()
    assert fake.calls == []


@pytest.mark.parametrize("stage", ["session", "client"])
@pytest.mark.parametrize("exception_type", [ValueError, RuntimeError, TimeoutError])
def test_initialization_exceptions_hide_details(
    monkeypatch: pytest.MonkeyPatch, stage: str, exception_type: type[Exception]
) -> None:
    session = Mock()
    failure = exception_type(_ERROR_DETAIL)
    session.client.side_effect = failure
    factory = Mock(return_value=session)
    if stage == "session":
        factory.side_effect = failure
    monkeypatch.setattr(aws_sqs_consumer.boto3, "Session", factory)

    with pytest.raises(RuntimeError) as error:
        AwsSqsConsumer(_REGION, _QUEUE_URL)

    assert str(error.value) == "SQS client initialization failed"
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
    assert _ERROR_DETAIL not in "".join(traceback.format_exception(error.value))
    factory.assert_called_once_with()
    if stage == "client":
        session.client.assert_called_once()


@pytest.mark.parametrize("operation", ["receive", "acknowledge", "extend"])
@pytest.mark.parametrize("exception_type", [ValueError, RuntimeError, TimeoutError])
def test_operation_exceptions_hide_details_without_retry(
    operation: str, exception_type: type[Exception]
) -> None:
    fake = FakeSqsClient(failure=exception_type(_ERROR_DETAIL))
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    with pytest.raises(RuntimeError) as error:
        _operate(consumer, operation)

    assert str(error.value) == f"SQS {operation} failed"
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
    assert _ERROR_DETAIL not in "".join(traceback.format_exception(error.value))
    assert [name for name, _ in fake.calls] == [operation]


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
    monkeypatch.setattr(aws_sqs_consumer.boto3, "Session", factory)

    with pytest.raises(exception_type) as error:
        AwsSqsConsumer(_REGION, _QUEUE_URL)

    assert error.value is failure


@pytest.mark.parametrize("operation", ["receive", "acknowledge", "extend"])
@pytest.mark.parametrize("exception_type", [KeyboardInterrupt, SystemExit])
def test_operation_interrupts_propagate(
    operation: str, exception_type: type[BaseException]
) -> None:
    failure = exception_type()
    fake = FakeSqsClient(failure=failure)
    consumer = AwsSqsConsumer(_REGION, _QUEUE_URL, client=fake)

    with pytest.raises(exception_type) as error:
        _operate(consumer, operation)

    assert error.value is failure
    assert [name for name, _ in fake.calls] == [operation]
