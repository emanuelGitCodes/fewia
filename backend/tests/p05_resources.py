"""Local PostgreSQL, SQS, and S3 fixtures for P05 integration tests."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from os import environ
from re import fullmatch
from typing import Protocol, cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.evidence_models import GroceryEvidence
from app.handoff_models import ShoppingHandoff
from app.job_models import Job, JobOutbox
from app.models import User
from app.providers.local_artifacts import LocalArtifactStore
from app.providers.local_sqs import ALLOWED_ENDPOINTS, LocalSqsSender
from app.providers.local_sqs_consumer import LocalSqsConsumer, _normalize_queue_url

_P05_DATABASE_URL = "FEWIA_P05_DATABASE_URL"
_P05_FLOCI_ENDPOINT = "FEWIA_P05_FLOCI_ENDPOINT"
_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})
_DRIVER = "postgresql+psycopg"
_URL_ERROR = "database URL MUST use PostgreSQL on localhost"
_RUN_ID = r"[0-9a-f]{32}"
_SCHEMA_NAME = r"p05_[0-9a-f]{32}"
_QUOTED_SCHEMA = r'"p05_[0-9a-f]{32}"'
_QUEUE_NAME = r"fewia-p05-[0-9a-f]{32}"
_ARTIFACT_KEY = r"evaluation/[0-9a-f]{64}\.json"
_EVAL_BUCKET = "fewia-eval"
_TIMEOUT_OPTIONS = "-c statement_timeout=10000 -c lock_timeout=3000"
_OWNED_MODELS = (User, Job, JobOutbox, GroceryEvidence, ShoppingHandoff)


class QueueAdminClient(Protocol):
    def create_queue(self, *, QueueName: str) -> dict[str, object]: ...

    def delete_queue(self, *, QueueUrl: str) -> dict[str, object]: ...

    def close(self) -> None: ...


class ObjectDeleteClient(Protocol):
    def delete_object(self, *, Bucket: str, Key: str) -> object: ...


@dataclass
class P05Resources:
    factory: sessionmaker[Session]
    sender: LocalSqsSender
    consumer: LocalSqsConsumer
    queue_url: str
    artifacts: LocalArtifactStore
    run_id: str
    owned_artifact_keys: list[str]


def _require_env() -> tuple[str, str]:
    database_url = environ.get(_P05_DATABASE_URL)
    endpoint = environ.get(_P05_FLOCI_ENDPOINT)
    if not database_url or not endpoint:
        pytest.skip(
            "FEWIA_P05_DATABASE_URL and FEWIA_P05_FLOCI_ENDPOINT MUST both be set"
        )
    return database_url, endpoint


def _validate_database_url(database_url: str) -> None:
    try:
        url = make_url(database_url)
    except Exception:
        raise ValueError(_URL_ERROR) from None
    if url.drivername != _DRIVER or url.host not in _LOCAL_HOSTS or url.query:
        raise ValueError(_URL_ERROR)


def _validate_floci_endpoint(endpoint: str) -> None:
    if endpoint not in ALLOWED_ENDPOINTS:
        raise ValueError("endpoint_url MUST target the local Floci service")


def _require_run_id(run_id: str) -> str:
    if fullmatch(_RUN_ID, run_id) is None:
        raise ValueError("run_id MUST be a UUID hex")
    return run_id


def _require_schema_name(schema_name: str) -> str:
    if fullmatch(_SCHEMA_NAME, schema_name) is None:
        raise ValueError("schema name MUST use a generated UUID")
    return schema_name


def _schema_name_for(run_id: str) -> str:
    return _require_schema_name(f"p05_{_require_run_id(run_id)}")


def _quote_schema(run_id: str) -> str:
    return f'"{_schema_name_for(run_id)}"'


def _require_quoted_schema(quoted_schema: str) -> str:
    if fullmatch(_QUOTED_SCHEMA, quoted_schema) is None:
        raise ValueError("schema name MUST use a generated UUID")
    return quoted_schema


def _queue_name_for(run_id: str) -> str:
    queue_name = f"fewia-p05-{_require_run_id(run_id)}"
    if fullmatch(_QUEUE_NAME, queue_name) is None:
        raise ValueError("queue name MUST use a generated UUID")
    return queue_name


def _owned_artifact_key(key: str) -> bool:
    return fullmatch(_ARTIFACT_KEY, key) is not None


def _owned_tables() -> list[Table]:
    tables = Base.metadata.tables
    return [tables[model.__tablename__] for model in _OWNED_MODELS]


def _connect_options(*, schema_name: str | None = None) -> str:
    if schema_name is None:
        return _TIMEOUT_OPTIONS
    name = _require_schema_name(schema_name)
    return f"-c search_path={name} {_TIMEOUT_OPTIONS}"


def _engine(database_url: str, *, schema_name: str | None = None) -> Engine:
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_timeout=3,
        connect_args={
            "connect_timeout": 3,
            "options": _connect_options(schema_name=schema_name),
        },
    )


def _create_schema(engine: Engine, quoted_schema: str) -> None:
    quoted = _require_quoted_schema(quoted_schema)
    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {quoted}"))


def _drop_schema(engine: Engine, quoted_schema: str) -> None:
    quoted = _require_quoted_schema(quoted_schema)
    with engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {quoted} CASCADE"))


def _close_if_possible(client: object) -> None:
    closer = getattr(client, "close", None)
    if callable(closer):
        closer()


def _normalized_queue_url(response: object, endpoint: str, queue_name: str) -> str:
    if not isinstance(response, dict):
        raise RuntimeError("SQS queue URL response is invalid")
    queue_url = response.get("QueueUrl")
    if not isinstance(queue_url, str):
        raise RuntimeError("SQS queue URL response is invalid")
    normalized = _normalize_queue_url(queue_url, endpoint, queue_name)
    if normalized is None:
        raise RuntimeError("SQS queue URL response is invalid")
    return normalized


def _delete_owned_artifact_keys(store: LocalArtifactStore, keys: list[str]) -> None:
    client = cast(ObjectDeleteClient, store._client)
    with ExitStack() as stack:
        for key in tuple(keys):
            if not _owned_artifact_key(key):
                continue
            stack.callback(client.delete_object, Bucket=_EVAL_BUCKET, Key=key)


@contextmanager
def local_resources() -> Iterator[P05Resources]:
    """Yield one scoped P05 resource bundle."""
    database_url, endpoint = _require_env()
    _validate_database_url(database_url)
    _validate_floci_endpoint(endpoint)

    run_id = uuid4().hex
    schema_name = _schema_name_for(run_id)
    quoted_schema = _quote_schema(run_id)
    queue_name = _queue_name_for(run_id)

    with ExitStack() as stack:
        admin_engine = _engine(database_url)
        stack.callback(admin_engine.dispose)
        _create_schema(admin_engine, quoted_schema)
        stack.callback(_drop_schema, admin_engine, quoted_schema)
        scoped_engine = _engine(database_url, schema_name=schema_name)
        stack.callback(scoped_engine.dispose)
        Base.metadata.create_all(bind=scoped_engine, tables=_owned_tables())

        sender = LocalSqsSender(endpoint)
        admin_client = cast(QueueAdminClient, sender._client)
        stack.callback(admin_client.close)
        created = admin_client.create_queue(QueueName=queue_name)
        queue_url = _normalized_queue_url(created, endpoint, queue_name)
        stack.callback(admin_client.delete_queue, QueueUrl=queue_url)

        consumer = LocalSqsConsumer(endpoint, "sync")
        consumer._queue_name = queue_name
        stack.callback(_close_if_possible, consumer._client)

        artifacts = LocalArtifactStore(endpoint)
        stack.callback(artifacts.close)
        owned_artifact_keys: list[str] = []
        stack.callback(_delete_owned_artifact_keys, artifacts, owned_artifact_keys)

        yield P05Resources(
            factory=sessionmaker(bind=scoped_engine, expire_on_commit=False),
            sender=sender,
            consumer=consumer,
            queue_url=queue_url,
            artifacts=artifacts,
            run_id=run_id,
            owned_artifact_keys=owned_artifact_keys,
        )
