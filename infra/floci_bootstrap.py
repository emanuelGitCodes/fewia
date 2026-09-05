import argparse
import json
from collections.abc import Callable
from typing import Any, Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

QUEUE_NAMES = ("fewia-sync", "fewia-agent")
ARTIFACT_BUCKET = "fewia-eval"
ALLOWED_ENDPOINTS = frozenset(
    {"http://127.0.0.1:4566", "http://localhost:4566", "http://floci:4566"}
)


class FlociClient(Protocol):
    def __getattr__(self, name: str) -> Callable[..., Any]: ...


class BotoSession(Protocol):
    def client(self, service_name: str, *, endpoint_url: str) -> FlociClient: ...


def _ensure_queue(sqs: FlociClient, name: str) -> str:
    dlq_url = sqs.create_queue(QueueName=f"{name}-dlq")["QueueUrl"]
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    queue_url = sqs.create_queue(QueueName=name)["QueueUrl"]
    sqs.set_queue_attributes(
        QueueUrl=queue_url,
        Attributes={
            "VisibilityTimeout": "120",
            "RedrivePolicy": json.dumps(
                {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}
            ),
        },
    )
    return cast(str, queue_url)


def bootstrap(
    endpoint_url: str, *, session: BotoSession | None = None
) -> dict[str, str]:
    if endpoint_url not in ALLOWED_ENDPOINTS:
        raise ValueError("endpoint_url MUST target the local Floci service")
    current: BotoSession = session or boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    sqs = current.client("sqs", endpoint_url=endpoint_url)
    s3 = current.client("s3", endpoint_url=endpoint_url)
    queues = [_ensure_queue(sqs, name) for name in QUEUE_NAMES]
    try:
        s3.create_bucket(Bucket=ARTIFACT_BUCKET)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if code != "BucketAlreadyOwnedByYou":
            raise
    return {
        "sync_queue_url": queues[0],
        "agent_queue_url": queues[1],
        "artifact_bucket": ARTIFACT_BUCKET,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create FEWIA Floci resources.")
    parser.add_argument(
        "--endpoint", "--endpoint-url", dest="endpoint_url", required=True
    )
    args = parser.parse_args()
    print(json.dumps(bootstrap(args.endpoint_url), sort_keys=True))


if __name__ == "__main__":
    main()
