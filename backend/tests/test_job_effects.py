"""Test fenced database effects with actual job claims."""

import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

import pytest
from conftest import require_test_database_url
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from test_plaid_sync import ScriptedProvider, page, txn
from test_plan_job import NOW, payload

from app.db import Base
from app.evaluation_database import fixture_database
from app.evidence_models import GroceryEvidence
from app.job_effect_models import JobEffect
from app.job_models import Job
from app.models import User
from app.plaid_models import PlaidItem, PlaidTransaction
from app.plan_models import PlanProposal, PlanRevision
from app.providers.plaid_contract import SyncPage
from app.services import plan_job as plan_job_module
from app.services.agent_jobs import make_agent_handler
from app.services.job_delivery import JobContext, LeaseLost, RetryableJobError
from app.services.job_effects import JobEffectConflict, apply_effect
from app.services.job_leases import claim_job
from app.services.job_submission import create_job
from app.services.plaid_sync import sync_item
from app.services.security_admission import (
    OwnerUnavailableError,
    database_utc_now,
)


def claim_context(
    factory: sessionmaker[Session],
    *,
    user_id: int = 1,
    payload: dict[str, object] | None = None,
    kind: Literal["agent", "sync"] = "agent",
    heartbeat: Callable[[], None] | None = None,
    job_id: str | None = None,
) -> JobContext:
    with factory.begin() as session:
        if job_id is None:
            job, _ = create_job(
                session,
                user_id,
                kind,
                str(uuid4()),
                {} if payload is None else json.loads(json.dumps(payload, default=str)),
            )
            job_id = job.id
        token = claim_job(session, job_id, now=database_utc_now(session))
        assert token is not None
        claimed = session.get(Job, job_id, populate_existing=True)
        assert claimed is not None
        return JobContext(
            job_id=claimed.id,
            user_id=claimed.user_id,
            lease_token=token,
            heartbeat=heartbeat or (lambda: None),
            attempt=claimed.attempts,
        )


@pytest.fixture()
def effect_factory() -> Iterator[sessionmaker[Session]]:
    with fixture_database(require_test_database_url()) as database:
        factory = database.factory
        with factory() as session:
            Base.metadata.create_all(
                session.get_bind(),
                tables=[PlanRevision.__table__, PlanProposal.__table__],
            )
        with factory.begin() as session:
            session.add_all(
                [User(id=1, display_name="One"), User(id=2, display_name="Two")]
            )
        yield factory


def expire(factory: sessionmaker[Session], context: JobContext) -> None:
    with factory.begin() as session:
        job = session.get(Job, context.job_id)
        assert job is not None
        job.lease_expires_at = database_utc_now(session) - timedelta(seconds=1)


def test_context_hides_lease_token(effect_factory: sessionmaker[Session]) -> None:
    context = claim_context(effect_factory)
    assert context.lease_token not in repr(context)


