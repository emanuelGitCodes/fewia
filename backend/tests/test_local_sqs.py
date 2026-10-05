"""Test the local SQS sender contract."""

import json
from unittest.mock import Mock

import pytest

from app.providers import local_sqs
from app.providers.local_sqs import LocalSqsSender


def test_allowed_endpoints_match_the_shared_set() -> None:
    assert local_sqs.ALLOWED_ENDPOINTS == frozenset(
        {
            "http://127.0.0.1:4566",
            "http://localhost:4566",
            "http://floci:4566",
            "http://127.0.0.1:4567",
            "http://localhost:4567",
        }
    )


@pytest.mark.parametrize(
    ("kind", "queue_name"),
    [("sync", "fewia-sync"), ("agent", "fewia-agent")],
)
@pytest.mark.parametrize("endpoint_url", sorted(local_sqs.ALLOWED_ENDPOINTS))
def test_send_routes_kind_and_sends_only_the_job_id(
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    queue_name: str,
    endpoint_url: str,
) -> None:
    session = Mock()
    client = Mock()
    queue_url = f"{endpoint_url}/queue/{queue_name}"
    client.get_queue_url.return_value = {"QueueUrl": queue_url}
    session.client.return_value = client
    session_factory = Mock(return_value=session)
    monkeypatch.setattr(local_sqs.boto3, "Session", session_factory)

    sender = LocalSqsSender(endpoint_url)
    sender.send(kind, "job-123")

    session_factory.assert_called_once_with(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    session.client.assert_called_once()
    client_kwargs = session.client.call_args.kwargs
    assert client_kwargs["endpoint_url"] == endpoint_url
    config = client_kwargs["config"]
    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert config.proxies == {}
    client.get_queue_url.assert_called_once_with(QueueName=queue_name)
    client.send_message.assert_called_once_with(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"job_id": "job-123"}),
    )


def test_invalid_endpoint_is_rejected_before_session_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = Mock()
    monkeypatch.setattr(local_sqs.boto3, "Session", session_factory)

    with pytest.raises(ValueError, match="endpoint_url"):
        LocalSqsSender("https://aws.example")

    session_factory.assert_not_called()


def test_invalid_kind_is_rejected_before_queue_network_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock()
    client = Mock()
    session.client.return_value = client
    monkeypatch.setattr(local_sqs.boto3, "Session", Mock(return_value=session))

    sender = LocalSqsSender("http://127.0.0.1:4566")
    with pytest.raises(ValueError, match="kind"):
        sender.send("other", "job-123")

    client.get_queue_url.assert_not_called()
    client.send_message.assert_not_called()
