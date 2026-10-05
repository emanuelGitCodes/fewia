import hashlib
import json
import os
import re
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Never, cast
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app import evaluation_duplicate as driver
from app.evaluation_database import FixtureDatabase, fixture_database
from app.evaluation_duplicate_handler import DuplicateHandler
from app.providers import local_sqs, local_sqs_consumer, local_sqs_isolated
from app.providers.local_artifacts import ArtifactPut
from app.providers.local_sqs_consumer import QueueMessage
from app.services.job_consumer import process_one
from app.services.job_delivery import JobQueue

ENDPOINT = "http://127.0.0.1:4566"
LOCAL_DATABASE = "postgresql+psycopg://localhost/fewia_eval"
MARKER = "synthetic-secret-marker"


class MemoryQueue:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.messages: list[QueueMessage] = []
        self.acknowledged: list[str] = []
        self.extended: list[str] = []
        self.drop_duplicate = False

    def send(self, kind: str, job_id: str) -> None:
        assert kind == "agent"
        self.sent.append(job_id)
        if self.drop_duplicate and len(self.sent) == 2:
            return
        self.messages.append(
            QueueMessage(json.dumps({"job_id": job_id}), str(len(self.sent)))
        )

    def receive(self) -> QueueMessage | None:
        return self.messages.pop(0) if self.messages else None

    def acknowledge(self, message: QueueMessage) -> None:
        self.acknowledged.append(message.receipt_handle)

    def extend(self, message: QueueMessage, seconds: int) -> None:
        assert seconds == 120
        self.extended.append(message.receipt_handle)


