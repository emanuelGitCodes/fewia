import json
import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import Connection, Engine, create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_chat_job import FailLLM, FakeLLM, _planner_then_final, _reply, chat_payload
from test_job_effects import claim_context, expire
from test_plan_job import NOW, expected_plan, payload, pure_context

from app import models
from app.agent.chat_loop import ChatUnavailable
from app.consume_jobs import main as consume_main
from app.db import Base
from app.evidence_models import GroceryEvidence
from app.job_effect_models import JobEffect
from app.job_models import Job, JobOutbox
from app.plan_models import PlanProposal, PlanRevision
from app.providers.local_sqs_consumer import QueueMessage
from app.services import chat_job as chat_job_module
from app.services import plan_job as plan_job_module
from app.services.agent_jobs import make_agent_handler
from app.services.evidence_store import load_evidence
from app.services.job_consumer import process_one
from app.services.job_delivery import JobFailure, LeaseLost
from app.services.job_submission import create_job
from app.services.model_cost import (
    ModelBudgetExhausted,
    ModelCapacityUnavailable,
    ModelCostError,
    ModelCostLedger,
    Reservation,
)
from app.services.model_cost_rates import RuntimeRates
from app.services.security_admission import database_utc_now


@pytest.fixture()
def evidence_engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "agent-jobs.db"
    test_engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
        isolation_level=None,
    )

    @event.listens_for(test_engine, "connect")
    def enable_foreign_keys(
        dbapi_connection: sqlite3.Connection, connection_record: object
    ) -> None:
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")

    @event.listens_for(test_engine, "begin")
    def begin_sqlite_transaction(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    tables = [
        models.User.__table__,
        GroceryEvidence.__table__,
        Job.__table__,
        JobOutbox.__table__,
        JobEffect.__table__,
        PlanRevision.__table__,
        PlanProposal.__table__,
    ]
    Base.metadata.create_all(test_engine, tables=tables)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine, tables=tables)
        test_engine.dispose()


@pytest.fixture()
def factory(evidence_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=evidence_engine, expire_on_commit=False)


def seed_user(factory: sessionmaker[Session]) -> None:
    with factory.begin() as session:
        session.add(models.User(id=1, display_name="Owner"))


def count_rows(factory: sessionmaker[Session]) -> int:
    with factory() as session:
        return int(
            session.scalar(select(func.count()).select_from(GroceryEvidence)) or 0
        )


def freeze_clocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plan_job_module, "_utc_now", lambda: NOW)
    monkeypatch.setattr(chat_job_module, "_utc_now", lambda: NOW)


class FakeQueue:
    def __init__(self, body: str) -> None:
        self.message = QueueMessage(body=body, receipt_handle="receipt")
        self.acknowledged = False

    def receive(self) -> QueueMessage:
        return self.message

    def acknowledge(self, message: QueueMessage) -> None:
        assert message == self.message
        self.acknowledged = True

    def extend(self, message: QueueMessage, seconds: int) -> None:
        assert message == self.message
        del seconds


def submit_agent_job(
    factory: sessionmaker[Session], body: dict[str, object], *, user_id: int = 1
) -> str:
    with factory.begin() as session:
        job, created = create_job(session, user_id, "agent", str(uuid4()), body)
        assert created is True
        return job.id


def stored_job(factory: sessionmaker[Session], job_id: str) -> Job:
    with factory() as session:
        job = session.get(Job, job_id)
        assert job is not None
        return job


