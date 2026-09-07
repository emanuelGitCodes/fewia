"""Test the local Floci S3 JSON artifact adapter."""

import hashlib
import json

import pytest
from botocore.config import Config

from app.providers import local_sqs
from app.providers.local_artifacts import (
    ArtifactPut,
    LocalArtifactError,
    LocalArtifactStore,
)

_ENDPOINT = "http://127.0.0.1:4566"
_SECRET = "SECRET_S3_MARKER"


class FakeS3:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.closed = False

    def put_object(self, **kwargs: object) -> dict[str, str]:
        self.calls.append(kwargs)
        return {"ETag": "unused"}

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, client: FakeS3) -> None:
        self.client_obj = client
        self.client_calls: list[tuple[str, dict[str, object]]] = []

    def client(self, service_name: str, **kwargs: object) -> FakeS3:
        self.client_calls.append((service_name, kwargs))
        return self.client_obj


class BoomS3:
    def put_object(self, **kwargs: object) -> None:
        del kwargs
        raise RuntimeError(_SECRET)


class NoCloseS3:
    def put_object(self, **kwargs: object) -> dict[str, str]:
        return {"ok": "1"} if kwargs else {"ok": "0"}


def _canonical(report: dict[str, object]) -> bytes:
    return json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    ).encode("utf-8")


def test_put_report_uses_fixed_bucket_key_type_and_body_digest() -> None:
    client = FakeS3()
    report = {"b": 2, "a": True}
    store = LocalArtifactStore(_ENDPOINT, client=client)

    result = store.put_report(report)

    payload = _canonical(report)
    digest = hashlib.sha256(payload).hexdigest()
    assert result == ArtifactPut(key=f"evaluation/{digest}.json", sha256=digest)
    assert client.calls == [
        {
            "Bucket": "fewia-eval",
            "Key": f"evaluation/{digest}.json",
            "Body": payload,
            "ContentType": "application/json",
        }
    ]
    body = client.calls[0]["Body"]
    assert isinstance(body, bytes)
    assert hashlib.sha256(body).hexdigest() == digest


@pytest.mark.parametrize("endpoint_url", sorted(local_sqs.ALLOWED_ENDPOINTS))
def test_session_factory_uses_synthetic_credentials_and_retry_bounds(
    endpoint_url: str,
) -> None:
    captured: dict[str, object] = {}
    client = FakeS3()
    session = FakeSession(client)

    def factory(**kwargs: object) -> FakeSession:
        captured.update(kwargs)
        return session

    store = LocalArtifactStore(endpoint_url, session_factory=factory)
    store.put_report({"ok": 1})

    assert captured == {
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
        "region_name": "us-east-1",
    }
    assert len(session.client_calls) == 1
    service, kwargs = session.client_calls[0]
    assert service == "s3"
    assert kwargs["endpoint_url"] == endpoint_url
    config = kwargs["config"]
    assert isinstance(config, Config)
    assert config.connect_timeout == 3
    assert config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert config.proxies == {}
    assert client.calls[0]["Bucket"] == "fewia-eval"


def test_same_report_uses_the_same_key() -> None:
    client = FakeS3()
    store = LocalArtifactStore(_ENDPOINT, client=client)
    first = store.put_report({"z": [1], "a": "x"})
    second = store.put_report({"a": "x", "z": [1]})
    assert first == second
    assert first.key == f"evaluation/{first.sha256}.json"
    assert len(client.calls) == 2
    assert client.calls[0]["Key"] == client.calls[1]["Key"]


@pytest.mark.parametrize(
    "report",
    [
        [],
        "object",
        1,
        None,
        True,
        {"bad": object()},
        {"bin": b"x"},
        {"n": float("nan")},
        {"n": float("inf")},
        {"n": float("-inf")},
        {1: "a"},
        {"x": (1, 2)},
        {"blob": "a" * 1_048_576},
    ],
)
def test_invalid_report_does_not_call_s3(report: object) -> None:
    client = FakeS3()
    store = LocalArtifactStore(_ENDPOINT, client=client)
    with pytest.raises(ValueError):
        store.put_report(report)
    assert client.calls == []


def test_cycle_does_not_call_s3() -> None:
    client = FakeS3()
    store = LocalArtifactStore(_ENDPOINT, client=client)
    report: dict[str, object] = {}
    report["self"] = report
    with pytest.raises(ValueError, match="report is invalid"):
        store.put_report(report)
    assert client.calls == []


def test_invalid_endpoint_does_not_use_session_factory() -> None:
    created = {"n": 0}

    def factory(**kwargs: object) -> FakeSession:
        del kwargs
        created["n"] += 1
        return FakeSession(FakeS3())

    with pytest.raises(ValueError, match="endpoint_url"):
        LocalArtifactStore("https://s3.amazonaws.com", session_factory=factory)
    assert created["n"] == 0


def test_put_failure_is_static_and_hides_secret() -> None:
    store = LocalArtifactStore(_ENDPOINT, client=BoomS3())
    with pytest.raises(LocalArtifactError) as caught:
        store.put_report({"ok": True})
    error = caught.value
    notes = getattr(error, "__notes__", None)
    text = f"{error!s}{error!r}{error.__cause__}{error.__context__}{notes}"
    assert str(error) == "local artifact store failed"
    assert error.__cause__ is None
    assert error.__context__ is None
    assert _SECRET not in text


def test_close_releases_owned_client_when_supported() -> None:
    client = FakeS3()
    session = FakeSession(client)

    def factory(**kwargs: object) -> FakeSession:
        del kwargs
        return session

    store = LocalArtifactStore(_ENDPOINT, session_factory=factory)
    store.close()
    assert client.closed is True


def test_close_does_not_release_injected_client() -> None:
    client = FakeS3()
    store = LocalArtifactStore(_ENDPOINT, client=client)
    store.close()
    assert client.closed is False


def test_close_skips_owned_client_without_close() -> None:
    class Session:
        def client(self, service_name: str, **kwargs: object) -> NoCloseS3:
            del service_name, kwargs
            return NoCloseS3()

    def factory(**kwargs: object) -> Session:
        del kwargs
        return Session()

    store = LocalArtifactStore(_ENDPOINT, session_factory=factory)
    store.close()


def test_injected_client_ignores_session_factory() -> None:
    client = FakeS3()
    created = {"n": 0}

    def factory(**kwargs: object) -> FakeSession:
        del kwargs
        created["n"] += 1
        return FakeSession(FakeS3())

    store = LocalArtifactStore(_ENDPOINT, session_factory=factory, client=client)
    store.put_report({"k": None})
    assert created["n"] == 0
    assert len(client.calls) == 1
