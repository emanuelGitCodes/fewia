import base64
import copy
import hashlib
import traceback
from typing import cast

import pytest
from botocore.config import Config

from app.providers import aws_artifacts
from app.providers.aws_artifacts import AwsArtifactError, AwsArtifactStore
from app.providers.local_artifacts import ArtifactPut, S3Client

_BUCKET = "fewia-evaluation-123"
_OWNER = "123456789012"
_PRIVATE = "private-provider-error"


class FakeS3:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.close_calls = 0
        self.failure = failure

    def put_object(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        return {"ETag": "unused"}

    def close(self) -> None:
        self.close_calls += 1
        if self.failure is not None:
            raise self.failure


class FakeSession:
    def __init__(self, client: S3Client, failure: BaseException | None = None) -> None:
        self.client_obj = client
        self.failure = failure
        self.calls: list[tuple[str, dict[str, object]]] = []

    def client(self, service_name: str, **kwargs: object) -> S3Client:
        self.calls.append((service_name, kwargs))
        if self.failure is not None:
            raise self.failure
        return self.client_obj


class StringSubclass(str):
    pass


class DictSubclass(dict[str, object]):
    pass


class ListSubclass(list[object]):
    pass


def _store(client: S3Client, prefix: str = "evaluation") -> AwsArtifactStore:
    return AwsArtifactStore("us-east-1", _BUCKET, _OWNER, prefix, client)


def _unexpected(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("unexpected session creation")


def _assert_static(error: BaseException) -> None:
    assert str(error) == "AWS artifact store failed"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _PRIVATE not in repr(error)
    assert _PRIVATE not in "".join(traceback.format_exception(error))


def test_exact_payload_checksum_owner_encryption_and_replay() -> None:
    client = FakeS3()
    report = {"z": [None, True, 12, 1.5], "a": {"b": "é", "a": False}}
    original = copy.deepcopy(report)
    payload = b'{"a":{"a":false,"b":"\\u00e9"},"z":[null,true,12,1.5]}'
    digest = hashlib.sha256(payload)
    key = f"runs/Estimate_1/{digest.hexdigest()}.json"
    expected = {
        "Bucket": _BUCKET,
        "Key": key,
        "Body": payload,
        "ContentType": "application/json",
        "ServerSideEncryption": "AES256",
        "ExpectedBucketOwner": _OWNER,
        "ChecksumSHA256": base64.b64encode(digest.digest()).decode("ascii"),
    }
    store = _store(client, "runs/Estimate_1")

    first = store.put_report(report)
    second = store.put_report({"a": {"a": False, "b": "é"}, "z": [None, True, 12, 1.5]})

    assert first == second == ArtifactPut(key, digest.hexdigest())
    assert client.calls == [expected, expected]
    assert report == original


def test_default_prefix_and_shared_values() -> None:
    client = FakeS3()
    shared: dict[str, object] = {"estimate": True}
    result = _store(client).put_report({"a": shared, "b": shared})
    assert result.key == f"evaluation/{result.sha256}.json"
    assert client.calls[0]["Body"] == b'{"a":{"estimate":true},"b":{"estimate":true}}'
    assert shared == {"estimate": True}


@pytest.mark.parametrize(
    "report",
    [
        None,
        [],
        "private-payload",
        1,
        True,
        {"n": float("nan")},
        {"n": float("inf")},
        {"n": float("-inf")},
        {1: "private-payload"},
        {"nested": [{False: "private-payload"}]},
        {"x": (1, 2)},
        {"x": {1, 2}},
        {"x": b"private-payload"},
        {"x": object()},
        {"reasoningContent": "private-payload"},
        {"x": [{"reasoningContent": "private-payload"}]},
        DictSubclass({"x": 1}),
        {"x": ListSubclass([1])},
        {"x": StringSubclass("private-payload")},
        {StringSubclass("x"): 1},
    ],
)
def test_invalid_json_is_static_before_put(report: object) -> None:
    client = FakeS3()
    with pytest.raises(ValueError, match="^report is invalid$") as caught:
        _store(client).put_report(report)
    assert caught.value.__context__ is None
    assert "private-payload" not in "".join(traceback.format_exception(caught.value))
    assert client.calls == []


def test_cycles_and_excessive_depth_are_invalid_before_put() -> None:
    cycle: dict[str, object] = {}
    cycle["self"] = cycle
    items: list[object] = []
    items.append(items)
    deep: dict[str, object] = {}
    cursor = deep
    for _ in range(10_000):
        child: dict[str, object] = {}
        cursor["next"] = child
        cursor = child
    client = FakeS3()
    store = _store(client)
    for report in (cycle, {"items": items}, deep):
        with pytest.raises(ValueError, match="^report is invalid$"):
            store.put_report(report)
    assert client.calls == []
    assert cycle["self"] is cycle
    assert items[0] is items


def test_payload_cap_counts_canonical_bytes() -> None:
    client = FakeS3()
    store = _store(client)
    store.put_report({"x": "a" * (1_048_576 - 8)})
    body = client.calls[0]["Body"]
    assert isinstance(body, bytes)
    assert len(body) == 1_048_576
    for report in (
        {"x": "a" * (1_048_576 - 7)},
        {"x": "é" * 180_000},
    ):
        with pytest.raises(ValueError, match="^report is invalid$"):
            store.put_report(report)
    assert len(client.calls) == 1


@pytest.mark.parametrize("injected", [False, True])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("region", "eu-west-1"),
        ("region", "us-east-1\n"),
        ("region", StringSubclass("us-east-1")),
        ("region", None),
        ("bucket", "ab"),
        ("bucket", "a" * 64),
        ("bucket", "Upper-case"),
        ("bucket", "bucket_name"),
        ("bucket", "évaluation"),
        ("bucket", "-bucket"),
        ("bucket", "bucket-"),
        ("bucket", "bucket\n"),
        ("bucket", "bucket.name"),
        ("bucket", "192.168.0.1"),
        ("bucket", "arn:aws:s3:::bucket"),
        ("bucket", "s3://bucket"),
        ("bucket", "xn--bucket"),
        ("bucket", "sthree-bucket"),
        ("bucket", "amzn-s3-demo-bucket"),
        ("bucket", "bucket-s3alias"),
        ("bucket", "bucket--ol-s3"),
        ("bucket", "bucket--x-s3"),
        ("bucket", "bucket--table-s3"),
        ("bucket", "bucket-an"),
        ("bucket", StringSubclass(_BUCKET)),
        ("bucket", None),
        ("expected_bucket_owner", "12345678901"),
        ("expected_bucket_owner", "1234567890123"),
        ("expected_bucket_owner", "１２３４５６７８９０１２"),
        ("expected_bucket_owner", "123456789012\n"),
        ("expected_bucket_owner", StringSubclass(_OWNER)),
        ("expected_bucket_owner", 123456789012),
        ("prefix", ""),
        ("prefix", "a" * 129),
        ("prefix", "/evaluation"),
        ("prefix", "evaluation/"),
        ("prefix", "evaluation//run"),
        ("prefix", "evaluation/../run"),
        ("prefix", "evaluation/./run"),
        ("prefix", "evaluation%2Frun"),
        ("prefix", "evaluation\\run"),
        ("prefix", "evaluation\n"),
        ("prefix", "evaluation\x00"),
        ("prefix", "evaluation run"),
        ("prefix", "évaluation"),
        ("prefix", StringSubclass("evaluation")),
        ("prefix", None),
    ],
)
def test_invalid_configuration_precedes_any_client(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, injected: bool
) -> None:
    monkeypatch.setattr(aws_artifacts.boto3, "Session", _unexpected)
    kwargs = {
        "region": "us-east-1",
        "bucket": _BUCKET,
        "expected_bucket_owner": _OWNER,
        "prefix": "evaluation",
    }
    kwargs[field] = cast(str, value)
    client = FakeS3()
    with pytest.raises(ValueError) as caught:
        AwsArtifactStore(**kwargs, client=client if injected else None)
    assert "private" not in str(caught.value)
    assert client.calls == []