class MemoryArtifacts:
    def __init__(self) -> None:
        self.reports: list[object] = []
        self.returned: list[ArtifactPut] = []
        self.fail = False
        self.close_calls = 0
        self.fail_close = False

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError(MARKER)

    def put_report(self, report: object) -> ArtifactPut:
        if self.fail:
            raise RuntimeError(MARKER)
        self.reports.append(deepcopy(report))
        encoded = json.dumps(
            report, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        artifact = ArtifactPut(f"evaluation/{digest}.json", digest)
        self.returned.append(artifact)
        return artifact


@pytest.fixture
def case() -> dict[str, object]:
    corpus = json.loads(
        (Path(__file__).parent / "evaluation" / "scenarios.json").read_text()
    )
    scenario = next(item for item in corpus["scenarios"] if item["id"] == "P05")
    return cast(dict[str, object], scenario)


@pytest.fixture
def services() -> driver._Services:
    queue = MemoryQueue()
    return driver._Services(queue, queue, MemoryArtifacts())


@pytest.fixture
def default_adapters(monkeypatch: pytest.MonkeyPatch) -> driver._Services:
    queue = MemoryQueue()
    artifacts = MemoryArtifacts()

    def sender(endpoint: str) -> MemoryQueue:
        assert endpoint == ENDPOINT
        return queue

    def consumer(endpoint: str, kind: str) -> MemoryQueue:
        assert endpoint == ENDPOINT and kind == "agent"
        return queue

    def store(endpoint: str) -> MemoryArtifacts:
        assert endpoint == ENDPOINT
        return artifacts

    class Isolated:
        def __init__(self, endpoint: str) -> None:
            assert endpoint == ENDPOINT
            self.sender = driver.LocalSqsSender(endpoint)
            self.consumer = driver.LocalSqsConsumer(endpoint, "agent")
            self.name = "fewia-eval-" + "0" * 32

        def close(self) -> None:
            pass

    monkeypatch.setattr(driver, "LocalSqsSender", sender)
    monkeypatch.setattr(driver, "LocalSqsConsumer", consumer)
    monkeypatch.setattr(driver, "LocalArtifactStore", store)
    monkeypatch.setattr(driver, "IsolatedLocalQueue", Isolated)
    return driver._Services(queue, queue, artifacts)


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("FEWIA_EVALUATION_DATABASE_URL")
    if not url:
        if os.environ.get("FEWIA_REQUIRE_DB") == "1":
            pytest.fail(
                "FEWIA_REQUIRE_DB requires FEWIA_EVALUATION_DATABASE_URL. "
                "Set FEWIA_EVALUATION_DATABASE_URL to a migrated PostgreSQL database."
            )
        pytest.skip("PostgreSQL integration requires FEWIA_EVALUATION_DATABASE_URL.")
    return url


@pytest.mark.parametrize("url", [None, ""])
def test_database_url_fails_when_missing_and_required(
    monkeypatch: pytest.MonkeyPatch, url: str | None
) -> None:
    if url is None:
        monkeypatch.delenv("FEWIA_EVALUATION_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", url)
    monkeypatch.setenv("FEWIA_REQUIRE_DB", "1")
    with pytest.raises((pytest.fail.Exception, pytest.skip.Exception)) as caught:
        database_url.__wrapped__()
    assert caught.type is pytest.fail.Exception
    assert str(caught.value) == (
        "FEWIA_REQUIRE_DB requires FEWIA_EVALUATION_DATABASE_URL. "
        "Set FEWIA_EVALUATION_DATABASE_URL to a migrated PostgreSQL database."
    )


@pytest.mark.parametrize("url", [None, ""])
@pytest.mark.parametrize("require_db", [None, "", "0", "true", "yes", " 1", "1 "])
def test_database_url_skips_when_missing_and_optional(
    monkeypatch: pytest.MonkeyPatch, url: str | None, require_db: str | None
) -> None:
    if url is None:
        monkeypatch.delenv("FEWIA_EVALUATION_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", url)
    if require_db is None:
        monkeypatch.delenv("FEWIA_REQUIRE_DB", raising=False)
    else:
        monkeypatch.setenv("FEWIA_REQUIRE_DB", require_db)
    with pytest.raises((pytest.fail.Exception, pytest.skip.Exception)) as caught:
        database_url.__wrapped__()
    assert caught.type is pytest.skip.Exception
    assert str(caught.value) == (
        "PostgreSQL integration requires FEWIA_EVALUATION_DATABASE_URL."
    )


@pytest.mark.parametrize("require_db", [None, "1", "0", "true"])
def test_database_url_returns_supplied_value(
    monkeypatch: pytest.MonkeyPatch, require_db: str | None
) -> None:
    monkeypatch.setenv("FEWIA_EVALUATION_DATABASE_URL", LOCAL_DATABASE)
    if require_db is None:
        monkeypatch.delenv("FEWIA_REQUIRE_DB", raising=False)
    else:
        monkeypatch.setenv("FEWIA_REQUIRE_DB", require_db)
    assert database_url.__wrapped__() == LOCAL_DATABASE


@pytest.fixture
def schemas(monkeypatch: pytest.MonkeyPatch, database_url: str) -> Iterator[list[str]]:
    names: list[str] = []

    @contextmanager
    def tracked(url: str | None = None) -> Iterator[FixtureDatabase]:
        with fixture_database(url) as database:
            with database.factory() as session:
                name = session.scalar(text("SELECT current_schema()"))
                assert isinstance(name, str) and name.startswith("eval_")
                names.append(name)
            yield database

    monkeypatch.setattr(driver, "fixture_database", tracked)
    yield names
    admin = create_engine(database_url, hide_parameters=True)
    try:
        with admin.connect() as connection:
            for name in names:
                exists = connection.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:name)"
                    ),
                    {"name": name},
                )
                assert exists is False
    finally:
        admin.dispose()


def run_case(
    case: dict[str, object], database_url: str, services: driver._Services
) -> dict[str, object]:
    return driver._evaluate(
        case, database_url=database_url, endpoint=ENDPOINT, services=services
    )


def test_default_artifact_store_closes_after_success(
    case: dict[str, object],
    database_url: str,
    default_adapters: driver._Services,
    schemas: list[str],
) -> None:
    report = driver.evaluate_duplicate_case(
        case, database_url=database_url, endpoint=ENDPOINT
    )
    assert report["status"] == "passed"
    artifacts = cast(MemoryArtifacts, default_adapters.artifacts)
    assert len(artifacts.reports) == 1
    assert artifacts.close_calls == 1
    assert len(schemas) == 1


@pytest.mark.parametrize(
    "failure_point",
    [
        "LocalSqsSender",
        "LocalSqsConsumer",
        "DuplicateHandler",
        "create_job",
        "publish_pending",
        "process_one",
        "repeat_handoff",
        "artifact_write",
        "scoring",
    ],
)
def test_default_artifact_store_closes_after_later_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: dict[str, object],
    database_url: str,
    default_adapters: driver._Services,
    schemas: list[str],
    failure_point: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> Never:
        raise RuntimeError(MARKER)

    artifacts = cast(MemoryArtifacts, default_adapters.artifacts)
    if failure_point == "repeat_handoff":
        monkeypatch.setattr(DuplicateHandler, "repeat_handoff", fail)
    elif failure_point == "artifact_write":
        artifacts.fail = True
    elif failure_point == "scoring":
        case["expected"] = {}
    else:
        monkeypatch.setattr(driver, failure_point, fail)
    report = driver.evaluate_duplicate_case(
        case, database_url=database_url, endpoint=ENDPOINT
    )
    assert report["status"] == "failed"
    assert artifacts.close_calls == 1
    assert MARKER not in json.dumps(report) + capsys.readouterr().err
    assert len(schemas) == 1


