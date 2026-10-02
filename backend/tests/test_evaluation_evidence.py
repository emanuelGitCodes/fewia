from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from sqlalchemy import Engine, create_engine, event, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from test_evidence_contract import genuine_planning, inputs

from app.evaluation_evidence import EvaluationEvidence
from app.evaluation_inputs import CaseContext, EvaluationInputError, prepare_case
from app.evidence_models import GroceryEvidence
from app.models import User
from app.services.evidence_contract import EvidenceInputs, canonical_json
from app.services.evidence_store import EvidenceConflict, load_evidence


@pytest.fixture()
def case() -> tuple[CaseContext, EvidenceInputs, dict[str, object]]:
    parsed = inputs().model_copy(update={"spending_source": "fixture"})
    context = prepare_case(
        {
            "id": "local-bean-taco-evidence",
            "messages": [{"role": "user", "content": "Plan bean tacos."}],
            "inputs": {
                "now": parsed.calculated_at.isoformat(),
                "budget_period": parsed.spending.period.isoformat(),
                "spending_period": parsed.spending.period.isoformat(),
                "monthly_limit_cents": parsed.monthly_limit_cents,
                "posted_cents": parsed.spending.posted_cents,
                "pending_cents": parsed.spending.pending_cents,
                "spending_refreshed_at": parsed.spending.refreshed_at.isoformat(),
                "plan_cap_cents": parsed.plan_cap_cents,
                "user_id": 7,
            },
        }
    )
    planning = genuine_planning(user_id=context.user_id, evidence_inputs=parsed)
    return context, parsed, planning


def active_factory(recorder: EvaluationEvidence) -> sessionmaker[Session]:
    factory = recorder._factory
    assert factory is not None
    return factory


def row_count(recorder: EvaluationEvidence) -> int:
    with active_factory(recorder)() as session:
        count = session.scalar(select(func.count()).select_from(GroceryEvidence))
    assert count is not None
    return count


def tamper_total(payload: dict[str, object]) -> bool:
    for key, value in payload.items():
        if "total" in key and "cents" in key and type(value) is int:
            payload[key] = value + 1
            return True
        if isinstance(value, dict) and tamper_total(cast(dict[str, object], value)):
            return True
    return False


