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
    evidence_id = _evidence_id(user_id, snapshot)
    conflict: EvidenceConflict | None = None
    stored: str | None = None
    with factory() as session:
        _insert_ignore(session, evidence_id, user_id, snapshot)
        row = session.scalar(
            select(GroceryEvidence).where(GroceryEvidence.id == evidence_id)
        )
        if row is None:
            raise RuntimeError(_MISSING)
        payload: dict[str, object] | None
        try:
            payload = _json_object(row.snapshot)
            owner = row.user_id
        except (TypeError, ValueError):
            payload = None
            owner = None
        if (
            payload is None
            or owner != user_id
            or canonical_json(payload) != canonical_json(snapshot)
        ):
            conflict = EvidenceConflict(_CONFLICT)
        else:
            session.commit()
            stored = evidence_id
    if conflict is not None:
        raise conflict
    if stored is None:
        raise RuntimeError(_MISSING)
    return stored


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
