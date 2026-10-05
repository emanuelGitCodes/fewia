"""Test the local SQS consumer transport."""

from unittest.mock import Mock

import pytest

from app.providers import local_sqs, local_sqs_consumer
from app.providers.local_sqs_consumer import LocalSqsConsumer, QueueMessage


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: Mock) -> Mock:
    session = Mock()
    session.client.return_value = client
    session_factory = Mock(return_value=session)
    monkeypatch.setattr(local_sqs_consumer.boto3, "Session", session_factory)
    return session_factory


def _queue_url(endpoint_url: str, kind: str) -> str:
    return f"{endpoint_url}/000000000000/{local_sqs.QUEUE_NAMES[kind]}"


@pytest.mark.parametrize(
    ("kind", "queue_name"),
    [("sync", "fewia-sync"), ("agent", "fewia-agent")],
)
@pytest.mark.parametrize("returned_endpoint_url", sorted(local_sqs.ALLOWED_ENDPOINTS))
@pytest.mark.parametrize("endpoint_url", sorted(local_sqs.ALLOWED_ENDPOINTS))
def test_receive_long_polls_one_message_and_returns_raw_body(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    queue_name: str,
    endpoint_url: str,
    returned_endpoint_url: str,
) -> None:
    client = Mock()
    returned_queue_url = _queue_url(returned_endpoint_url, kind)
    normalized_queue_url = _queue_url(endpoint_url, kind)
    client.get_queue_url.return_value = {"QueueUrl": returned_queue_url}
    client.receive_message.return_value = {
        "Messages": [{"Body": "raw-job", "ReceiptHandle": "rh-1"}]
    }
    session_factory = _patch_client(monkeypatch, client)

    consumer = LocalSqsConsumer(endpoint_url, kind)
    message = consumer.receive()

    assert message == QueueMessage(body="raw-job", receipt_handle="rh-1")
    session_factory.assert_called_once_with(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    client_kwargs = session_factory.return_value.client.call_args.kwargs
    assert client_kwargs["endpoint_url"] == endpoint_url
    config = client_kwargs["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 20
    assert config.read_timeout > 10
    assert config.retries["total_max_attempts"] == 1
    assert config.proxies == {}
    client.get_queue_url.assert_called_once_with(QueueName=queue_name)
    client.receive_message.assert_called_once_with(
        QueueUrl=normalized_queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=10,
        VisibilityTimeout=120,
    )
    client.delete_message.assert_not_called()


def test_invalid_endpoint_is_rejected_before_session_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(local_sqs_consumer.boto3, "Session", session_factory)

    with pytest.raises(ValueError, match="endpoint_url"):
        LocalSqsConsumer("https://aws.example", "sync")

    session_factory.assert_not_called()


def test_invalid_kind_is_rejected_before_session_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(local_sqs_consumer.boto3, "Session", session_factory)

    with pytest.raises(ValueError, match="kind"):
        LocalSqsConsumer("http://127.0.0.1:4566", "other")

    session_factory.assert_not_called()


_EVAL_QUEUE = "fewia-eval-" + "ab" * 16


def test_receive_uses_override_queue_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    queue_url = f"http://127.0.0.1:4566/000000000000/{_EVAL_QUEUE}"
    client.get_queue_url.return_value = {"QueueUrl": queue_url}
    client.receive_message.return_value = {
        "Messages": [{"Body": "raw-job", "ReceiptHandle": "rh-1"}]
    }
    session_factory = _patch_client(monkeypatch, client)

    consumer = LocalSqsConsumer(
        "http://127.0.0.1:4566", "agent", queue_name=_EVAL_QUEUE
    )
    message = consumer.receive()

    assert message == QueueMessage(body="raw-job", receipt_handle="rh-1")
    session_factory.assert_called_once()
    client.get_queue_url.assert_called_once_with(QueueName=_EVAL_QUEUE)
    client.receive_message.assert_called_once_with(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=10,
        VisibilityTimeout=120,
    )


@pytest.mark.parametrize(
    "queue_name",
    [
        "fewia-agent",
        "fewia-eval-" + "AB" * 16,
        "fewia-eval-" + "a" * 31,
        "fewia-eval-" + "a" * 32 + "\n",
    ],
)
def test_invalid_queue_name_is_rejected_before_session_creation(
    monkeypatch: pytest.MonkeyPatch, queue_name: str
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(local_sqs_consumer.boto3, "Session", session_factory)

    with pytest.raises(ValueError, match="queue_name"):
        LocalSqsConsumer("http://127.0.0.1:4566", "agent", queue_name=queue_name)

    session_factory.assert_not_called()


@pytest.mark.parametrize(
    "queue_url",
    [
        "https://sqs.us-east-1.amazonaws.com/123/fewia-sync",
        "http://evil.example/000000000000/fewia-sync",
        "http://evil.example/queue/fewia-sync",
        "http://user@127.0.0.1:4566/queue/fewia-sync",
        "http://user:pass@127.0.0.1:4566/queue/fewia-sync",
        "http://127.0.0.1:4566/queue/fewia-sync?foo=1",
        "http://127.0.0.1:4566/queue/fewia-sync#frag",
        "https://127.0.0.1:4566/queue/fewia-sync",
        "http://127.0.0.1:4567/queue/fewia-sync",
        "http://127.0.0.1:4566.evil.example/queue/fewia-sync",
        "http://127.0.0.1:4566/00000000000/fewia-sync",
        "http://127.0.0.1:4566/000000000000/fewia-sync/extra",
        "http://127.0.0.1:4566/000000000000/fewia-sync/",
        "http://127.0.0.1:4566/000000000000/other",
        "http://127.0.0.1:4566/000000000000%2Ffewia-sync",
        "http://127.0.0.1:4566/000000000000/fewia-sync%2Fextra",
        "http://127.0.0.1:4566/000000000000/fewia-sync\\extra",
        "http://127.0.0.1:4566/000000000000/fewia-sync\nextra",
    ],
)
def test_disallowed_queue_url_is_rejected_before_receive(
    monkeypatch: pytest.MonkeyPatch, queue_url: str
) -> None:
    client = Mock()
    client.get_queue_url.return_value = {"QueueUrl": queue_url}
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")

    with pytest.raises(RuntimeError, match="queue URL"):
        consumer.receive()

    client.receive_message.assert_not_called()
    with pytest.raises(RuntimeError, match="queue URL"):
        consumer.acknowledge(QueueMessage("b", "rh"))
    client.delete_message.assert_not_called()
    client.change_message_visibility.assert_not_called()


@pytest.mark.parametrize("returned_endpoint_url", sorted(local_sqs.ALLOWED_ENDPOINTS))
@pytest.mark.parametrize("endpoint_url", sorted(local_sqs.ALLOWED_ENDPOINTS))
def test_normalizes_approved_queue_alias_for_all_operations(
    monkeypatch: pytest.MonkeyPatch,
    endpoint_url: str,
    returned_endpoint_url: str,
) -> None:
    client = Mock()
    returned_queue_url = _queue_url(returned_endpoint_url, "sync")
    normalized_queue_url = _queue_url(endpoint_url, "sync")
    client.get_queue_url.return_value = {"QueueUrl": returned_queue_url}
    client.receive_message.return_value = {
        "Messages": [{"Body": "raw-job", "ReceiptHandle": "rh-1"}]
    }
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer(endpoint_url, "sync")

    assert consumer.receive() == QueueMessage("raw-job", "rh-1")
    consumer.acknowledge(QueueMessage("raw-job", "rh-1"))
    consumer.extend(QueueMessage("raw-job", "rh-1"), 30)

    assert client.receive_message.call_args.kwargs["QueueUrl"] == normalized_queue_url
    assert client.delete_message.call_args.kwargs["QueueUrl"] == normalized_queue_url
    assert (
        client.change_message_visibility.call_args.kwargs["QueueUrl"]
        == normalized_queue_url
    )


def test_malformed_queue_url_error_does_not_expose_parser_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.get_queue_url.return_value = {"QueueUrl": "http://[sensitive-payload]/queue"}
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")

    with pytest.raises(RuntimeError, match="queue URL") as error:
        consumer.receive()

    assert "sensitive-payload" not in str(error.value)
    assert error.value.__cause__ is None
    client.receive_message.assert_not_called()


def test_empty_receipt_is_rejected_before_acknowledge_or_extend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.get_queue_url.return_value = {
        "QueueUrl": "http://127.0.0.1:4566/000000000000/fewia-sync"
    }
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")
    message = QueueMessage("raw-job", "")

    with pytest.raises(ValueError, match="receipt_handle"):
        consumer.acknowledge(message)
    with pytest.raises(ValueError, match="receipt_handle"):
        consumer.extend(message, 30)

    client.get_queue_url.assert_not_called()
    client.delete_message.assert_not_called()
    client.change_message_visibility.assert_not_called()


def test_receive_returns_none_for_empty_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.get_queue_url.return_value = {
        "QueueUrl": "http://127.0.0.1:4566/000000000000/fewia-sync"
    }
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")

    client.receive_message.return_value = {}
    assert consumer.receive() is None
    client.receive_message.return_value = {"Messages": []}
    assert consumer.receive() is None
    client.delete_message.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        ["Messages"],
        {"Messages": {"Body": "x"}},
        {"Messages": [{"Body": "a", "ReceiptHandle": "r"}, {"Body": "b"}]},
        {"Messages": ["x"]},
        {"Messages": [{"ReceiptHandle": "r"}]},
        {"Messages": [{"Body": "a"}]},
        {"Messages": [{"Body": 1, "ReceiptHandle": "r"}]},
        {"Messages": [{"Body": "a", "ReceiptHandle": None}]},
        {"Messages": [{"Body": "a", "ReceiptHandle": ""}]},
        {"Messages": None},
    ],
)
def test_malformed_receive_shapes_fail_without_delete(
    monkeypatch: pytest.MonkeyPatch, response: object
) -> None:
    client = Mock()
    client.get_queue_url.return_value = {
        "QueueUrl": "http://127.0.0.1:4566/000000000000/fewia-sync"
    }
    client.receive_message.return_value = response
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")

    with pytest.raises(RuntimeError, match="SQS receive"):
        consumer.receive()

    client.delete_message.assert_not_called()
    client.change_message_visibility.assert_not_called()


def test_acknowledge_deletes_with_receipt_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    queue_url = "http://127.0.0.1:4566/000000000000/fewia-sync"
    client.get_queue_url.return_value = {"QueueUrl": queue_url}
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")

    consumer.acknowledge(QueueMessage(body="raw-job", receipt_handle="rh-1"))

    client.delete_message.assert_called_once_with(
        QueueUrl=queue_url, ReceiptHandle="rh-1"
    )


@pytest.mark.parametrize("seconds", [0, 43200])
def test_extend_accepts_visibility_bounds(
    monkeypatch: pytest.MonkeyPatch, seconds: int
) -> None:
    client = Mock()
    queue_url = "http://127.0.0.1:4566/000000000000/fewia-sync"
    client.get_queue_url.return_value = {"QueueUrl": queue_url}
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")
    message = QueueMessage(body="raw-job", receipt_handle="rh-1")

    consumer.extend(message, seconds)

    client.change_message_visibility.assert_called_once_with(
        QueueUrl=queue_url,
        ReceiptHandle="rh-1",
        VisibilityTimeout=seconds,
    )
    client.delete_message.assert_not_called()


@pytest.mark.parametrize("seconds", [True, False, -1, 43201])
def test_extend_rejects_non_integer_and_out_of_range(
    monkeypatch: pytest.MonkeyPatch, seconds: object
) -> None:
    client = Mock()
    client.get_queue_url.return_value = {
        "QueueUrl": "http://127.0.0.1:4566/000000000000/fewia-sync"
    }
    _patch_client(monkeypatch, client)
    consumer = LocalSqsConsumer("http://127.0.0.1:4566", "sync")

    with pytest.raises(ValueError, match="seconds"):
        consumer.extend(QueueMessage("raw-job", "rh-1"), seconds)  # type: ignore[arg-type]

    client.get_queue_url.assert_not_called()
    client.change_message_visibility.assert_not_called()
    client.delete_message.assert_not_called()
