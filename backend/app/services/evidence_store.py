import hashlib
import json
from typing import cast

from sqlalchemy import Insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from app.evidence_models import GroceryEvidence
from app.services.evidence_contract import (
    EvidenceInputs,
    canonical_json,
    normalize_snapshot,
)
from app.services.job_delivery import JobContext
from app.services.job_effects import apply_effect

_CONFLICT = "evidence snapshot conflicts"
_USER_ERROR = "user_id is invalid"
_MISSING = "evidence row is missing"


class EvidenceConflict(ValueError):
    """An existing evidence row does not match this snapshot."""


def _json_object(value: object) -> dict[str, object]:
    copied = json.loads(canonical_json(value))
    if not isinstance(copied, dict):
        raise ValueError(_CONFLICT)
    return cast(dict[str, object], copied)


def _evidence_id(user_id: int, snapshot: dict[str, object]) -> str:
    return hashlib.sha256(
        canonical_json({"user_id": user_id, "snapshot": snapshot}).encode("utf-8")
    ).hexdigest()


def _insert_ignore(
    session: Session, evidence_id: str, user_id: int, snapshot: dict[str, object]
) -> None:
    dialect = session.get_bind().dialect.name
    statement: Insert
    if dialect == "postgresql":
        statement = (
            pg_insert(GroceryEvidence)
            .values(id=evidence_id, user_id=user_id, snapshot=snapshot)
            .on_conflict_do_nothing(index_elements=["id"])
        )
    elif dialect == "sqlite":
        statement = (
            sqlite_insert(GroceryEvidence)
            .values(id=evidence_id, user_id=user_id, snapshot=snapshot)
            .on_conflict_do_nothing(index_elements=["id"])
        )
    else:
        raise ValueError("database dialect is unsupported")
    session.execute(statement)


def save_plan_evidence(
    factory: sessionmaker[Session],
    user_id: int,
    planning: dict[str, object],
    inputs: EvidenceInputs,
) -> str:
    snapshot = _json_object(normalize_snapshot(user_id, planning, inputs))
    with factory.begin() as session:
        return persist_snapshot(session, user_id, snapshot)


def persist_snapshot(
    session: Session, user_id: int, snapshot: dict[str, object]
) -> str:
    """Persist a normalized immutable snapshot in the caller's transaction."""
    evidence_id = _evidence_id(user_id, snapshot)
    _insert_ignore(session, evidence_id, user_id, snapshot)
    row = session.scalar(
        select(GroceryEvidence).where(GroceryEvidence.id == evidence_id)
    )
    if row is None:
        raise RuntimeError(_MISSING)
    try:
        payload = _json_object(row.snapshot)
    except (TypeError, ValueError):
        raise EvidenceConflict(_CONFLICT) from None
    if row.user_id != user_id or canonical_json(payload) != canonical_json(snapshot):
        raise EvidenceConflict(_CONFLICT)
    return evidence_id


def save_job_plan_evidence(
    factory: sessionmaker[Session],
    context: JobContext,
    effect_key: str,
    planning: dict[str, object],
    inputs: EvidenceInputs,
) -> str:
    snapshot = _json_object(normalize_snapshot(context.user_id, planning, inputs))
    budget_inputs = inputs.model_dump(mode="json", exclude={"calculated_at"})

    def write(session: Session) -> dict[str, object]:
        return {
            "kind": "evidence",
            "id": persist_snapshot(session, context.user_id, snapshot),
        }

    reference = apply_effect(
        factory,
        context,
        effect_key,
        {"planning": planning, "budget_inputs": budget_inputs},
        write,
    )
    return cast(str, reference["id"])


def load_evidence(
    factory: sessionmaker[Session], user_id: int, evidence_id: str
) -> dict[str, object] | None:
    if type(user_id) is not int or user_id < 1:
        raise ValueError(_USER_ERROR)
    with factory() as session:
        row = session.scalar(
            select(GroceryEvidence).where(
                GroceryEvidence.id == evidence_id,
                GroceryEvidence.user_id == user_id,
            )
        )
        if row is None:
            return None
        return _json_object(row.snapshot)