def test_default_artifact_store_closes_before_database_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, object],
    database_url: str,
    default_adapters: driver._Services,
    schemas: list[str],
) -> None:
    tracked_database = driver.fixture_database
    artifacts = cast(MemoryArtifacts, default_adapters.artifacts)

    @contextmanager
    def cleanup_failure(url: str | None = None) -> Iterator[FixtureDatabase]:
        with tracked_database(url) as database:
            try:
                yield database
            finally:
                assert artifacts.close_calls == 1
        raise RuntimeError(MARKER)

    monkeypatch.setattr(driver, "fixture_database", cleanup_failure)
    report = driver.evaluate_duplicate_case(
        case, database_url=database_url, endpoint=ENDPOINT
    )
    assert report["status"] == "failed"
    assert report["evidence_paths"] == []
    assert artifacts.close_calls == 1
    assert MARKER not in json.dumps(report)
    assert len(schemas) == 1


def test_artifact_close_failure_is_safe_and_schema_is_cleaned(
    case: dict[str, object],
    database_url: str,
    default_adapters: driver._Services,
    schemas: list[str],
) -> None:
    artifacts = cast(MemoryArtifacts, default_adapters.artifacts)
    artifacts.fail_close = True
    report = driver.evaluate_duplicate_case(
        case, database_url=database_url, endpoint=ENDPOINT
    )
    assert report["status"] == "failed"
    assert report["evidence_paths"] == []
    assert report["reason"] == "duplicate_execution_failed"
    assert len(artifacts.reports) == 1
    assert artifacts.close_calls == 1
    assert MARKER not in json.dumps(report)
    assert len(schemas) == 1


@pytest.mark.parametrize("artifact_failure", [False, True])
def test_injected_artifact_store_stays_caller_owned(
    case: dict[str, object],
    database_url: str,
    services: driver._Services,
    schemas: list[str],
    artifact_failure: bool,
) -> None:
    artifacts = cast(MemoryArtifacts, services.artifacts)
    artifacts.fail = artifact_failure
    artifacts.fail_close = True
    report = run_case(case, database_url, services)
    assert report["status"] == ("failed" if artifact_failure else "passed")
    assert artifacts.close_calls == 0
    assert report["evidence_paths"] == [
        "local_postgresql",
        "worker",
        "deterministic_fake_queue",
        "deterministic_fake_artifact",
        "deterministic_fake_provider",
    ]
    assert len(schemas) == 1


def test_duplicate_deliveries_use_production_worker_and_cached_handoff(
    case: dict[str, object],
    database_url: str,
    services: driver._Services,
    schemas: list[str],
) -> None:
    report = run_case(case, database_url, services)
    assert report["status"] == "passed"
    checks = cast(dict[str, object], report["checks"])
    assert checks and all(value is True for value in checks.values())
    observed = cast(dict[str, object], report["observed"])
    assert observed["worker_outcomes"] == ["succeeded", "terminal"]
    assert observed["job_status"] == "succeeded"
    for key in ("job_count", "outbox_count", "evidence_count", "handoff_count"):
        assert observed[key] == 1
    for key in ("handler_calls", "provider_calls", "artifact_attempts"):
        assert observed[key] == 1
    queue = cast(MemoryQueue, services.queue)
    assert len(queue.sent) == 2 and queue.sent[0] == queue.sent[1]
    assert queue.acknowledged == ["1", "2"]
    assert queue.extended
    artifacts = cast(MemoryArtifacts, services.artifacts)
    assert len(artifacts.reports) == 1
    assert observed["artifact"] == artifacts.returned[0]._asdict()
    revision = observed["evidence_revision_id"]
    assert isinstance(revision, str) and len(revision) == 64
    assert report["evidence_paths"] == [
        "local_postgresql",
        "worker",
        "deterministic_fake_queue",
        "deterministic_fake_artifact",
        "deterministic_fake_provider",
    ]
    assert report["model_quality_applicable"] is False
    assert len(schemas) == 1


