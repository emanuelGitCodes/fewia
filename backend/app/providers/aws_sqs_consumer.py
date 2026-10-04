"""Receive SQS jobs through ambient task-role credentials."""

from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]

from app.providers.aws_config import aws_client_config
from app.providers.aws_sqs_sender import validate_queue_url
from app.providers.local_sqs_consumer import QueueMessage


class SqsConsumerClient(Protocol):
    def receive_message(
        self,
        *,
        QueueUrl: str,
        MaxNumberOfMessages: int,
        WaitTimeSeconds: int,
        VisibilityTimeout: int,
    ) -> dict[str, object]: ...
    def delete_message(
        self, *, QueueUrl: str, ReceiptHandle: str
    ) -> dict[str, object]: ...
    def change_message_visibility(
        self, *, QueueUrl: str, ReceiptHandle: str, VisibilityTimeout: int
    ) -> dict[str, object]: ...


def _receipt_handle(message: QueueMessage) -> str:
    if (
        not isinstance(message, QueueMessage)
        or type(message.receipt_handle) is not str
        or not message.receipt_handle
    ):
        raise ValueError(
            "message MUST be a QueueMessage with a nonempty string receipt"
        )
    return message.receipt_handle


class AwsSqsConsumer:
    def __init__(
        self,
        region: str,
        queue_url: str,
        client: SqsConsumerClient | None = None,
    ) -> None:
        self._queue_url = validate_queue_url(region, queue_url)
        if client is not None:
            self._client = client
            return
        try:
            session = boto3.Session()
            self._client = cast(
                SqsConsumerClient,
                session.client(
                    "sqs",
                    region_name=region,
                    endpoint_url=f"https://sqs.{region}.amazonaws.com",
                    config=aws_client_config(20, local=False),
                ),
            )
        except Exception:  # noqa: BLE001
            raise RuntimeError("SQS client initialization failed") from None

    def receive(self) -> QueueMessage | None:
        try:
            response = self._client.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10,
                VisibilityTimeout=120,
            )
        except Exception:  # noqa: BLE001
            raise RuntimeError("SQS receive failed") from None
        if not isinstance(response, dict):
            raise RuntimeError("SQS receive response is invalid")
        if "Messages" not in response:
            return None
        messages = response["Messages"]
        if not isinstance(messages, list) or len(messages) > 1:
            raise RuntimeError("SQS receive response is invalid")
        if not messages:
            return None
        message = messages[0]
        if not isinstance(message, dict):
            raise RuntimeError("SQS receive response is invalid")
        body = message.get("Body")
        receipt = message.get("ReceiptHandle")
        if not isinstance(body, str) or type(receipt) is not str or not receipt:
            raise RuntimeError("SQS receive response is invalid")
        return QueueMessage(body=body, receipt_handle=receipt)

    def acknowledge(self, message: QueueMessage) -> None:
        receipt = _receipt_handle(message)
        try:
            self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt)
        except Exception:  # noqa: BLE001
            raise RuntimeError("SQS acknowledge failed") from None

    def extend(self, message: QueueMessage, seconds: int) -> None:
        receipt = _receipt_handle(message)
        if type(seconds) is not int or seconds < 0 or seconds > 43200:
            raise ValueError("seconds MUST be an integer from 0 to 43200")
        try:
            self._client.change_message_visibility(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt,
                VisibilityTimeout=seconds,
            )
        except Exception:  # noqa: BLE001
            raise RuntimeError("SQS extend failed") from None