@pytest.mark.parametrize("bucket", ["a0z", "a" * 63, "123", "a--b"])
@pytest.mark.parametrize("prefix", ["a", "a" * 128, "A_0-/b"])
def test_valid_configuration_boundaries_stay_offline(
    monkeypatch: pytest.MonkeyPatch, bucket: str, prefix: str
) -> None:
    monkeypatch.setattr(aws_artifacts.boto3, "Session", _unexpected)
    client = FakeS3()
    store = AwsArtifactStore("us-west-2", bucket, "000000000000", prefix, client)
    store.put_report({})
    assert client.calls[0]["Bucket"] == bucket
    assert client.calls[0]["ExpectedBucketOwner"] == "000000000000"
    assert cast(str, client.calls[0]["Key"]).startswith(f"{prefix}/")
    store.close()
    assert client.close_calls == 0


@pytest.mark.parametrize("region", ["us-east-1", "us-west-2"])
def test_ambient_session_pinned_endpoint_timeouts_and_owned_close(
    monkeypatch: pytest.MonkeyPatch, region: str
) -> None:
    client = FakeS3()
    session = FakeSession(client)
    factory_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def factory(*args: object, **kwargs: object) -> FakeSession:
        factory_calls.append((args, kwargs))
        return session

    monkeypatch.setattr(aws_artifacts.boto3, "Session", factory)
    store = AwsArtifactStore(region, _BUCKET, _OWNER)
    assert factory_calls == [((), {})]
    assert len(session.calls) == 1
    service, kwargs = session.calls[0]
    assert service == "s3"
    assert set(kwargs) == {"region_name", "endpoint_url", "config"}
    assert kwargs["region_name"] == region
    assert kwargs["endpoint_url"] == f"https://s3.{region}.amazonaws.com"
    config = kwargs["config"]
    assert isinstance(config, Config)
    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries == {"total_max_attempts": 1}
    assert config.proxies is None
    assert client.calls == []
    store.close()
    assert client.close_calls == 1


