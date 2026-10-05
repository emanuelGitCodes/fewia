"""Test the private local evaluation queue."""

import re
from unittest.mock import Mock

import pytest

from app.providers import local_sqs, local_sqs_consumer, local_sqs_isolated
from app.providers.local_sqs import LocalSqsSender
from app.providers.local_sqs_consumer import LocalSqsConsumer
from app.providers.local_sqs_isolated import IsolatedLocalQueue

_ENDPOINT = "http://127.0.0.1:4566"
_EVAL_NAME = re.compile(r"fewia-eval-[0-9a-f]{32}")


def _patch_sessions(monkeypatch: pytest.MonkeyPatch, client: Mock) -> Mock:
    session = Mock()
    session.client.return_value = client
    session_factory = Mock(return_value=session)
    monkeypatch.setattr(local_sqs_isolated.boto3, "Session", session_factory)
    monkeypatch.setattr(local_sqs.boto3, "Session", session_factory)
    monkeypatch.setattr(local_sqs_consumer.boto3, "Session", session_factory)
    return session_factory


def test_create_close_and_double_close(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()

    def create_queue(*, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"{_ENDPOINT}/000000000000/{QueueName}"}

    client.create_queue.side_effect = create_queue
    session_factory = _patch_sessions(monkeypatch, client)

    queue = IsolatedLocalQueue(_ENDPOINT)

    assert _EVAL_NAME.fullmatch(queue.name)
    assert isinstance(queue.sender, LocalSqsSender)
    assert isinstance(queue.consumer, LocalSqsConsumer)
    session_factory.assert_called_with(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    isolated_kwargs = session_factory.return_value.client.call_args_list[0].kwargs
    assert isolated_kwargs["endpoint_url"] == _ENDPOINT
    config = isolated_kwargs["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert config.proxies == {}
    client.create_queue.assert_called_once_with(QueueName=queue.name)
    queue.close()
    queue.close()
    client.delete_queue.assert_called_once_with(
        QueueUrl=f"{_ENDPOINT}/000000000000/{queue.name}"
    )


def test_invalid_endpoint_is_rejected_before_session_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(local_sqs_isolated.boto3, "Session", session_factory)

    with pytest.raises(ValueError, match="endpoint_url"):
        IsolatedLocalQueue("https://aws.example")

    session_factory.assert_not_called()


def test_create_queue_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.create_queue.side_effect = RuntimeError("floci-down")
    _patch_sessions(monkeypatch, client)

    with pytest.raises(RuntimeError, match="floci-down"):
        IsolatedLocalQueue(_ENDPOINT)

    client.delete_queue.assert_not_called()


def test_create_queue_agent_path_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.create_queue.return_value = {
        "QueueUrl": f"{_ENDPOINT}/000000000000/fewia-agent"
    }
    _patch_sessions(monkeypatch, client)

    with pytest.raises(RuntimeError, match="SQS queue URL response is invalid"):
        IsolatedLocalQueue(_ENDPOINT)

    client.delete_queue.assert_not_called()


def test_create_queue_foreign_origin_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()

    def create_queue(*, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"http://evil:4566/000000000000/{QueueName}"}

    client.create_queue.side_effect = create_queue
    _patch_sessions(monkeypatch, client)

    with pytest.raises(RuntimeError, match="SQS queue URL response is invalid"):
        IsolatedLocalQueue(_ENDPOINT)

    client.delete_queue.assert_not_called()


def test_invalid_create_queue_url_deletes_via_get_queue_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.create_queue.return_value = {
        "QueueUrl": f"{_ENDPOINT}/000000000000/fewia-agent"
    }

    def get_queue_url(*, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"http://localhost:4566/000000000000/{QueueName}"}

    client.get_queue_url.side_effect = get_queue_url
    _patch_sessions(monkeypatch, client)

    with pytest.raises(RuntimeError, match="SQS queue URL response is invalid"):
        IsolatedLocalQueue(_ENDPOINT)

    name = client.get_queue_url.call_args.kwargs["QueueName"]
    client.get_queue_url.assert_called_once_with(QueueName=name)
    client.delete_queue.assert_called_once_with(
        QueueUrl=f"{_ENDPOINT}/000000000000/{name}"
    )


def test_invalid_create_and_get_queue_url_skips_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.create_queue.return_value = {
        "QueueUrl": f"{_ENDPOINT}/000000000000/fewia-agent"
    }
    client.get_queue_url.return_value = {
        "QueueUrl": f"{_ENDPOINT}/000000000000/fewia-agent"
    }
    _patch_sessions(monkeypatch, client)

    with pytest.raises(RuntimeError, match="SQS queue URL response is invalid"):
        IsolatedLocalQueue(_ENDPOINT)

    client.delete_queue.assert_not_called()


def test_get_queue_url_error_does_not_replace_invalid_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    client.create_queue.return_value = {
        "QueueUrl": f"{_ENDPOINT}/000000000000/fewia-agent"
    }
    client.get_queue_url.side_effect = RuntimeError("lookup-failed")
    _patch_sessions(monkeypatch, client)

    with pytest.raises(RuntimeError, match="SQS queue URL response is invalid"):
        IsolatedLocalQueue(_ENDPOINT)

    client.delete_queue.assert_not_called()


def test_close_deletes_normalized_endpoint_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()

    def create_queue(*, QueueName: str) -> dict[str, str]:
        return {"QueueUrl": f"http://localhost:4566/000000000000/{QueueName}"}

    client.create_queue.side_effect = create_queue
    _patch_sessions(monkeypatch, client)

    queue = IsolatedLocalQueue(_ENDPOINT)
    queue.close()
    client.delete_queue.assert_called_once_with(
        QueueUrl=f"{_ENDPOINT}/000000000000/{queue.name}"
    )