def test_handler_routes_plan_and_chat(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    provider = FakeLLM(_planner_then_final())
    handler = make_agent_handler(factory, provider)
    plan_body = payload()
    expected = expected_plan(plan_body)

    plan_result = handler(plan_body, claim_context(factory, payload=plan_body))

    assert plan_result["request"] == expected["request"]
    assert plan_result["plan"] == expected["plan"]
    assert plan_result["evidence_id"] == expected["evidence_id"]
    revision = plan_result["evidence_revision_id"]
    assert isinstance(revision, str)
    assert len(revision) == 64
    assert load_evidence(factory, 1, revision) is not None
    assert count_rows(factory) == 1

    chat_result = handler(
        chat_payload(), claim_context(factory, payload=chat_payload())
    )
    assert chat_result["status"] == "planned"
    assert chat_result["plan"] is not None
    chat_revision = chat_result["evidence_revision_id"]
    assert isinstance(chat_revision, str)
    assert load_evidence(factory, 1, chat_revision) is not None
    assert count_rows(factory) == 2
    assert len(provider.requests) == 1


def test_process_one_succeeds_for_plan_and_chat(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    provider = FakeLLM(_planner_then_final())
    handler = make_agent_handler(factory, provider)
    plan_body = plan_job_module.PlanJobInput.model_validate(payload()).model_dump(
        mode="json"
    )
    chat_body = chat_job_module.ChatJobInput.model_validate(chat_payload()).model_dump(
        mode="json"
    )
    plan_id = submit_agent_job(factory, plan_body)
    chat_id = submit_agent_job(factory, chat_body)
    plan_queue = FakeQueue(json.dumps({"job_id": plan_id}))
    chat_queue = FakeQueue(json.dumps({"job_id": chat_id}))
    assert (
        process_one(
            factory, plan_queue, "agent", handler, now=lambda: datetime.now(UTC)
        )
        == "succeeded"
    )
    assert (
        process_one(
            factory, chat_queue, "agent", handler, now=lambda: datetime.now(UTC)
        )
        == "succeeded"
    )
    plan_job_row = stored_job(factory, plan_id)
    chat_job_row = stored_job(factory, chat_id)
    assert plan_job_row.status == "succeeded"
    assert chat_job_row.status == "succeeded"
    assert plan_job_row.result is not None
    assert chat_job_row.result is not None


def test_handler_rejects_unknown_operation_before_external_work(
    factory: sessionmaker[Session],
) -> None:
    handler = make_agent_handler(factory, FailLLM())
    with pytest.raises(ValueError, match="operation is invalid") as caught:
        handler({"operation": "purchase"}, pure_context())
    assert "purchase" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert count_rows(factory) == 0


def test_handler_plan_recorder_persists_without_provider(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    handler = make_agent_handler(factory, None)
    result = handler(payload(), claim_context(factory, payload=payload()))
    revision = result["evidence_revision_id"]
    assert isinstance(revision, str)
    snapshot = load_evidence(factory, 1, revision)
    assert snapshot is not None
    assert snapshot["planning"]["spending_source"] == "fixture"


def test_handler_does_not_fake_chat_when_provider_missing(
    factory: sessionmaker[Session],
) -> None:
    handler = make_agent_handler(factory, None)
    with pytest.raises(ChatUnavailable, match="unavailable") as caught:
        handler(chat_payload(), pure_context())
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert count_rows(factory) == 0


@pytest.mark.parametrize("error", [ModelBudgetExhausted(), ModelCapacityUnavailable()])
def test_handler_maps_model_denial_to_static_job_failure(
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    error: ModelCostError,
) -> None:
    freeze_clocks(monkeypatch)
    handler = make_agent_handler(factory, FakeLLM([error]))
    with pytest.raises(JobFailure) as caught:
        handler(chat_payload(), pure_context())
    assert caught.value.error_code == error.code
    assert caught.value.detail == {
        "code": error.code,
        "retry_guidance": error.retry_guidance,
    }
    assert caught.value.__context__ is None
    assert count_rows(factory) == 0


def test_handler_maps_technical_model_cost_failure_to_unavailable(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    with pytest.raises(ChatUnavailable, match="^The language model is unavailable.$"):
        make_agent_handler(factory, FakeLLM([ModelCostError()]))(
            chat_payload(), pure_context()
        )
    assert count_rows(factory) == 0


@pytest.mark.parametrize("state", ["active", "expired", "disabled", "replaced"])
def test_cost_provider_uses_shared_fence_before_network(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    context = claim_context(factory, payload=chat_payload())
    with factory.begin() as session:
        job = session.get(Job, context.job_id)
        owner = session.get(models.User, context.user_id)
        assert job is not None and owner is not None
        if state == "expired":
            job.lease_expires_at = database_utc_now(session)
        elif state == "disabled":
            owner.status = "disabled"
        elif state == "replaced":
            job.lease_token = "replacement"
    attempts: list[int] = []

    def reserve(self: ModelCostLedger, **kwargs: object) -> Reservation:
        fence = cast(Callable[[Session], int], kwargs["fence"])
        with factory.begin() as session:
            attempts.append(fence(session))
        raise ModelBudgetExhausted()

    monkeypatch.setattr(ModelCostLedger, "reserve", reserve)
    provider = FakeLLM([])
    handler = make_agent_handler(factory, provider, rates=cast(RuntimeRates, object()))
    expected = JobFailure if state == "active" else LeaseLost
    with pytest.raises(expected):
        handler(chat_payload(), context)
    assert attempts == ([context.attempt] if state == "active" else [])
    assert provider.requests == []


@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("disable", [False, True])
def test_provider_failure_or_cancellation_keeps_stale_owner_fenced(
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
    disable: bool,
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    context = claim_context(factory, payload=chat_payload())
    settlements: list[int | None] = []

    def reserve(self: ModelCostLedger, **kwargs: object) -> Reservation:
        fence = cast(Callable[[Session], int], kwargs["fence"])
        with factory.begin() as session:
            attempt = fence(session)
        return Reservation(
            "reservation",
            context.job_id,
            context.user_id,
            attempt,
            1,
            "gpt-6-luna",
            "global",
            "sha256:" + "a" * 64,
            1000,
        )

    def settle(
        self: ModelCostLedger, reservation: Reservation, cost: int | None
    ) -> None:
        settlements.append(cost)

    class FailingLLM(FakeLLM):
        def converse(
            self,
            system_prompt: str,
            messages: list[dict[str, object]],
            tools: list[dict[str, object]],
        ) -> dict[str, object]:
            with factory.begin() as session:
                job = session.get(Job, context.job_id)
                owner = session.get(models.User, context.user_id)
                assert job is not None and owner is not None
                if disable:
                    owner.status = "disabled"
                else:
                    job.lease_expires_at = database_utc_now(session)
            return super().converse(system_prompt, messages, tools)

    monkeypatch.setattr(ModelCostLedger, "reserve", reserve)
    monkeypatch.setattr(ModelCostLedger, "settle", settle)
    error = KeyboardInterrupt() if cancel else RuntimeError("Synthetic failure")
    provider = FailingLLM([error])
    handler = make_agent_handler(factory, provider, rates=cast(RuntimeRates, object()))
    with pytest.raises(KeyboardInterrupt if cancel else ChatUnavailable):
        handler(chat_payload(), context)
    assert settlements == [None]
    with pytest.raises(LeaseLost):
        handler(chat_payload(), context)
    assert len(provider.requests) == 1
    assert settlements == [None]


def test_handler_invalid_payloads_fail_closed(
    factory: sessionmaker[Session],
) -> None:
    handler = make_agent_handler(factory, FailLLM())
    with pytest.raises(ValidationError):
        handler(payload(unexpected="value"), pure_context())
    with pytest.raises(ValidationError):
        handler(chat_payload(user_id=1), pure_context())
    assert count_rows(factory) == 0


def test_bounded_cli_persists_evidence_for_the_claimed_owner(
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    with factory.begin() as session:
        session.add(models.User(id=2, display_name="Other owner"))
    body = plan_job_module.PlanJobInput.model_validate(payload()).model_dump(
        mode="json"
    )
    job_id = submit_agent_job(factory, body, user_id=2)
    queue = FakeQueue(json.dumps({"job_id": job_id}))
    code = consume_main(
        ["--endpoint", "http://127.0.0.1:4566", "--max-messages", "1"],
        factory=factory,
        consumer_factory=lambda endpoint, kind: queue,
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["counts"]["succeeded"] == 1
    job = stored_job(factory, job_id)
    assert job.result is not None
    revision = job.result["evidence_revision_id"]
    assert isinstance(revision, str)
    assert load_evidence(factory, 2, revision) is not None
    assert load_evidence(factory, 1, revision) is None
    with factory() as session:
        effect = session.get(JobEffect, (job_id, "evidence:0"))
        assert effect is not None and effect.user_id == 2


def _seed_chat_owners(factory: sessionmaker[Session]) -> tuple[UUID, UUID]:
    ids = (uuid4(), uuid4())
    snapshot: dict[str, object] = {
        "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
        "pantry_ingredient_ids": [],
        "plan_cap_cents": None,
    }
    with factory.begin() as session:
        session.add_all(
            [
                models.User(id=1, display_name="One"),
                models.User(id=2, display_name="Two"),
            ]
        )
        session.flush()
        session.add_all(
            [
                PlanRevision(id=ids[0], user_id=1, snapshot=snapshot),
                PlanRevision(id=ids[1], user_id=2, snapshot=snapshot),
            ]
        )
    return ids


@pytest.mark.parametrize(
    "reference",
    [
        "foreign_top",
        "foreign_embedded",
        "missing",
        "mismatched",
        "altered",
        "previous",
        "previous_missing",
        "previous_running",
        "previous_sync",
    ],
)
def test_chat_refuses_unowned_or_mismatched_references_before_provider(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, reference: str
) -> None:
    freeze_clocks(monkeypatch)
    foreign, owned = _seed_chat_owners(factory)
    snapshot: dict[str, object] = {
        "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
        "pantry_ingredient_ids": [],
        "plan_cap_cents": None,
    }
    fields: dict[str, object]
    if reference.startswith("previous"):
        prior = submit_agent_job(
            factory, {}, user_id=1 if reference == "previous" else 2
        )
        with factory.begin() as session:
            job = session.get(Job, prior)
            assert job is not None
            job.status = "queued" if reference == "previous_running" else "succeeded"
            if reference == "previous_sync":
                job.kind = "sync"
            job.result = {}
        fields = {
            "previous_job_id": str(uuid4())
            if reference == "previous_missing"
            else prior
        }
    elif reference == "foreign_top":
        fields = {"plan_revision_id": str(foreign)}
    elif reference == "foreign_embedded":
        fields = {"plan_revision": {"id": str(foreign), "snapshot": snapshot}}
    elif reference == "missing":
        fields = {"plan_revision_id": str(uuid4())}
    else:
        fields = {
            "plan_revision_id": str(owned),
            "plan_revision": {
                "id": str(foreign if reference == "mismatched" else owned),
                "snapshot": {**snapshot, "plan_cap_cents": 100},
            },
        }
    body = chat_job_module.ChatJobInput.model_validate(
        chat_payload(**fields)
    ).model_dump(mode="json")
    job_id = submit_agent_job(factory, body, user_id=2)
    provider = FakeLLM([])
    outcome = process_one(
        factory,
        FakeQueue(json.dumps({"job_id": job_id})),
        "agent",
        make_agent_handler(factory, provider),
    )
    assert outcome == "handler_failed"
    assert provider.requests == []
    assert count_rows(factory) == 0


def test_chat_proposal_uses_owned_embedded_revision_and_replays(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    _, owned = _seed_chat_owners(factory)
    with factory() as session:
        base = session.get(PlanRevision, owned)
        assert base is not None
        snapshot = base.snapshot
    body = chat_payload(plan_revision={"id": str(owned), "snapshot": snapshot})
    context = claim_context(factory, user_id=2, payload=body)
    replies = _proposal_replies("provider-call-a")
    first = make_agent_handler(factory, FakeLLM(replies))(body, context)
    expire(factory, context)
    reclaimed = claim_context(factory, user_id=2, job_id=context.job_id)
    second = make_agent_handler(factory, FakeLLM(_proposal_replies("provider-call-b")))(
        body, reclaimed
    )
    assert first["proposal_id"] == second["proposal_id"]
    with factory() as session:
        proposals = session.scalars(select(PlanProposal)).all()
        assert len(proposals) == 1
        assert proposals[0].user_id == 2
        assert proposals[0].base_plan_revision_id == owned


def _proposal_replies(tool_id: str) -> list[dict[str, object] | BaseException]:
    return [
        _reply(
            [
                {
                    "toolUse": {
                        "toolUseId": tool_id,
                        "name": "propose_plan_change",
                        "input": {
                            "operations": [
                                {
                                    "op": "set_servings",
                                    "recipe_id": "bean_tacos",
                                    "servings": 3,
                                }
                            ]
                        },
                    }
                }
            ],
            "tool_use",
        ),
        _reply([{"text": "Done."}], "end_turn"),
    ]


@pytest.mark.parametrize("kind", ["evidence", "proposal"])
def test_repeated_chat_effects_use_per_job_ordinals(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    freeze_clocks(monkeypatch)
    _, owned = _seed_chat_owners(factory)
    with factory() as session:
        revision = session.get(PlanRevision, owned)
        assert revision is not None
        snapshot = revision.snapshot
    body = chat_payload(plan_revision={"id": str(owned), "snapshot": snapshot})
    context = claim_context(factory, user_id=2, payload=body)
    calls: list[dict[str, object]] = []
    for servings in (2, 3):
        arguments: dict[str, object]
        if kind == "proposal":
            name = "propose_plan_change"
            arguments = {
                "operations": [
                    {
                        "op": "set_servings",
                        "recipe_id": "bean_tacos",
                        "servings": servings,
                    }
                ]
            }
        else:
            name = "plan_groceries"
            arguments = {
                "meals": [{"recipe_id": "bean_tacos", "servings": servings}],
                "budget_period": "2026-09-01",
            }
        calls.append(
            {
                "toolUse": {
                    "toolUseId": f"provider-call-{servings}",
                    "name": name,
                    "input": arguments,
                }
            }
        )
    provider = FakeLLM(
        [_reply(calls, "tool_use"), _reply([{"text": "Done."}], "end_turn")]
    )
    make_agent_handler(factory, provider)(body, context)
    with factory() as session:
        effects = session.scalars(
            select(JobEffect).where(JobEffect.job_id == context.job_id)
        ).all()
        assert {effect.effect_key for effect in effects} == {f"{kind}:0", f"{kind}:1"}
        assert len({str(effect.result_reference["id"]) for effect in effects}) == 2


def test_two_owner_chat_consumer_persists_owned_evidence(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    _seed_chat_owners(factory)
    body = chat_job_module.ChatJobInput.model_validate(chat_payload()).model_dump(
        mode="json"
    )
    job_id = submit_agent_job(factory, body, user_id=2)
    queue = FakeQueue(json.dumps({"job_id": job_id}))
    provider = FakeLLM(_planner_then_final())
    assert (
        process_one(factory, queue, "agent", make_agent_handler(factory, provider))
        == "succeeded"
    )
    job = stored_job(factory, job_id)
    assert job.result is not None
    revision = job.result["evidence_revision_id"]
    assert isinstance(revision, str)
    evidence = load_evidence(factory, 2, revision)
    assert evidence is not None
    assert evidence["planning"]["evidence_id"] == job.result["evidence_id"]
    assert load_evidence(factory, 1, revision) is None
    assert queue.acknowledged


def test_consumer_does_not_acknowledge_lease_lost_after_provider(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_clocks(monkeypatch)
    seed_user(factory)
    body = chat_job_module.ChatJobInput.model_validate(chat_payload()).model_dump(
        mode="json"
    )
    job_id = submit_agent_job(factory, body)
    queue = FakeQueue(json.dumps({"job_id": job_id}))

    class ExpiringLLM(FakeLLM):
        def converse(
            self,
            system_prompt: str,
            messages: list[dict[str, object]],
            tools: list[dict[str, object]],
        ) -> dict[str, object]:
            with factory.begin() as session:
                job = session.get(Job, job_id)
                assert job is not None
                job.lease_expires_at = database_utc_now(session)
            return super().converse(system_prompt, messages, tools)

    handler = make_agent_handler(factory, ExpiringLLM(_planner_then_final()))
    assert process_one(factory, queue, "agent", handler) == "lease_lost"
    assert queue.acknowledged is False
    assert count_rows(factory) == 0
