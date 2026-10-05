"""Create a private local Floci queue for one evaluation run."""

from typing import Protocol, cast
from uuid import uuid4

import boto3  # type: ignore[import-untyped]

from app.providers.aws_config import aws_client_config
from app.providers.local_sqs import ALLOWED_ENDPOINTS, LocalSqsSender
from app.providers.local_sqs_consumer import LocalSqsConsumer


class IsolatedSqsClient(Protocol):
    def create_queue(self, *, QueueName: str) -> dict[str, object]: ...

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
        self._closed = False
        response = self._client.create_queue(QueueName=self.name)
        queue_url = response.get("QueueUrl")
        if not isinstance(queue_url, str):
            raise RuntimeError("SQS queue URL response is invalid")
        self._queue_url = queue_url
        self.sender = LocalSqsSender(endpoint_url, queue_name=self.name)
        self.consumer = LocalSqsConsumer(endpoint_url, "agent", queue_name=self.name)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._client.delete_queue(QueueUrl=self._queue_url)