def test_crash_reclaim_reuses_first_immutable_evidence(
    effect_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = NOW
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: clock)
    body = payload()
    context = claim_context(effect_factory, payload=body)
    handler = make_agent_handler(effect_factory, None)
    first = handler(body, context)
    expire(effect_factory, context)
    reclaimed = claim_context(effect_factory, job_id=context.job_id)
    clock += timedelta(minutes=5)
    second = handler(body, reclaimed)
    assert second == first
    with effect_factory() as session:
        evidence = session.scalars(select(GroceryEvidence)).all()
        effects = session.scalars(select(JobEffect)).all()
        assert len(evidence) == len(effects) == 1
        assert evidence[0].id == first["evidence_revision_id"]
        assert evidence[0].snapshot["budget_inputs"]["calculated_at"] == (
            NOW.isoformat().replace("+00:00", "Z")
        )
    changed = payload(monthly_limit_cents=10_001)
    with pytest.raises(JobEffectConflict, match="Job effect input conflicts"):
        handler(changed, reclaimed)
    with effect_factory() as session:
        assert len(session.scalars(select(GroceryEvidence)).all()) == 1
        assert len(session.scalars(select(JobEffect)).all()) == 1


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize(
    "failure", ["token", "expired", "owner", "disabled", "attempt"]
)
def test_fence_rejects_writes_and_replays(
    effect_factory: sessionmaker[Session], failure: str, replay: bool
) -> None:
    context = claim_context(effect_factory)
    writes: list[bool] = []

    def write(session: Session) -> dict[str, object]:
        del session
        writes.append(True)
        return {"kind": "sync", "changed_count": 1}

    if replay:
        apply_effect(effect_factory, context, "sync:0", {}, write)
    if failure == "token":
        context = replace(context, lease_token="stale-token")
    elif failure == "expired":
        expire(effect_factory, context)
    elif failure == "owner":
        context = replace(context, user_id=2)
    elif failure == "attempt":
        context = replace(context, attempt=context.attempt + 1)
    else:
        with effect_factory.begin() as session:
            owner = session.get(User, context.user_id)
            assert owner is not None
            owner.status = "disabled"
    error = OwnerUnavailableError if failure == "disabled" else LeaseLost
    with pytest.raises(error):
        apply_effect(effect_factory, context, "sync:0", {}, write)
    assert len(writes) == int(replay)


def test_effect_and_database_write_roll_back_together(
    effect_factory: sessionmaker[Session],
) -> None:
    context = claim_context(effect_factory)

    def write(session: Session) -> dict[str, object]:
        session.add(GroceryEvidence(id="a" * 64, user_id=1, snapshot={}))
        session.flush()
        raise RuntimeError("synthetic interruption")

    with pytest.raises(RuntimeError, match="synthetic interruption"):
        apply_effect(effect_factory, context, "evidence:0", {}, write)
    with effect_factory() as session:
        assert session.scalars(select(GroceryEvidence)).all() == []
        assert session.scalars(select(JobEffect)).all() == []


@pytest.mark.parametrize(
    "reference",
    [
        {"kind": "sync", "changed_count": True},
        {"kind": "sync", "changed_count": -1},
        {"kind": "sync", "changed_count": 2_147_483_648},
        {"kind": "evidence", "id": "A" * 64},
        {"kind": "proposal", "id": "invalid"},
        {"kind": "sync", "changed_count": 1, "raw_payload": "synthetic"},
        {"kind": ["sync"], "changed_count": 1},
    ],
)
def test_effect_results_accept_only_bounded_typed_references(
    effect_factory: sessionmaker[Session], reference: dict[str, object]
) -> None:
    context = claim_context(effect_factory)

    def write(session: Session) -> dict[str, object]:
        session.add(GroceryEvidence(id="b" * 64, user_id=1, snapshot={}))
        return reference

    with pytest.raises(ValueError, match="Job effect reference is invalid"):
        apply_effect(effect_factory, context, "evidence:0", {}, write)
    with effect_factory() as session:
        assert session.scalars(select(JobEffect)).all() == []
        assert session.scalars(select(GroceryEvidence)).all() == []


def test_new_york_month_and_freshness_use_current_calculation_time(
    effect_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = NOW
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: clock)
    body = payload()
    context = claim_context(effect_factory, payload=body)
    handler = make_agent_handler(effect_factory, None)
    handler(body, context)
    clock += timedelta(hours=25)
    with pytest.raises(ValueError, match="Spending snapshot is stale"):
        handler(body, context)
    capped = payload(
        request={
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": "2026-09-01",
            "plan_cap_cents": 5000,
        }
    )
    capped_context = claim_context(effect_factory, payload=capped)
    clock = NOW
    handler(capped, capped_context)
    clock += timedelta(hours=25)
    with pytest.raises(JobEffectConflict):
        handler(capped, capped_context)


