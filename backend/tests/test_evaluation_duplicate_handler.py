import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from app.domain.grocery import SUPPORTED_RECIPE_IDS
from app.evaluation_database import fixture_database
from app.evaluation_duplicate_handler import DuplicateHandler
from app.evaluation_inputs import CaseContext, prepare_case
from app.evaluation_plan_inputs import fixture_plan
from app.models import User
from app.providers import instacart
from app.providers.local_artifacts import ArtifactPut
from app.services.evidence_store import load_evidence
from app.services.handoff_intents import read_handoff
from app.services.job_delivery import JobHandler
from app.services.shopping_payload import build_shopping_payload, shopping_payload_hash


class _Store:
    def __init__(self) -> None:
        self.attempts = 0
        self.fail = False
        self.reports: list[dict[str, object]] = []
        self.results: list[ArtifactPut] = []

    def put_report(self, report: object) -> ArtifactPut:
        self.attempts += 1
        if self.fail:
            raise RuntimeError("artifact put failed")
        encoded = json.dumps(report, sort_keys=True, allow_nan=False)
        copied = cast(dict[str, object], json.loads(encoded))
        self.reports.append(copied)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        result = ArtifactPut(f"test-reports/{digest}.json", digest)
        self.results.append(result)
        return result


def _context() -> CaseContext:
    return prepare_case(
        {
            "id": "P05",
            "messages": [{"role": "user", "content": "Plan eight servings."}],
            "inputs": {
                "user_id": 7,
                "now": "2026-04-15T12:00:00+00:00",
                "budget_period": "2026-04-01",
                "spending_period": "2026-04-01",
                "monthly_limit_cents": 100_000,
                "posted_cents": 1_000,
                "pending_cents": 250,
                "spending_refreshed_at": "2026-04-15T12:00:00+00:00",
                "plan_cap_cents": 80_000,
                "meals": [
                    {"recipe_id": sorted(SUPPORTED_RECIPE_IDS)[0], "servings": 8}
                ],
            },
        }
    )


@pytest.fixture
def harness() -> Iterator[tuple[DuplicateHandler, _Store, CaseContext]]:
    with fixture_database() as database:
        with database.factory.begin() as session:
            session.add_all(
                [User(id=7, display_name="Owner"), User(id=8, display_name="Other")]
            )
        context = _context()
        store = _Store()
        yield DuplicateHandler(database.factory, context, store), store, context


def test_production_evidence_is_owner_scoped(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
) -> None:
    handler, store, context = harness
    job_handler: JobHandler = handler
    result = job_handler({"case_id": "P05", "user_id": 7}, lambda: None)
    revision = handler.evidence_revision_id
    assert revision is not None
    assert result["evidence_revision_id"] == revision
    snapshot = load_evidence(handler.factory, context.user_id, revision)
    assert snapshot is not None
    assert snapshot["planning"] == handler.planning
    assert load_evidence(handler.factory, 8, revision) is None
    budget_inputs = cast(dict[str, object], snapshot["budget_inputs"])
    spending = cast(dict[str, object], budget_inputs["spending"])
    assert spending["posted_cents"] == 1_000
    assert spending["pending_cents"] == 250
    assert budget_inputs["spending_source"] == "fixture"
    assert len(store.reports) == 1


def test_payload_preserves_current_plan_quantities(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
) -> None:
    handler, _, context = harness
    result = handler({"case_id": "P05", "user_id": 7}, lambda: None)
    current_plan = fixture_plan(context.inputs)
    expected_payload = build_shopping_payload(current_plan)
    assert handler.shopping_payload == expected_payload
    assert handler.provider.payload == expected_payload
    assert handler.planning is not None
    assert handler.planning["plan"] == json.loads(json.dumps(asdict(current_plan)))
    purchases = sorted(
        (line for line in current_plan.lines if not line.from_pantry),
        key=lambda line: line.ingredient_id,
    )
    line_items = cast(list[dict[str, object]], expected_payload["line_items"])
    for item, line in zip(line_items, purchases, strict=True):
        assert item["line_item_measurements"] == [
            {"quantity": line.quantity, "unit": line.unit}
        ]
    handoff = cast(dict[str, object], result["handoff"])
    assert handoff["payload_hash"] == shopping_payload_hash(expected_payload)


def test_repeat_handoff_uses_cached_intent_and_fixed_clock(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
) -> None:
    handler, store, _ = harness
    handler({"case_id": "P05", "user_id": 7}, lambda: None)
    original = handler.handoff
    assert original is not None
    assert original.state == "succeeded"
    assert original.attempts == 1
    assert original.url == "https://www.instacart.com/store/shopping_lists/evaluation"
    clock = datetime(2026, 4, 15, 12, tzinfo=UTC)
    assert original.expires_at == clock + timedelta(days=7)
    assert handler.repeat_handoff() == original
    assert read_handoff(handler.factory, 7, original.id, now=clock) == original
    assert read_handoff(handler.factory, 8, original.id, now=clock) is None
    assert handler.provider.calls == 1
    assert handler.handler_calls == 1
    assert store.attempts == 1