@pytest.mark.parametrize("stage", ["session", "client", "put", "close"])
def test_provider_errors_are_static_without_retry(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    failure = RuntimeError(_PRIVATE)
    client = FakeS3(failure if stage in {"put", "close"} else None)
    session = FakeSession(client, failure if stage == "client" else None)
    factory_calls = 0

    def factory() -> FakeSession:
        nonlocal factory_calls
        factory_calls += 1
        if stage == "session":
            raise failure
        return session

    monkeypatch.setattr(aws_artifacts.boto3, "Session", factory)
    with pytest.raises(AwsArtifactError) as caught:
        store = AwsArtifactStore("us-east-1", _BUCKET, _OWNER)
        if stage == "put":
            store.put_report({"estimated": True})
        elif stage == "close":
            store.close()
    _assert_static(caught.value)
    assert factory_calls == 1
    assert len(session.calls) == (0 if stage == "session" else 1)
    assert len(client.calls) == (1 if stage == "put" else 0)
    assert client.close_calls == (1 if stage == "close" else 0)


@pytest.mark.parametrize("stage", ["session", "client", "put", "close"])
@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_interrupts_propagate(
    monkeypatch: pytest.MonkeyPatch, stage: str, interrupt: type[BaseException]
) -> None:
    failure = interrupt()
    client = FakeS3(failure if stage in {"put", "close"} else None)
    session = FakeSession(client, failure if stage == "client" else None)

    def factory() -> FakeSession:
        if stage == "session":
            raise failure
        return session

    monkeypatch.setattr(aws_artifacts.boto3, "Session", factory)
    with pytest.raises(interrupt) as caught:
        store = AwsArtifactStore("us-east-1", _BUCKET, _OWNER)
        if stage == "put":
            store.put_report({})
        elif stage == "close":
            store.close()
    assert caught.value is failure


def test_close_skips_owned_client_without_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoCloseS3:
        def put_object(self, **kwargs: object) -> object:
            return kwargs

    session = FakeSession(NoCloseS3())

    def factory() -> FakeSession:
        return session

    monkeypatch.setattr(aws_artifacts.boto3, "Session", factory)
    store = AwsArtifactStore("us-east-1", _BUCKET, _OWNER)
    store.close()


def test_close_never_accesses_injected_client_lifecycle() -> None:
    class InjectedS3:
        def put_object(self, **kwargs: object) -> object:
            return kwargs

        @property
        def close(self) -> object:
            raise AssertionError("injected client lifecycle was accessed")

    _store(InjectedS3()).close()