def test_repeated_invocations_get_private_schemas(
    case: dict[str, object],
    database_url: str,
    schemas: list[str],
) -> None:
    for _ in range(2):
        queue = MemoryQueue()
        report = run_case(
            case, database_url, driver._Services(queue, queue, MemoryArtifacts())
        )
        assert report["status"] == "passed"
    assert len(schemas) == 2 and len(set(schemas)) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("plan_accepted", False),
        ("plan_accepted", 1),
        ("plan_accepted", "true"),
        ("delivery_attempts", True),
        ("delivery_attempts", 2.0),
        ("delivery_attempts", "2"),
        ("delivery_attempts", 1),
        ("delivery_attempts", 3),
        ("user_id", True),
        ("user_id", 0),
        ("meals", []),
        ("meals", [{"recipe_id": "unknown", "servings": 2}]),
        ("meals", [{"recipe_id": "bean_tacos", "servings": True}]),
    ],
)
def test_malformed_inputs_fail_before_publication(
    case: dict[str, object], services: driver._Services, field: str, value: object
) -> None:
    cast(dict[str, object], case["inputs"])[field] = value
    report = run_case(case, LOCAL_DATABASE, services)
    assert report["status"] == "failed"
    assert cast(MemoryQueue, services.queue).sent == []
    assert cast(MemoryArtifacts, services.artifacts).reports == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "P04"),
        ("fixture_behavior", {"kind": "duplicate_sqs_delivery", "provider": "live"}),
        ("fixture_behavior", {"kind": "other", "provider": "fake"}),
    ],
)
def test_only_explicit_fake_p05_runs(
    case: dict[str, object], services: driver._Services, field: str, value: object
) -> None:
    case[field] = value
    assert run_case(case, LOCAL_DATABASE, services)["status"] == "failed"
    assert cast(MemoryQueue, services.queue).sent == []


@pytest.mark.parametrize(
    ("url", "endpoint"),
    [
        ("", ENDPOINT),
        ("sqlite://", ENDPOINT),
        (LOCAL_DATABASE, "https://sqs.us-east-1.amazonaws.com"),
        (LOCAL_DATABASE, "http://localhost:9999"),
    ],
)
def test_local_boundaries_fail_without_transport(
    case: dict[str, object], services: driver._Services, url: str, endpoint: str
) -> None:
    report = driver._evaluate(
        case, database_url=url, endpoint=endpoint, services=services
    )
    assert report["status"] == "failed"
    assert report["evidence_paths"] == []
    assert cast(MemoryQueue, services.queue).sent == []


def test_sqlite_fixture_cannot_claim_postgresql(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, object],
    services: driver._Services,
) -> None:
    closed: list[bool] = []

    @contextmanager
    def sqlite_database(url: str | None = None) -> Iterator[FixtureDatabase]:
        del url
        try:
            with fixture_database() as database:
                yield database
        finally:
            closed.append(True)

    monkeypatch.setattr(driver, "fixture_database", sqlite_database)
    report = run_case(case, LOCAL_DATABASE, services)
    assert report["evidence_class"] == "unknown"
    assert report["status"] == "failed"
    assert closed == [True]
    assert cast(MemoryQueue, services.queue).sent == []


def test_failed_first_handler_has_terminal_duplicate_and_safe_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: dict[str, object],
    database_url: str,
    services: driver._Services,
    schemas: list[str],
) -> None:
    outcomes: list[str] = []
    handler_calls: list[bool] = []

    class FailingHandler(DuplicateHandler):
        def __call__(
            self, payload: dict[str, object], heartbeat: Callable[[], None]
        ) -> dict[str, object]:
            self.handler_calls += 1
            handler_calls.append(True)
            raise RuntimeError(MARKER)

    def observe(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: DuplicateHandler,
    ) -> str:
        outcome = process_one(factory, queue, kind, handler)
        outcomes.append(outcome)
        return outcome

    monkeypatch.setattr(driver, "DuplicateHandler", FailingHandler)
    monkeypatch.setattr(driver, "process_one", observe)
    report = run_case(case, database_url, services)
    assert report["status"] == "failed"
    assert outcomes == ["handler_failed", "terminal"]
    assert handler_calls == [True]
    assert cast(MemoryQueue, services.queue).acknowledged == ["1", "2"]
    assert not cast(MemoryArtifacts, services.artifacts).reports
    assert MARKER not in json.dumps(report) + capsys.readouterr().err
    assert len(schemas) == 1


