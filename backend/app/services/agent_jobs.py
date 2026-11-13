from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.agent.chat_loop import ChatUnavailable
from app.agent.provider import LLMProvider
from app.services.chat_job import chat_job
from app.services.evidence_contract import EvidenceInputs
from app.services.evidence_store import save_job_plan_evidence
from app.services.job_delivery import JobContext, JobFailure, JobHandler, LeaseLost
from app.services.job_effects import fence_job
from app.services.model_cost import (
    CostControlledProvider,
    ModelBudgetExhausted,
    ModelCapacityUnavailable,
    ModelCostError,
)
from app.services.model_cost_rates import RuntimeRates
from app.services.plan_job import PlanJobInput, plan_job
from app.services.security_admission import OwnerUnavailableError

_UNAVAILABLE = "The language model is unavailable."
_OPERATION = "operation is invalid"


def make_agent_handler(
    factory: sessionmaker[Session],
    provider: LLMProvider | None,
    *,
    rates: RuntimeRates | None = None,
) -> JobHandler:
    def handle(payload: dict[str, object], context: JobContext) -> dict[str, object]:
        if payload.get("operation") == "chat":
            if provider is None:
                raise ChatUnavailable(_UNAVAILABLE)
            selected_provider = provider
            if rates is not None:

                def fence(session: Session) -> int:
                    try:
                        return fence_job(session, context).attempts
                    except OwnerUnavailableError:
                        raise LeaseLost from None

                selected_provider = CostControlledProvider(
                    session_factory=factory,
                    job_id=context.job_id,
                    user_id=context.user_id,
                    fence=fence,
                    provider=provider,
                    rates=rates,
                )
            failure: JobFailure | ChatUnavailable
            try:
                return chat_job(
                    payload, context, provider=selected_provider, factory=factory
                )
            except (ModelBudgetExhausted, ModelCapacityUnavailable) as exc:
                failure = JobFailure(
                    exc.code,
                    {"code": exc.code, "retry_guidance": exc.retry_guidance},
                )
            except ModelCostError:
                failure = ChatUnavailable(_UNAVAILABLE)
            raise failure
        if "operation" in payload:
            raise ValueError(_OPERATION)

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
            return save_job_plan_evidence(
                factory, context, "evidence:0", planning, inputs
            )

        return plan_job(
            payload,
            context,
            record_evidence=record_evidence,
        )

    return handle