@pytest.mark.parametrize(
    "mutation", ["expired", "token", "disabled", "cursor", "credential"]
)
def test_sync_rechecks_after_network_without_holding_database_locks(
    effect_factory: sessionmaker[Session], mutation: str
) -> None:
    with effect_factory.begin() as session:
        session.add(
            PlaidItem(
                id="owned-item",
                user_id=1,
                provider_item_id="synthetic-provider",
                credential_ref="synthetic-credential",
            )
        )
    context = claim_context(effect_factory, kind="sync")

    class Provider:
        def sync_page(self, credential_ref: str, cursor: str | None) -> SyncPage:
            with effect_factory.begin() as session:
                owner = session.scalar(
                    select(User).where(User.id == 1).with_for_update(nowait=True)
                )
                job = session.scalar(
                    select(Job)
                    .where(Job.id == context.job_id)
                    .with_for_update(nowait=True)
                )
                item = session.scalar(
                    select(PlaidItem)
                    .where(PlaidItem.id == "owned-item")
                    .with_for_update(nowait=True)
                )
                assert owner is not None and job is not None and item is not None
                if mutation == "expired":
                    job.lease_expires_at = database_utc_now(session) - timedelta(
                        seconds=1
                    )
                elif mutation == "token":
                    job.lease_token = "replacement-token"
                elif mutation == "disabled":
                    owner.status = "disabled"
                elif mutation == "cursor":
                    item.cursor = "winner-cursor"
                    item.last_synced_at = database_utc_now(session)
                else:
                    item.credential_ref = "rotated-synthetic-credential"
            return page(added=(txn("stale-transaction"),), next_cursor="stale-cursor")

    error: type[Exception]
    if mutation == "disabled":
        error = OwnerUnavailableError
    elif mutation in {"cursor", "credential"}:
        error = RetryableJobError
    else:
        error = LeaseLost
    with pytest.raises(error):
        sync_item(effect_factory, "owned-item", Provider(), context=context)
    with effect_factory() as session:
        assert session.scalars(select(PlaidTransaction)).all() == []
        assert session.scalars(select(JobEffect)).all() == []
        item = session.get(PlaidItem, "owned-item")
        assert item is not None
        assert item.cursor == ("winner-cursor" if mutation == "cursor" else None)


def test_sync_effect_replay_precedes_repeat_network_request(
    effect_factory: sessionmaker[Session],
) -> None:
    with effect_factory.begin() as session:
        session.add(
            PlaidItem(
                id="owned-item",
                user_id=1,
                provider_item_id="synthetic-provider",
                credential_ref="synthetic-credential",
            )
        )
    context = claim_context(effect_factory, kind="sync")
    provider = ScriptedProvider([page(added=(txn("one"),), next_cursor="final")])
    assert sync_item(effect_factory, "owned-item", provider, context=context) == 1
    expire(effect_factory, context)
    reclaimed = claim_context(effect_factory, kind="sync", job_id=context.job_id)
    assert sync_item(effect_factory, "owned-item", provider, context=reclaimed) == 1
    assert provider.calls == [("synthetic-credential", None)]
    with effect_factory() as session:
        effects = session.scalars(select(JobEffect)).all()
        assert len(effects) == 1
        assert effects[0].result_reference == {"kind": "sync", "changed_count": 1}


def test_replay_rechecks_the_new_york_month_boundary(
    effect_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = datetime(2026, 10, 1, 3, 59, tzinfo=UTC)
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: clock)
    body = payload(
        spending={
            "period": "2026-09-01",
            "posted_cents": 2500,
            "pending_cents": 400,
            "refreshed_at": clock - timedelta(minutes=1),
        }
    )
    context = claim_context(effect_factory, payload=body)
    handler = make_agent_handler(effect_factory, None)
    handler(body, context)
    clock += timedelta(minutes=1)
    with pytest.raises(ValueError, match="current New York month"):
        handler(body, context)
    with effect_factory() as session:
        assert len(session.scalars(select(JobEffect)).all()) == 1
