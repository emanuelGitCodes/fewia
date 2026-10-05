"""Send durable job identifiers to local Floci SQS queues."""

import json
import re
from typing import Protocol, cast

import boto3  # type: ignore[import-untyped]

from app.providers.aws_config import aws_client_config

ALLOWED_ENDPOINTS = frozenset(
    {"http://127.0.0.1:4566", "http://localhost:4566", "http://floci:4566"}
)
QUEUE_NAMES = {"sync": "fewia-sync", "agent": "fewia-agent"}
_EVAL_QUEUE = re.compile(r"fewia-eval-[0-9a-f]{32}")


def _eval_queue_name(queue_name: str | None) -> str | None:
    if queue_name is None:
        return None
    if _EVAL_QUEUE.fullmatch(queue_name) is None:
        raise ValueError("queue_name MUST match fewia-eval-[0-9a-f]{32}")
    return queue_name


class SqsClient(Protocol):
    def get_queue_url(self, *, QueueName: str) -> dict[str, object]: ...

    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, object]: ...


class LocalSqsSender:
    """Send one job message through a local SQS endpoint."""

    def __init__(self, endpoint_url: str, *, queue_name: str | None = None) -> None:
        if endpoint_url not in ALLOWED_ENDPOINTS:
            raise ValueError("endpoint_url MUST target the local Floci service")
        self._queue_name = _eval_queue_name(queue_name)
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
                config=aws_client_config(5, local=True),
            ),
        )

    def send(self, kind: str, job_id: str) -> None:
        mapped = QUEUE_NAMES.get(kind)
        if mapped is None:
            raise ValueError("kind MUST be sync or agent")
        queue_name = self._queue_name if self._queue_name is not None else mapped
        response = self._client.get_queue_url(QueueName=queue_name)
        queue_url = response.get("QueueUrl")
        if not isinstance(queue_url, str):
            raise RuntimeError("SQS queue URL response is invalid")
        self._client.send_message(
            QueueUrl=queue_url, MessageBody=json.dumps({"job_id": job_id})
        )
