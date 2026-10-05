"""Create a private local Floci queue for one evaluation run."""

from typing import Protocol, cast
from uuid import uuid4

import boto3  # type: ignore[import-untyped]

from app.providers.aws_config import aws_client_config
from app.providers.local_sqs import ALLOWED_ENDPOINTS, LocalSqsSender
from app.providers.local_sqs_consumer import LocalSqsConsumer, _normalize_queue_url


class IsolatedSqsClient(Protocol):
    def create_queue(self, *, QueueName: str) -> dict[str, object]: ...

    def get_queue_url(self, *, QueueName: str) -> dict[str, object]: ...

    def delete_queue(self, *, QueueUrl: str) -> object: ...


class IsolatedLocalQueue:
    """Hold one private evaluation queue until close."""

    def __init__(self, endpoint_url: str) -> None:
        if endpoint_url not in ALLOWED_ENDPOINTS:
            raise ValueError("endpoint_url MUST target the local Floci service")
        self.name = f"fewia-eval-{uuid4().hex}"
        session = boto3.Session(
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        )
        self._client = cast(
            IsolatedSqsClient,
            session.client(
                "sqs",
                endpoint_url=endpoint_url,
                config=aws_client_config(5, local=True),
            ),
        )
        self.sender = LocalSqsSender(endpoint_url, queue_name=self.name)
        self.consumer = LocalSqsConsumer(endpoint_url, "agent", queue_name=self.name)
        response = self._client.create_queue(QueueName=self.name)
        queue_url = response.get("QueueUrl")
        normalized = (
            _normalize_queue_url(queue_url, endpoint_url, self.name)
            if isinstance(queue_url, str)
            else None
        )
        if normalized is None:
            try:
                lookup = self._client.get_queue_url(QueueName=self.name)
                lookup_url = lookup.get("QueueUrl")
                lookup_normalized = (
                    _normalize_queue_url(lookup_url, endpoint_url, self.name)
                    if isinstance(lookup_url, str)
                    else None
                )
                if lookup_normalized is not None:
                    self._client.delete_queue(QueueUrl=lookup_normalized)
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError("SQS queue URL response is invalid")
        self._queue_url = normalized
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._client.delete_queue(QueueUrl=self._queue_url)
