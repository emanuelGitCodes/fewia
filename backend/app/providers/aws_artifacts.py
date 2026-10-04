"""Put caller-sanitized JSON reports into task-role S3.

The caller MUST sanitize the report before put_report.
This adapter does not sanitize arbitrary data.
"""

import base64
import hashlib
import re
from typing import cast

import boto3  # type: ignore[import-untyped]

from app.evaluation_io_json import canonical_json_bytes
from app.providers.aws_config import aws_client_config
from app.providers.local_artifacts import ArtifactPut, S3Client

_REGIONS = frozenset({"us-east-1", "us-west-2"})
_RESERVED_PREFIXES = ("xn--", "sthree-", "amzn-s3-demo-")
_RESERVED_SUFFIXES = ("-s3alias", "--ol-s3", "--x-s3", "--table-s3", "-an")
_MAX_BYTES = 1_048_576


class AwsArtifactError(Exception):
    def __init__(self) -> None:
        super().__init__("AWS artifact store failed")


def _validate_config(region: str, bucket: str, owner: str, prefix: str) -> None:
    if type(region) is not str or region not in _REGIONS:
        raise ValueError("region MUST be us-east-1 or us-west-2")
    if (
        type(bucket) is not str
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket) is None
        or bucket.startswith(_RESERVED_PREFIXES)
        or bucket.endswith(_RESERVED_SUFFIXES)
    ):
        raise ValueError("bucket MUST be a standard S3 bucket name")
    if type(owner) is not str or re.fullmatch(r"[0-9]{12}", owner) is None:
        raise ValueError("expected_bucket_owner MUST contain 12 ASCII digits")
    if (
        type(prefix) is not str
        or not 1 <= len(prefix) <= 128
        or re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", prefix) is None
    ):
        raise ValueError("prefix MUST contain valid ASCII path segments")


def _encode_report(report: object) -> bytes:
    payload: bytes | None = None
    try:
        payload = canonical_json_bytes(report)
    except ValueError:
        pass
    if payload is None or len(payload) > _MAX_BYTES:
        raise ValueError("report is invalid") from None
    return payload


class AwsArtifactStore:
    def __init__(
        self,
        region: str,
        bucket: str,
        expected_bucket_owner: str,
        prefix: str = "evaluation",
        client: S3Client | None = None,
    ) -> None:
        _validate_config(region, bucket, expected_bucket_owner, prefix)
        self._bucket = bucket
        self._owner = expected_bucket_owner
        self._prefix = prefix
        self._owns_client = client is None
        if client is not None:
            self._client = client
            return
        error: AwsArtifactError | None = None
        try:
            session = boto3.Session()
            self._client = cast(
                S3Client,
                session.client(
                    "s3",
                    region_name=region,
                    endpoint_url=f"https://s3.{region}.amazonaws.com",
                    config=aws_client_config(5, local=False),
                ),
            )
        except Exception:  # noqa: BLE001
            error = AwsArtifactError()
        if error is not None:
            raise error from None

    def put_report(self, report: object) -> ArtifactPut:
        payload = _encode_report(report)
        digest = hashlib.sha256(payload)
        hex_digest = digest.hexdigest()
        key = f"{self._prefix}/{hex_digest}.json"
        error: AwsArtifactError | None = None
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=payload,
                ContentType="application/json",
                ServerSideEncryption="AES256",
                ExpectedBucketOwner=self._owner,
                ChecksumSHA256=base64.b64encode(digest.digest()).decode("ascii"),
            )
        except Exception:  # noqa: BLE001
            error = AwsArtifactError()
        if error is not None:
            raise error from None
        return ArtifactPut(key=key, sha256=hex_digest)

    def close(self) -> None:
        if not self._owns_client:
            return
        error: AwsArtifactError | None = None
        try:
            closer = getattr(self._client, "close", None)
            if callable(closer):
                closer()
        except Exception:  # noqa: BLE001
            error = AwsArtifactError()
        if error is not None:
            raise error from None
