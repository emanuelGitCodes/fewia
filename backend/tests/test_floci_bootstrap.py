import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from infra.floci_bootstrap import bootstrap  # noqa: E402


class FakeSqs:
    def __init__(self) -> None:
        self.urls: dict[str, str] = {}
        self.attributes: dict[str, dict[str, str]] = {}
        self.create_calls: list[str] = []

    def create_queue(self, *, QueueName: str) -> dict[str, str]:
        self.create_calls.append(QueueName)
        url = self.urls.setdefault(QueueName, f"http://floci/queue/{QueueName}")
        return {"QueueUrl": url}

    def get_queue_attributes(
        self, *, QueueUrl: str, AttributeNames: list[str]
    ) -> dict[str, dict[str, str]]:
        assert AttributeNames == ["QueueArn"]
        name = QueueUrl.rsplit("/", maxsplit=1)[-1]
        return {"Attributes": {"QueueArn": f"arn:aws:sqs:local:000000000000:{name}"}}

    def set_queue_attributes(
        self, *, QueueUrl: str, Attributes: dict[str, str]
    ) -> None:
        self.attributes[QueueUrl] = Attributes


class FakeS3:
    def __init__(self, existing_error: str = "BucketAlreadyOwnedByYou") -> None:
        self.buckets: set[str] = set()
        self.existing_error = existing_error

    def create_bucket(self, *, Bucket: str) -> None:
        if Bucket in self.buckets:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": self.existing_error}}, "CreateBucket")
        self.buckets.add(Bucket)


class FakeSession:
    def __init__(self, bucket_error: str = "BucketAlreadyOwnedByYou") -> None:
        self.sqs = FakeSqs()
        self.s3 = FakeS3(bucket_error)
        self.clients: list[tuple[str, str]] = []

    def client(self, service_name: str, *, endpoint_url: str) -> FakeSqs | FakeS3:
        self.clients.append((service_name, endpoint_url))
        return self.sqs if service_name == "sqs" else self.s3


def test_bootstrap_creates_resources_and_redrive_policies() -> None:
    session = FakeSession()

    result = bootstrap("http://floci:4566", session=session)

    assert result == {
        "sync_queue_url": "http://floci/queue/fewia-sync",
        "agent_queue_url": "http://floci/queue/fewia-agent",
        "artifact_bucket": "fewia-eval",
    }
    assert session.clients == [
        ("sqs", "http://floci:4566"),
        ("s3", "http://floci:4566"),
    ]
    assert session.sqs.create_calls == [
        "fewia-sync-dlq",
        "fewia-sync",
        "fewia-agent-dlq",
        "fewia-agent",
    ]
    for queue_name in ("fewia-sync", "fewia-agent"):
        policy = json.loads(
            session.sqs.attributes[f"http://floci/queue/{queue_name}"]["RedrivePolicy"]
        )
        assert policy == {
            "deadLetterTargetArn": f"arn:aws:sqs:local:000000000000:{queue_name}-dlq",
            "maxReceiveCount": "3",
        }
        assert (
            session.sqs.attributes[f"http://floci/queue/{queue_name}"][
                "VisibilityTimeout"
            ]
            == "120"
        )


def test_bootstrap_is_idempotent_with_existing_bucket_and_queues() -> None:
    session = FakeSession()

    first = bootstrap("http://floci:4566", session=session)
    second = bootstrap("http://floci:4566", session=session)

    assert second == first
    assert session.s3.buckets == {"fewia-eval"}
    assert set(session.sqs.urls) == {
        "fewia-sync-dlq",
        "fewia-sync",
        "fewia-agent-dlq",
        "fewia-agent",
    }
    assert len(session.sqs.attributes) == 2


def test_bootstrap_rejects_non_local_endpoint_before_client_creation() -> None:
    session = FakeSession()

    try:
        bootstrap("https://aws.example", session=session)
    except ValueError as error:
        assert str(error) == "endpoint_url MUST target the local Floci service"
    else:
        raise AssertionError("bootstrap accepted a non-local endpoint")
    assert session.clients == []


@pytest.mark.parametrize("error_code", ["AccessDenied", "BucketAlreadyExists"])
def test_bootstrap_propagates_unowned_bucket_errors(error_code: str) -> None:
    session = FakeSession(bucket_error=error_code)
    session.s3.buckets.add("fewia-eval")

    from botocore.exceptions import ClientError

    with pytest.raises(ClientError, match=error_code):
        bootstrap("http://localhost:4566", session=session)


def test_bootstrap_constructs_an_explicit_dummy_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def session_factory(**kwargs: str) -> FakeSession:
        captured.update(kwargs)
        return FakeSession()

    import infra.floci_bootstrap as module

    monkeypatch.setattr(module.boto3, "Session", session_factory)
    bootstrap("http://localhost:4566")

    assert captured == {
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
        "region_name": "us-east-1",
    }
