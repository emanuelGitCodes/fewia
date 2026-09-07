"""Receive local Floci SQS messages for worker transport."""

import re
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import urlsplit

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from app.providers.local_sqs import ALLOWED_ENDPOINTS, QUEUE_NAMES

_WAIT_TIME_SECONDS = 10
_VISIBILITY_TIMEOUT = 120
_MAX_VISIBILITY_SECONDS = 43200


class SqsConsumerClient(Protocol):
    def get_queue_url(self, *, QueueName: str) -> dict[str, object]: ...
    def receive_message(self, **kwargs: object) -> dict[str, object]: ...
    def delete_message(self, **kwargs: object) -> dict[str, object]: ...
    def change_message_visibility(self, **kwargs: object) -> dict[str, object]: ...


@dataclass(frozen=True)
class QueueMessage:
    body: str
    receipt_handle: str


def _normalize_queue_url(
    queue_url: str, endpoint_url: str, queue_name: str
) -> str | None:
    if any(ord(char) < 32 or ord(char) == 127 for char in queue_url):
        return None
    if any(char in queue_url for char in ("\\", "%", "?", "#")):
        return None
    try:
        parts = urlsplit(queue_url)
    except ValueError:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in ALLOWED_ENDPOINTS or not re.fullmatch(
        rf"/[0-9]{{12}}/{re.escape(queue_name)}", parts.path
    ):
        return None
    return endpoint_url + parts.path


class LocalSqsConsumer:
    """Receive, extend, and acknowledge one local SQS message."""

    def __init__(self, endpoint_url: str, kind: str) -> None:
        if endpoint_url not in ALLOWED_ENDPOINTS:
            raise ValueError("endpoint_url MUST target the local Floci service")
        self._endpoint_url = endpoint_url
        queue_name = QUEUE_NAMES.get(kind)
        if queue_name is None:
            raise ValueError("kind MUST be sync or agent")
        self._queue_name = queue_name
        session = boto3.Session(
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        )
        self._client = cast(
            SqsConsumerClient,
            session.client(
                "sqs",
                endpoint_url=endpoint_url,
                config=Config(
                    connect_timeout=3,
                    read_timeout=20,
                    retries={"total_max_attempts": 1},
                ),
            ),
        )

    def _queue_url(self) -> str:
        response = self._client.get_queue_url(QueueName=self._queue_name)
        if not isinstance(response, dict):
            raise RuntimeError("SQS queue URL response is invalid")
        queue_url = response.get("QueueUrl")
        if not isinstance(queue_url, str):
            raise RuntimeError("SQS queue URL response is invalid")
        normalized_url = _normalize_queue_url(
            queue_url, self._endpoint_url, self._queue_name
        )
        if normalized_url is None:
            raise RuntimeError("SQS queue URL response is invalid")
        return normalized_url

    def receive(self) -> QueueMessage | None:
        queue_url = self._queue_url()
        response = self._client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=_WAIT_TIME_SECONDS,
            VisibilityTimeout=_VISIBILITY_TIMEOUT,
        )
        if not isinstance(response, dict):
            raise RuntimeError("SQS receive response is invalid")
        if "Messages" not in response:
            return None
        messages = response["Messages"]
        if not isinstance(messages, list):
            raise RuntimeError("SQS receive message list is invalid")
        if len(messages) == 0:
            return None
        if len(messages) != 1:
            raise RuntimeError("SQS receive message list is invalid")
        message = messages[0]
        if not isinstance(message, dict):
            raise RuntimeError("SQS receive message is invalid")
        body = message.get("Body")
        receipt_handle = message.get("ReceiptHandle")
        if (
            not isinstance(body, str)
            or not isinstance(receipt_handle, str)
            or not receipt_handle
        ):
            raise RuntimeError("SQS receive message fields are invalid")
        return QueueMessage(body=body, receipt_handle=receipt_handle)

    def acknowledge(self, message: QueueMessage) -> None:
        if not message.receipt_handle:
            raise ValueError("receipt_handle MUST be nonempty")
        queue_url = self._queue_url()
        self._client.delete_message(
            QueueUrl=queue_url, ReceiptHandle=message.receipt_handle
        )

    def extend(self, message: QueueMessage, seconds: int) -> None:
        if (
            isinstance(seconds, bool)
            or type(seconds) is not int
            or seconds < 0
            or seconds > _MAX_VISIBILITY_SECONDS
        ):
            raise ValueError("seconds MUST be an integer from 0 to 43200")
        if not message.receipt_handle:
            raise ValueError("receipt_handle MUST be nonempty")
        queue_url = self._queue_url()
        self._client.change_message_visibility(
            QueueUrl=queue_url,
            ReceiptHandle=message.receipt_handle,
            VisibilityTimeout=seconds,
        )