def test_public_driver_failure_does_not_claim_floci(case: dict[str, object]) -> None:
    report = driver.evaluate_duplicate_case(
        case, database_url=LOCAL_DATABASE, endpoint="https://example.com"
    )
    assert report["status"] == "failed"
    assert report["evidence_class"] == "unknown"
    assert report["evidence_paths"] == []


def test_database_exception_uses_static_failure(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, object],
    services: driver._Services,
) -> None:
    def unavailable(url: str | None = None) -> AbstractContextManager[FixtureDatabase]:
        raise RuntimeError(MARKER)

    monkeypatch.setattr(driver, "fixture_database", unavailable)
    report = run_case(case, LOCAL_DATABASE, services)
    assert report["status"] == "failed"
    assert report["reason"] == "duplicate_execution_failed"
    assert MARKER not in json.dumps(report)
    assert cast(MemoryQueue, services.queue).sent == []


def test_publication_failure_cleans_private_schema(
    case: dict[str, object],
    database_url: str,
    schemas: list[str],
) -> None:
    class FailingSender:
        def send(self, kind: str, job_id: str) -> None:
            raise RuntimeError(MARKER)

    queue = MemoryQueue()
    artifacts = MemoryArtifacts()
    services = driver._Services(FailingSender(), queue, artifacts)
    report = run_case(case, database_url, services)
    assert report["status"] == "failed"
    assert report["evidence_paths"] == []
    assert MARKER not in json.dumps(report)
    assert not queue.sent and not artifacts.reports
    assert len(schemas) == 1


def test_artifact_failure_is_visible_and_schema_is_cleaned(
    case: dict[str, object],
    database_url: str,
    services: driver._Services,
    schemas: list[str],
) -> None:
    cast(MemoryArtifacts, services.artifacts).fail = True
    report = run_case(case, database_url, services)
    assert report["status"] == "failed"
    checks = cast(dict[str, object], report["checks"])
    assert checks["artifact_saved"] is False
    assert checks["job_succeeded"] is False
    assert cast(dict[str, object], report["observed"])["worker_outcomes"] == [
        "handler_failed",
        "terminal",
    ]
    assert MARKER not in json.dumps(report)
    assert len(schemas) == 1


def test_falsified_duplicate_handler_execution_breaks_checks(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, object],
    database_url: str,
    services: driver._Services,
    schemas: list[str],
) -> None:
    def unsafe_process(
        factory: sessionmaker[Session],
        queue: JobQueue,
        kind: str,
        handler: DuplicateHandler,
    ) -> str:
        outcome = process_one(factory, queue, kind, handler)
        if outcome == "terminal":
            handler(
                {"case_id": "P05", "user_id": handler.context.user_id}, lambda: None
            )
        return outcome

    monkeypatch.setattr(driver, "process_one", unsafe_process)
    report = run_case(case, database_url, services)
    assert report["status"] == "failed"
    checks = cast(dict[str, object], report["checks"])
    assert checks["deliveries"] is True
    assert checks["handler_once"] is False
    assert checks["artifact_once"] is False
    observed = cast(dict[str, object], report["observed"])
    assert observed["handler_calls"] == 2
    assert observed["artifact_attempts"] == 2
    assert len(cast(MemoryArtifacts, services.artifacts).reports) == 2
    assert len(schemas) == 1


def test_missing_duplicate_delivery_breaks_checks(
    case: dict[str, object],
    database_url: str,
    services: driver._Services,
    schemas: list[str],
) -> None:
    cast(MemoryQueue, services.queue).drop_duplicate = True
    report = run_case(case, database_url, services)
    assert report["status"] == "failed"
    assert cast(dict[str, object], report["checks"])["deliveries"] is False
    assert cast(dict[str, object], report["observed"])["worker_outcomes"] == [
        "succeeded",
        "empty",
    ]
    assert len(schemas) == 1


def test_gold_is_scored_after_real_behavior(
    case: dict[str, object],
    database_url: str,
    services: driver._Services,
    schemas: list[str],
) -> None:
    expected = cast(dict[str, object], case["expected"])
    expected["total_cents"] = -1
    expected["evidence_class"] = "deployed_aws"
    calls = cast(list[dict[str, object]], expected["domain_calls"])
    cast(dict[str, object], calls[1]["expectation"])["delivery_attempts"] = 3
    cast(dict[str, object], case["inputs"])["unused_secret"] = MARKER
    report = run_case(case, database_url, services)
    assert report["status"] == "failed"
    checks = cast(dict[str, object], report["checks"])
    assert checks["gold_total"] is False
    assert checks["gold_deliveries"] is False
    assert checks["handler_once"] is True
    assert report["evidence_class"] == "local_postgresql"
    assert MARKER not in json.dumps(report)
    assert len(cast(MemoryArtifacts, services.artifacts).reports) == 1
    assert len(schemas) == 1


