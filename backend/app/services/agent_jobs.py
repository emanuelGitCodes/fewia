from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.agent.chat_loop import ChatUnavailable
from app.agent.provider import LLMProvider
from app.services.chat_job import chat_job
from app.services.evidence_contract import EvidenceInputs
from app.services.evidence_store import save_plan_evidence
from app.services.job_delivery import JobHandler
from app.services.plan_job import PlanJobInput, plan_job

_UNAVAILABLE = "The language model is unavailable."
_OPERATION = "operation is invalid"
_DEMO_USER_ID = 1


def make_agent_handler(
    factory: sessionmaker[Session],
    provider: LLMProvider | None,
) -> JobHandler:
    def record_evidence(
        planning: dict[str, object],
        parsed: PlanJobInput,
        clock: datetime,
    ) -> str:
        inputs = EvidenceInputs(
            monthly_limit_cents=parsed.monthly_limit_cents,
            spending=parsed.spending,
            spending_source=parsed.spending_source,
            calculated_at=clock,
            plan_cap_cents=parsed.request.plan_cap_cents,
        )
        return save_plan_evidence(factory, _DEMO_USER_ID, planning, inputs)

    def handle(
        payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]:
        if payload.get("operation") == "chat":
            if provider is None:
                raise ChatUnavailable(_UNAVAILABLE)
            return chat_job(payload, heartbeat, provider=provider, factory=factory)
        if "operation" in payload:
            raise ValueError(_OPERATION)
        return plan_job(
            payload,
            heartbeat,
            record_evidence=record_evidence,
        )

    return handle
