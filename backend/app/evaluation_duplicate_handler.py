from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel, StrictInt
from sqlalchemy.orm import Session, sessionmaker

from app.agent.planning_tool import execute_plan
from app.domain.grocery import GroceryRequest
from app.evaluation_inputs import CaseContext
from app.evaluation_plan_inputs import fixture_plan
from app.providers.local_artifacts import ArtifactPut
from app.services.evidence_contract import EvidenceInputs
from app.services.evidence_store import load_evidence, save_plan_evidence
from app.services.handoff_contract import HandoffView
from app.services.handoff_dispatch import dispatch_handoff
from app.services.handoff_intents import prepare_handoff
from app.services.job_delivery import JobHandler
from app.services.shopping_payload import build_shopping_payload, shopping_payload_hash


class ReportStore(Protocol):
    def put_report(self, report: object) -> ArtifactPut: ...


class _Envelope(BaseModel):
    case_id: Literal["P05"]
    user_id: StrictInt


class _CountingLinkProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.payload: dict[str, object] | None = None

    def create_link(self, payload: dict[str, object]) -> str:
        self.calls += 1
        self.payload = payload
        return "https://www.instacart.com/store/shopping_lists/evaluation"


class DuplicateHandler(JobHandler):
    def __init__(
        self,
        factory: sessionmaker[Session],
        context: CaseContext,
        artifact_store: ReportStore,
    ) -> None:
        if context.case_id != "P05":
            raise ValueError("duplicate handler context is invalid")
        self.factory = factory
        self.context = context
        self.artifact_store = artifact_store
        self.provider = _CountingLinkProvider()
        self.handler_calls = 0
        self.artifact_attempts = 0
        self.planning: dict[str, object] | None = None
        self.shopping_payload: dict[str, object] | None = None
        self.evidence_revision_id: str | None = None
        self.handoff: HandoffView | None = None
        self.artifact: ArtifactPut | None = None
        facts = context.inputs
        self._request = GroceryRequest.model_validate(
            {
                "meals": facts.get("meals"),
                "diet": facts.get("diet", "omnivore"),
                "pantry_ingredients": facts.get("pantry_ingredients", []),
                "ingredient_exclusions": facts.get("ingredient_exclusions", []),
                "budget_period": context.period,
                "plan_cap_cents": context.plan_cap_cents,
            }
        )
        self._inputs = EvidenceInputs.model_validate(
            {
                "monthly_limit_cents": facts.get("monthly_limit_cents"),
                "spending": {
                    "period": context.period,
                    "posted_cents": facts.get("posted_cents"),
                    "pending_cents": facts.get("pending_cents"),
                    "refreshed_at": facts.get("spending_refreshed_at"),
                },
                "spending_source": "fixture",
                "calculated_at": facts.get("now"),
                "plan_cap_cents": context.plan_cap_cents,
            }
        )

    def repeat_handoff(self) -> HandoffView:
        if self.shopping_payload is None:
            raise ValueError("duplicate handler has no shopping payload")
        prepared = prepare_handoff(
            self.factory,
            self.context.user_id,
            self.shopping_payload,
            now=self._inputs.calculated_at,
        )
        self.handoff = dispatch_handoff(
            self.factory,
            self.provider,
            self.context.user_id,
            prepared.id,
            now=lambda: self._inputs.calculated_at,
        )
        return self.handoff

    def __call__(
        self, payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        envelope = _Envelope.model_validate(payload)
        if envelope.user_id != self.context.user_id:
            raise ValueError("duplicate handler owner does not match")
        self.handler_calls += 1
        heartbeat()
        planning = execute_plan(
            self._request.model_dump(mode="json"),
            self.context.budget,
            self.context.period,
            user_id=self.context.user_id,
        )
        self.planning = planning
        current_plan = fixture_plan(self.context.inputs)
        self.shopping_payload = build_shopping_payload(current_plan)
        heartbeat()
        revision = save_plan_evidence(
            self.factory, self.context.user_id, planning, self._inputs
        )
        if load_evidence(self.factory, self.context.user_id, revision) is None:
            raise RuntimeError("duplicate handler evidence is missing")
        self.evidence_revision_id = revision
        heartbeat()
        handoff = self.repeat_handoff()
        heartbeat()
        summary: dict[str, object] = {
            "case_id": self.context.case_id,
            "planning": {key: planning[key] for key in ("request", "plan", "budget")},
            "evidence_revision_id": revision,
            "handoff": {
                "id": handoff.id,
                "state": handoff.state,
                "attempts": handoff.attempts,
                "payload_hash": shopping_payload_hash(self.shopping_payload),
            },
            "handler_calls": self.handler_calls,
            "provider_calls": self.provider.calls,
            "artifact_attempts": self.artifact_attempts + 1,
        }
        self.artifact_attempts += 1
        self.artifact = self.artifact_store.put_report(summary)
        summary["artifact"] = {"key": self.artifact.key, "sha256": self.artifact.sha256}
        heartbeat()
        return summary