def test_actual_bean_taco_evidence(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, parsed, planning = case
    encoded = canonical_json(planning).lower()
    assert "bean" in encoded and "taco" in encoded
    recorder = EvaluationEvidence(context)
    with recorder:
        engine = recorder._engine
        assert engine is not None
        assert inspect(engine).get_table_names() == ["grocery_evidence", "users"]
        revision = recorder.record(planning)
        snapshot = load_evidence(active_factory(recorder), context.user_id, revision)
        assert snapshot == {
            "planning": planning,
            "budget_inputs": parsed.model_dump(mode="json"),
        }
        assert recorder.snapshots() == [
            {
                "revision_id": revision,
                "user_id": context.user_id,
                "snapshot": snapshot,
                "storage": "local_sqlite",
            }
        ]
        with active_factory(recorder)() as session:
            assert session.get(User, context.user_id) is not None
            assert session.get(User, 1) is None
    assert recorder._engine is None
    assert recorder._factory is None
    assert recorder.snapshots()[0]["revision_id"] == revision


def test_replay_deduplicates(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, planning = case
    with EvaluationEvidence(context) as recorder:
        first = recorder.record(planning)
        assert recorder.record(deepcopy(planning)) == first
        assert row_count(recorder) == 1
        assert len(recorder.snapshots()) == 1


def test_tampered_totals_are_rejected(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, planning = case
    tampered = deepcopy(planning)
    assert tamper_total(tampered)
    with EvaluationEvidence(context) as recorder:
        with pytest.raises(ValueError, match="evidence snapshot is invalid"):
            recorder.record(tampered)
        assert row_count(recorder) == 0
        assert recorder.snapshots() == []
        recorder.record(planning)
        assert row_count(recorder) == 1


def test_owner_scoped_lookup(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, planning = case
    with EvaluationEvidence(context) as recorder:
        revision = recorder.record(planning)
        factory = active_factory(recorder)
        assert load_evidence(factory, context.user_id + 1, revision) is None
        assert load_evidence(factory, context.user_id, revision) is not None


def test_snapshot_mutation_cannot_modify_store(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, planning = case
    with EvaluationEvidence(context) as recorder:
        revision = recorder.record(planning)
        expected = recorder.snapshots()
        changed = recorder.snapshots()
        snapshot = cast(dict[str, object], changed[0]["snapshot"])
        stored_plan = cast(dict[str, object], snapshot["planning"])
        stored_plan.clear()
        changed[0]["storage"] = "forged"
        changed.clear()
        planning.clear()
        assert recorder.snapshots() == expected
        assert load_evidence(active_factory(recorder), context.user_id, revision) == (
            expected[0]["snapshot"]
        )


def test_conflict_does_not_record_an_id(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, planning = case
    with EvaluationEvidence(context) as recorder:
        revision = recorder.record(planning)
    with EvaluationEvidence(context) as recorder:
        with active_factory(recorder).begin() as session:
            session.add(
                GroceryEvidence(
                    id=revision, user_id=context.user_id, snapshot={"forged": True}
                )
            )
        with pytest.raises(EvidenceConflict, match="evidence snapshot conflicts"):
            recorder.record(planning)
        assert recorder.snapshots() == []
        assert row_count(recorder) == 1
        assert load_evidence(active_factory(recorder), context.user_id, revision) == {
            "forged": True
        }


def test_cleanup_on_raised_exception(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, planning = case
    recorder = EvaluationEvidence(context)
    disposed: list[Engine] = []
    with pytest.raises(RuntimeError, match="evaluation failed"):
        with recorder:
            engine = recorder._engine
            assert engine is not None

            @event.listens_for(engine, "engine_disposed")
            def track_disposal(disposed_engine: Engine) -> None:
                disposed.append(disposed_engine)

            recorder.record(planning)
            raise RuntimeError("evaluation failed")
    assert disposed == [engine]
    assert recorder._engine is None
    assert recorder._factory is None
    with pytest.raises(RuntimeError, match="context is not active"):
        recorder.record(planning)


def test_invalid_context_is_rejected(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, _ = case
    with pytest.raises(EvaluationInputError, match="evaluation inputs are invalid"):
        EvaluationEvidence(replace(context, user_id=context.user_id + 1))


def test_cleanup_on_setup_failure(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, _, _ = case
    recorder = EvaluationEvidence(context)
    created: list[Engine] = []
    disposed: list[Engine] = []

    def local_engine(url: str, **kwargs: object) -> Engine:
        engine = create_engine(url, **kwargs)
        created.append(engine)

        @event.listens_for(engine, "engine_disposed")
        def track_disposal(disposed_engine: Engine) -> None:
            disposed.append(disposed_engine)

        return engine

    def fail_schema(engine: Engine, **kwargs: object) -> None:
        raise RuntimeError("schema failed")

    monkeypatch.setattr("app.evaluation_evidence.create_engine", local_engine)
    monkeypatch.setattr(User.metadata, "create_all", fail_schema)
    with pytest.raises(RuntimeError, match="schema failed"):
        with recorder:
            pytest.fail("The context accepted failed setup.")
    assert len(created) == 1
    assert disposed == created
    assert recorder._engine is None
    assert recorder._factory is None
    assert recorder.snapshots() == []


def test_context_mutation_does_not_change_captured_inputs(
    case: tuple[CaseContext, EvidenceInputs, dict[str, object]],
) -> None:
    context, _, planning = case
    recorder = EvaluationEvidence(context)
    context.inputs["posted_cents"] = 99_999
    context.inputs["user_id"] = 99
    with recorder:
        recorder.record(planning)
        assert recorder.snapshots()[0]["user_id"] == context.user_id
