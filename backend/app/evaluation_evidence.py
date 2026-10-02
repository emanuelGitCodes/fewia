import sqlite3
from copy import deepcopy
from types import TracebackType

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.evaluation_inputs import (
    INVALID_INPUT_ERROR,
    CaseContext,
    EvaluationInputError,
    prepare_case,
)
from app.evidence_models import GroceryEvidence
from app.models import User
from app.services.evidence_contract import EvidenceInputs
from app.services.evidence_store import load_evidence, save_plan_evidence


class EvaluationEvidence:
    """Record fixture evidence in a dedicated local SQLite database."""

    def __init__(self, context: CaseContext) -> None:
        validated = prepare_case(
            {
                "id": context.case_id,
                "messages": [
                    {"role": "user", "content": message}
                    for message in context.messages
                ],
                "inputs": context.inputs,
            }
        )
        if validated != context:
            raise EvaluationInputError(INVALID_INPUT_ERROR)
        source = validated.inputs
        try:
            self._inputs = EvidenceInputs.model_validate(
                {
                    "monthly_limit_cents": source["monthly_limit_cents"],
                    "spending": {
                        "period": validated.period,
                        "posted_cents": source["posted_cents"],
                        "pending_cents": source["pending_cents"],
                        "refreshed_at": source["spending_refreshed_at"],
                    },
                    "spending_source": "fixture",
                    "calculated_at": source["now"],
                    "plan_cap_cents": validated.plan_cap_cents,
                }
            )
        except (KeyError, TypeError, ValueError):
            raise EvaluationInputError(INVALID_INPUT_ERROR) from None
        self._user_id = validated.user_id
        self._engine: Engine | None = None
        self._factory: sessionmaker[Session] | None = None
        self._records: dict[str, dict[str, object]] = {}
        self._entered = False

    def __enter__(self) -> "EvaluationEvidence":
        if self._entered:
            raise RuntimeError("evaluation evidence context was already entered")
        self._entered = True
        engine = create_engine("sqlite://", poolclass=StaticPool)
        self._engine = engine

        try:

            @event.listens_for(engine, "connect")
            def enable_foreign_keys(
                connection: sqlite3.Connection, connection_record: object
            ) -> None:
                del connection_record
                connection.execute("PRAGMA foreign_keys=ON")

            User.metadata.create_all(
                engine, tables=[User.__table__, GroceryEvidence.__table__]
            )
            factory = sessionmaker(bind=engine, expire_on_commit=False)
            with factory.begin() as session:
                session.add(User(id=self._user_id, display_name="Evaluation demo"))
            self._factory = factory
        except BaseException:
            self._close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._close()

    def _close(self) -> None:
        engine = self._engine
        self._factory = None
        self._engine = None
        if engine is not None:
            engine.dispose()

    def record(self, planning: dict[str, object]) -> str:
        factory = self._factory
        if factory is None:
            raise RuntimeError("evaluation evidence context is not active")
        revision_id = save_plan_evidence(factory, self._user_id, planning, self._inputs)
        snapshot = load_evidence(factory, self._user_id, revision_id)
        if snapshot is None:
            raise RuntimeError("evaluation evidence row is missing")
        self._records[revision_id] = {
            "revision_id": revision_id,
            "user_id": self._user_id,
            "snapshot": deepcopy(snapshot),
            "storage": "local_sqlite",
        }
        return revision_id

    def snapshots(self) -> list[dict[str, object]]:
        return [deepcopy(self._records[key]) for key in sorted(self._records)]
