"""PostgreSQL, Floci SQS, fake handoff, and Floci S3 tests for scenario P05."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import p05_resources
import pytest
from p05_resources import P05Resources
from sqlalchemy import func, select

from app.api.handoff_models import job_shopping_payload
from app.evidence_models import GroceryEvidence
from app.handoff_models import ShoppingHandoff
from app.job_models import Job
from app.models import User
from app.providers.instacart import validate_link_url
from app.services.agent_jobs import make_agent_handler
from app.services.handoff_dispatch import dispatch_handoff
from app.services.handoff_intents import prepare_handoff
from app.services.job_consumer import process_one
from app.services.job_submission import create_job
from app.services.plan_job import PlanJobInput

_SCENARIOS = Path(__file__).resolve().parent / "evaluation" / "scenarios.json"
_NOTICE = (
    "Estimated from the demo price catalog. Instacart prices, availability, "
    "taxes, delivery fees, and tips are not verified."
)
_HEX = frozenset("0123456789abcdef")
_EVAL_BUCKET = "fewia-eval"
_BODY_LIMIT = 65536
_FIXTURE_LINK = "https://www.instacart.com/store/shopping_lists/p05-fixture"
_PATH_CLASSES = ("local_postgresql", "worker", "floci_sqs", "floci_s3")


class _QueueSendClient(Protocol):
    def send_message(self, *, QueueUrl: str, MessageBody: str) -> dict[str, object]: ...


class _S3Body(Protocol):
    def read(self, amt: int) -> bytes: ...

    def close(self) -> None: ...


class _S3GetClient(Protocol):
    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]: ...


class _FakeLinkProvider:
    def __init__(self) -> None:
        self.calls = 0

    def create_link(self, payload: dict[str, object]) -> str:
        del payload
        self.calls += 1
        return _FIXTURE_LINK


def _require_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise TypeError(f"{name} MUST be an object")
    return cast(dict[str, object], value)


def _p05_scenario() -> dict[str, object]:
    document = json.loads(_SCENARIOS.read_text(encoding="utf-8"))
    root = _require_object(document, "scenarios.json")
    scenarios = root.get("scenarios")
    if not isinstance(scenarios, list):
        raise TypeError("scenarios MUST be a list")
    for item in scenarios:
        if isinstance(item, dict) and item.get("id") == "P05":
            return _require_object(item, "P05")
    raise LookupError("P05 is missing")


def _plan_payload(inputs: dict[str, object]) -> dict[str, object]:
    return {
        "request": {
            "meals": inputs["meals"],
            "budget_period": inputs["budget_period"],
            "plan_cap_cents": inputs["plan_cap_cents"],
            "diet": inputs["diet"],
            "pantry_ingredients": inputs["pantry_ingredients"],
            "ingredient_exclusions": inputs["ingredient_exclusions"],
        },
        "monthly_limit_cents": inputs["monthly_limit_cents"],
        "spending": {
            "period": inputs["budget_period"],
            "posted_cents": inputs["posted_cents"],
            "pending_cents": inputs["pending_cents"],
            "refreshed_at": inputs["spending_refreshed_at"],
        },
        "spending_source": "fixture",
    }


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("now MUST be an ISO-8601 UTC string")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _is_revision_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in _HEX for char in value)
    )


def _handoff_count(resources: P05Resources) -> int:
    with resources.factory() as session:
        return int(
            session.scalar(select(func.count()).select_from(ShoppingHandoff)) or 0
        )


def _canonical_report(report: dict[str, object]) -> bytes:
    return json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    ).encode("utf-8")


def _read_s3_bytes(resources: P05Resources, key: str) -> bytes:
    client = cast(_S3GetClient, resources.artifacts._client)
    body: _S3Body | None = None
    try:
        response = client.get_object(Bucket=_EVAL_BUCKET, Key=key)
        body = cast(_S3Body, response["Body"])
        return body.read(_BODY_LIMIT)
    finally:
        if body is not None:
            body.close()


def run_duplicate_plan(
    resources: P05Resources, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, int]:
    """Create one plan job, enqueue it twice, and process both deliveries."""
    scenario = _p05_scenario()
    inputs = _require_object(scenario.get("inputs"), "inputs")
    assert inputs["plan_accepted"] is True
    attempts = inputs["delivery_attempts"]
    assert type(attempts) is int
    assert attempts == 2
    payload = _plan_payload(inputs)
    PlanJobInput.model_validate(payload)
    clock = _parse_utc(inputs["now"])

    def frozen_now() -> datetime:
        return clock

    monkeypatch.setattr("app.services.plan_job._utc_now", frozen_now)
    with resources.factory.begin() as session:
        session.add(User(id=1, display_name="User 1"))
        session.flush()
        job, created = create_job(session, 1, "agent", str(uuid4()), payload)
        assert created is True
        job_id = job.id
    sender = cast(_QueueSendClient, resources.sender._client)
    body = json.dumps({"job_id": job_id})
    sender.send_message(QueueUrl=resources.queue_url, MessageBody=body)
    sender.send_message(QueueUrl=resources.queue_url, MessageBody=body)
    inner = make_agent_handler(resources.factory, None)
    calls: list[int] = []

    def handler(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        calls.append(1)
        return inner(payload, heartbeat)

    first = process_one(
        resources.factory,
        resources.consumer,
        "agent",
        handler,
        now=frozen_now,
    )
    second = process_one(
        resources.factory,
        resources.consumer,
        "agent",
        handler,
        now=frozen_now,
    )
    assert first == "succeeded"
    assert second == "terminal"
    assert len(calls) == 1
    return job_id, len(calls)


def test_p05_duplicate_sqs_delivery_completes_one_plan_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _p05_scenario()
    inputs = _require_object(scenario.get("inputs"), "inputs")
    expected = _require_object(scenario.get("expected"), "expected")
    assert inputs["plan_accepted"] is True
    assert type(inputs["delivery_attempts"]) is int
    assert inputs["delivery_attempts"] == 2
    assert expected["accepted"] is True
    assert expected["total_cents"] == 1703
    assert expected["notice"] == _NOTICE
    assert expected["evidence_class"] == "local_postgresql"
    path_classes = expected["path_classes"]
    assert isinstance(path_classes, list)
    assert "floci_sqs" in path_classes
    clock = _parse_utc(inputs["now"])
    deliveries = int(inputs["delivery_attempts"])

    def frozen_now() -> datetime:
        return clock

    with p05_resources.local_resources() as resources:
        job_id, handler_executions = run_duplicate_plan(resources, monkeypatch)
        with resources.factory() as session:
            job_count = int(session.scalar(select(func.count()).select_from(Job)) or 0)
            evidence_count = int(
                session.scalar(select(func.count()).select_from(GroceryEvidence)) or 0
            )
            job = session.get(Job, job_id)
        assert job_count == 1
        assert evidence_count == 1
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 1
        result = job.result
        assert isinstance(result, dict)
        assert _is_revision_id(result.get("evidence_revision_id"))
        plan = result.get("plan")
        assert isinstance(plan, dict)
        assert plan.get("accepted") is True
        assert plan.get("accepted") is expected["accepted"]
        assert plan.get("total_cents") == expected["total_cents"]
        assert plan.get("notice") == expected["notice"]
        assert handler_executions == 1
        payload = job_shopping_payload(resources.factory, job_id)
        first_prepare = prepare_handoff(resources.factory, 1, payload, now=clock)
        second_prepare = prepare_handoff(resources.factory, 1, payload, now=clock)
        assert first_prepare.id == second_prepare.id
        assert _handoff_count(resources) == 1
        assert validate_link_url(_FIXTURE_LINK) == _FIXTURE_LINK
        provider = _FakeLinkProvider()
        first_dispatch = dispatch_handoff(
            resources.factory,
            provider,
            1,
            first_prepare.id,
            retry=False,
            now=frozen_now,
        )
        second_dispatch = dispatch_handoff(
            resources.factory,
            provider,
            1,
            first_prepare.id,
            retry=False,
            now=frozen_now,
        )
        handoff_count = _handoff_count(resources)
        link_calls = provider.calls
        assert first_dispatch.state == "succeeded"
        assert second_dispatch.state == "succeeded"
        assert first_dispatch.id == first_prepare.id
        assert second_dispatch.id == first_prepare.id
        assert first_dispatch.attempts == 1
        assert second_dispatch.attempts == 1
        assert link_calls == 1
        assert handoff_count == 1
        report: dict[str, object] = {
            "run_id": resources.run_id,
            "evidence_class": "local_postgresql",
            "path_classes": list(_PATH_CLASSES),
            "handoff_provider_class": "deterministic_fake_provider",
            "metrics_status": "unassessed",
            "counts": {
                "jobs": job_count,
                "evidence": evidence_count,
                "handoffs": handoff_count,
                "handler_executions": handler_executions,
                "deliveries": deliveries,
                "link_calls": link_calls,
            },
        }
        artifact = resources.artifacts.put_report(report)
        resources.owned_artifact_keys.append(artifact.key)
        stored = _read_s3_bytes(resources, artifact.key)
        canonical = _canonical_report(report)
        digest = hashlib.sha256(canonical).hexdigest()
        assert stored == canonical
        assert artifact.sha256 == digest
        assert hashlib.sha256(stored).hexdigest() == digest
        assert artifact.key == f"evaluation/{digest}.json"
