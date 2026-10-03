"""Send durable job identifiers through task-role SQS credentials."""

import json
import re
from typing import Protocol, cast
from uuid import UUID

import boto3  # type: ignore[import-untyped]

from app.providers.aws_config import aws_client_config

_ALLOWED_REGIONS = frozenset({"us-east-1", "us-west-2"})


class SqsClient(Protocol):
    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, object]: ...


def validate_queue_url(region: str, queue_url: str) -> str:
    if type(region) is not str or region not in _ALLOWED_REGIONS:
        raise ValueError("region MUST be us-east-1 or us-west-2")
    if (
        type(queue_url) is not str
        or re.fullmatch(
            rf"https://sqs\.{re.escape(region)}\.amazonaws\.com/"
            r"[0-9]{12}/[A-Za-z0-9_-]{1,80}",
            queue_url,
        )
        is None
    ):
        raise ValueError("queue_url MUST be a canonical standard SQS URL")
    return queue_url


class AwsSqsSender:
    def __init__(
        self,
        region: str,
        agent_queue_url: str,
        sync_queue_url: str,
        client: SqsClient | None = None,
    ) -> None:
        agent_url = validate_queue_url(region, agent_queue_url)
        sync_url = validate_queue_url(region, sync_queue_url)
        if agent_url == sync_url or agent_url.split("/")[3] != sync_url.split("/")[3]:
            raise ValueError("queues MUST differ and use the same account")
        self._queues = {"agent": agent_url, "sync": sync_url}
        if client is not None:
            self._client = client
            return
        try:
            session = boto3.Session()
            self._client = cast(
                SqsClient,
                session.client(
                    "sqs",
                    region_name=region,
                    endpoint_url=f"https://sqs.{region}.amazonaws.com",
                    config=aws_client_config(5, local=False),
                ),
            )
        except Exception:  # noqa: BLE001
            raise RuntimeError("SQS client initialization failed") from None

    def send(self, kind: str, job_id: str) -> None:
        if type(kind) is not str or kind not in self._queues:
            raise ValueError("kind MUST be agent or sync")
        if type(job_id) is not str or len(job_id) != 36:
            raise ValueError("job_id MUST be a canonical UUID")
        try:
            canonical_id = str(UUID(job_id))
        except ValueError:
            raise ValueError("job_id MUST be a canonical UUID") from None
        if canonical_id != job_id:
            raise ValueError("job_id MUST be a canonical UUID")
        try:
            self._client.send_message(
                QueueUrl=self._queues[kind],
                MessageBody=json.dumps({"job_id": job_id}),
            )
        except Exception:  # noqa: BLE001
            raise RuntimeError("SQS send failed") from None