class FakeFlociSqs:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.deleted_urls: list[str] = []
        self.lookups: list[str] = []
        self.sent_urls: list[str] = []
        self.received_urls: list[str] = []
        self._messages: list[tuple[str, str]] = []
        self._receipts = 0

    def create_queue(self, *, QueueName: str) -> dict[str, object]:
        self.created.append(QueueName)
        return {"QueueUrl": f"{ENDPOINT}/000000000000/{QueueName}"}

    def get_queue_url(self, *, QueueName: str) -> dict[str, object]:
        self.lookups.append(QueueName)
        return {"QueueUrl": f"{ENDPOINT}/000000000000/{QueueName}"}

    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, object]:
        self.sent_urls.append(QueueUrl)
        self._messages.append((QueueUrl, MessageBody))
        return {}

    def receive_message(self, **kwargs: object) -> dict[str, object]:
        queue_url = kwargs.get("QueueUrl")
        if isinstance(queue_url, str):
            self.received_urls.append(queue_url)
        if not self._messages:
            return {}
        _url, body = self._messages.pop(0)
        self._receipts += 1
        return {"Messages": [{"Body": body, "ReceiptHandle": str(self._receipts)}]}

    def delete_message(self, **kwargs: object) -> dict[str, object]:
        return {}

    def change_message_visibility(self, **kwargs: object) -> dict[str, object]:
        return {}

    def delete_queue(self, *, QueueUrl: str) -> dict[str, object]:
        self.deleted_urls.append(QueueUrl)
        return {}


def _patch_fake_sqs(
    monkeypatch: pytest.MonkeyPatch, client: FakeFlociSqs
) -> MemoryArtifacts:
    session = Mock()
    session.client.return_value = client
    factory = Mock(return_value=session)
    monkeypatch.setattr(local_sqs.boto3, "Session", factory)
    monkeypatch.setattr(local_sqs_consumer.boto3, "Session", factory)
    monkeypatch.setattr(local_sqs_isolated.boto3, "Session", factory)
    artifacts = MemoryArtifacts()

    def store(endpoint: str) -> MemoryArtifacts:
        assert endpoint == ENDPOINT
        return artifacts

    monkeypatch.setattr(driver, "LocalArtifactStore", store)
    return artifacts


def _assert_private_queue(client: FakeFlociSqs) -> None:
    assert len(client.created) == 1
    name = client.created[0]
    assert re.fullmatch(r"fewia-eval-[0-9a-f]{32}", name)
    assert "fewia-agent" not in client.lookups
    assert all(item == name for item in client.lookups)
    queue_url = f"{ENDPOINT}/000000000000/{name}"
    assert client.deleted_urls == [queue_url]
    assert all(url == queue_url for url in client.sent_urls)
    assert all(url == queue_url for url in client.received_urls)


def test_duplicate_driver_deletes_private_queue_on_success(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, object],
    database_url: str,
    schemas: list[str],
) -> None:
    client = FakeFlociSqs()
    artifacts = _patch_fake_sqs(monkeypatch, client)
    report = driver.evaluate_duplicate_case(
        case, database_url=database_url, endpoint=ENDPOINT
    )
    assert report["status"] == "passed"
    assert "floci_sqs" in cast(list[object], report["evidence_paths"])
    _assert_private_queue(client)
    assert len(client.sent_urls) == 2
    assert len(client.received_urls) >= 2
    assert artifacts.close_calls == 1
    assert len(schemas) == 1


def test_duplicate_driver_deletes_private_queue_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    case: dict[str, object],
    database_url: str,
    schemas: list[str],
) -> None:
    client = FakeFlociSqs()
    _patch_fake_sqs(monkeypatch, client)

    def fail(*args: object, **kwargs: object) -> Never:
        raise RuntimeError(MARKER)

    monkeypatch.setattr(driver, "process_one", fail)
    report = driver.evaluate_duplicate_case(
        case, database_url=database_url, endpoint=ENDPOINT
    )
    assert report["status"] == "failed"
    _assert_private_queue(client)
    assert len(schemas) == 1
