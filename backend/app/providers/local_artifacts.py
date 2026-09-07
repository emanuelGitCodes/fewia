"""Put caller-sanitized JSON reports into local Floci S3.

The caller MUST sanitize the report before put_report.
This adapter does not sanitize arbitrary data.
"""

import hashlib
import json
from collections.abc import Callable
from typing import NamedTuple, Protocol, cast

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from app.providers.local_sqs import ALLOWED_ENDPOINTS

_BUCKET = "fewia-eval"
_MAX_BYTES = 1_048_576
_ATOMS = frozenset({bool, float, int, str, type(None)})
_FAILURE = "local artifact store failed"
_INVALID = "report is invalid"


class LocalArtifactError(Exception):
    def __init__(self) -> None:
        super().__init__(_FAILURE)


class ArtifactPut(NamedTuple):
    key: str
    sha256: str


class S3Client(Protocol):
    def put_object(self, **kwargs: object) -> object: ...


class BotoSession(Protocol):
    def client(self, service_name: str, **kwargs: object) -> S3Client: ...


def _reject_bad(value: object, seen: set[int]) -> None:
    ident = id(value)
    if ident in seen:
        raise ValueError(_INVALID)
    if isinstance(value, dict):
        seen.add(ident)
        for key, child in value.items():
            if type(key) is not str:
                raise ValueError(_INVALID)
            _reject_bad(child, seen)
        seen.discard(ident)
        return
    if isinstance(value, list):
        seen.add(ident)
        for child in value:
            _reject_bad(child, seen)
        seen.discard(ident)
        return
    if type(value) not in _ATOMS:
        raise ValueError(_INVALID)


def _encode_report(report: object) -> bytes:
    if not isinstance(report, dict):
        raise ValueError("report MUST be a JSON object")
    error: ValueError | None = None
    encoded: str | None = None
    try:
        _reject_bad(report, set())
        encoded = json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=True,
        )
    except (RecursionError, TypeError, ValueError):
        error = ValueError(_INVALID)
    if error is not None:
        raise error
    if encoded is None:
        raise ValueError(_INVALID)
    payload = encoded.encode("utf-8")
    if len(payload) > _MAX_BYTES:
        raise ValueError("report exceeds 1MiB")
    return payload


class LocalArtifactStore:
    """Put one JSON report into bucket fewia-eval."""

    def __init__(
        self,
        endpoint_url: str,
        *,
        session_factory: Callable[..., BotoSession] | None = None,
        client: S3Client | None = None,
    ) -> None:
        if endpoint_url not in ALLOWED_ENDPOINTS:
            raise ValueError("endpoint_url MUST target the local Floci service")
        self._owns_client = client is None
        if client is not None:
            self._client = client
            return
        factory = session_factory or cast(Callable[..., BotoSession], boto3.Session)
        session = factory(
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        )
        self._client = session.client(
            "s3",
            endpoint_url=endpoint_url,
            config=Config(
                connect_timeout=3,
                read_timeout=5,
                retries={"total_max_attempts": 1},
                proxies={},
            ),
        )

    def close(self) -> None:
        if not self._owns_client:
            return
        closer = getattr(self._client, "close", None)
        if callable(closer):
            closer()

    def put_report(self, report: object) -> ArtifactPut:
        payload = _encode_report(report)
        digest = hashlib.sha256(payload).hexdigest()
        key = f"evaluation/{digest}.json"
        error: LocalArtifactError | None = None
        try:
            self._client.put_object(
                Bucket=_BUCKET,
                Key=key,
                Body=payload,
                ContentType="application/json",
            )
        except Exception:
            error = LocalArtifactError()
        if error is not None:
            raise error
        return ArtifactPut(key=key, sha256=digest)
