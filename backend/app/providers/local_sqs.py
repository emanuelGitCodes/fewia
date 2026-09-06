"""Send durable job identifiers to local Floci SQS queues."""

import json
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

ALLOWED_ENDPOINTS = frozenset(
    {"http://127.0.0.1:4566", "http://localhost:4566", "http://floci:4566"}
)
QUEUE_NAMES = {"sync": "fewia-sync", "agent": "fewia-agent"}


class SqsClient(Protocol):
    def get_queue_url(self, *, QueueName: str) -> dict[str, object]: ...

    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, object]: ...


class LocalSqsSender:
    """Send one job message through a local SQS endpoint."""

    def __init__(self, endpoint_url: str) -> None:
        if endpoint_url not in ALLOWED_ENDPOINTS:
            raise ValueError("endpoint_url MUST target the local Floci service")
        session = boto3.Session(
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        )
        self._client = cast(
            SqsClient,
            session.client(
                "sqs",
                endpoint_url=endpoint_url,
                config=Config(
                    connect_timeout=3,
                    read_timeout=5,
                    retries={"total_max_attempts": 1},
                ),
            ),
        )

    def send(self, kind: str, job_id: str) -> None:
        queue_name = QUEUE_NAMES.get(kind)
        if queue_name is None:
            raise ValueError("kind MUST be sync or agent")
        response = self._client.get_queue_url(QueueName=queue_name)
        queue_url = response.get("QueueUrl")
        if not isinstance(queue_url, str):
            raise RuntimeError("SQS queue URL response is invalid")
        self._client.send_message(
            QueueUrl=queue_url, MessageBody=json.dumps({"job_id": job_id})
        )