def test_duplicate_handler_call_keeps_evidence_and_handoff(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
) -> None:
    handler, store, _ = harness
    payload: dict[str, object] = {"case_id": "P05", "user_id": 7}
    first = handler(payload, lambda: None)
    second = handler(payload, lambda: None)
    assert first["evidence_revision_id"] == second["evidence_revision_id"]
    assert first["handoff"] == second["handoff"]
    assert handler.handler_calls == second["handler_calls"] == 2
    assert handler.artifact_attempts == second["artifact_attempts"] == 2
    assert handler.provider.calls == second["provider_calls"] == 1
    assert store.attempts == 2
    assert "artifact" not in store.reports[0]
    assert second["artifact"] == {
        "key": store.results[1].key,
        "sha256": store.results[1].sha256,
    }


def test_artifact_failure_propagates_and_retry_caches_handoff(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
) -> None:
    handler, store, _ = harness
    store.fail = True
    payload: dict[str, object] = {"case_id": "P05", "user_id": 7}
    with pytest.raises(RuntimeError, match="^artifact put failed$"):
        handler(payload, lambda: None)
    assert handler.handler_calls == 1
    assert handler.artifact_attempts == store.attempts == 1
    assert handler.artifact is None
    assert handler.evidence_revision_id is not None
    original = handler.handoff
    assert original is not None
    assert original.state == "succeeded"
    store.fail = False
    result = handler(payload, lambda: None)
    assert handler.handoff == original
    assert result["artifact_attempts"] == store.attempts == 2
    assert handler.provider.calls == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"case_id": "P04", "user_id": 7},
        {"case_id": "P05", "user_id": 8},
        {"case_id": "P05", "user_id": "7"},
        {"case_id": "P05", "user_id": True},
        {"user_id": 7},
        {"case_id": "P05"},
    ],
)
def test_invalid_envelope_rejects_before_effects(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    handler, store, _ = harness

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("unexpected stage")

    with monkeypatch.context() as patch:
        for name in ("execute_plan", "save_plan_evidence", "prepare_handoff"):
            patch.setattr(f"app.evaluation_duplicate_handler.{name}", forbidden)
        with pytest.raises(ValueError):
            handler(payload, lambda: forbidden())
    assert handler.handler_calls == 0
    assert handler.planning is None
    assert handler.evidence_revision_id is None
    assert handler.handoff is None
    assert handler.provider.calls == 0
    assert handler.artifact_attempts == store.attempts == 0
    result = handler({"case_id": "P05", "user_id": 7}, lambda: None)
    assert handler.handler_calls == result["handler_calls"] == 1
    assert handler.artifact_attempts == store.attempts == 1


def test_heartbeat_brackets_meaningful_stages(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
) -> None:
    handler, _, _ = harness
    stages: list[tuple[bool, bool, int, int]] = []

    def heartbeat() -> None:
        stages.append(
            (
                handler.planning is not None,
                handler.evidence_revision_id is not None,
                handler.provider.calls,
                handler.artifact_attempts,
            )
        )

    handler({"case_id": "P05", "user_id": 7}, heartbeat)
    assert stages == [
        (False, False, 0, 0),
        (True, False, 0, 0),
        (True, True, 0, 0),
        (True, True, 1, 0),
        (True, True, 1, 1),
    ]


def test_untrusted_fields_cannot_override_facts_or_reach_report(
    harness: tuple[DuplicateHandler, _Store, CaseContext],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing, store, context = harness

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("unexpected network or client setup")

    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("app.providers.local_artifacts.boto3.Session", forbidden)
    assert not hasattr(instacart, "InstacartDevelopmentProvider")
    handler = DuplicateHandler(existing.factory, context, store)
    result = handler(
        {
            "case_id": "P05",
            "user_id": 7,
            "expected": {"evidence_revision_id": "untrusted-value"},
            "credential_ref": "untrusted-value",
            "raw_ledger": [{"amount": "untrusted-value"}],
            "inputs": {"meals": [], "monthly_limit_cents": 0},
            "hostile_url": "https://example.invalid",
        },
        lambda: None,
    )
    assert handler.planning is not None
    request = cast(dict[str, object], handler.planning["request"])
    assert request["meals"] == context.inputs["meals"]
    report = store.reports[0]
    assert set(report) == {
        "case_id",
        "planning",
        "evidence_revision_id",
        "handoff",
        "handler_calls",
        "provider_calls",
        "artifact_attempts",
    }
    assert "untrusted-value" not in json.dumps(report)
    assert result["artifact"] == {
        "key": store.results[0].key,
        "sha256": store.results[0].sha256,
    }
