from contextlib import ExitStack, closing
from typing import NamedTuple, cast

from sqlalchemy import select

from app.evaluation_database import fixture_database
from app.evaluation_duplicate_handler import DuplicateHandler, ReportStore
from app.evaluation_inputs import prepare_case
from app.evidence_models import GroceryEvidence
from app.handoff_models import ShoppingHandoff
from app.job_models import Job, JobOutbox
from app.models import User
from app.providers.local_artifacts import LocalArtifactStore
from app.providers.local_sqs import ALLOWED_ENDPOINTS, LocalSqsSender as LocalSqsSender
from app.providers.local_sqs_consumer import LocalSqsConsumer as LocalSqsConsumer
from app.providers.local_sqs_isolated import IsolatedLocalQueue
from app.services.job_consumer import process_one
from app.services.job_delivery import JobQueue
from app.services.job_submission import create_job
from app.services.outbox_publisher import JobSender, publish_pending


class _Services(NamedTuple):
    sender: JobSender
    queue: JobQueue
    artifacts: ReportStore


def evaluate_duplicate_case(
    case: dict[str, object], *, database_url: str, endpoint: str
) -> dict[str, object]:
    return _evaluate(case, database_url=database_url, endpoint=endpoint)


def _evaluate(
    case: dict[str, object],
    *,
    database_url: str,
    endpoint: str,
    services: _Services | None = None,
) -> dict[str, object]:
    failure: dict[str, object] = {
        "case_id": "P05",
        "status": "failed",
        "evidence_class": "unknown",
        "evidence_paths": [],
        "model_quality_applicable": False,
        "checks": {"execution": False},
        "observed": {},
        "reason": "duplicate_execution_failed",
    }
    try:
        behavior = case.get("fixture_behavior")
        inputs = case.get("inputs")
        if (
            case.get("id") != "P05"
            or not isinstance(behavior, dict)
            or behavior.get("kind") != "duplicate_sqs_delivery"
            or behavior.get("provider") != "fake"
            or not isinstance(inputs, dict)
            or inputs.get("plan_accepted") is not True
            or type(inputs.get("delivery_attempts")) is not int
            or inputs.get("delivery_attempts") != 2
            or not database_url
            or endpoint not in ALLOWED_ENDPOINTS
        ):
            return failure
        context = prepare_case(case)
        fake = services is not None
        with fixture_database(database_url) as database, ExitStack() as cleanup:
            if database.backend != "postgresql":
                return failure
            factory = database.factory
            if services is None:
                store = cleanup.enter_context(closing(LocalArtifactStore(endpoint)))
                queue = cleanup.enter_context(closing(IsolatedLocalQueue(endpoint)))
                services = _Services(queue.sender, queue.consumer, store)
            handler = DuplicateHandler(factory, context, services.artifacts)
            owner = context.user_id
            with factory.begin() as session:
                session.add(User(id=owner, display_name="Evaluation demo"))
                session.flush()
                payload: dict[str, object] = {"case_id": "P05", "user_id": owner}
                job, created = create_job(session, owner, "agent", "P05", payload)
            published = publish_pending(factory, services.sender)
            services.sender.send("agent", job.id)
            outcomes = [
                process_one(factory, services.queue, "agent", handler) for _ in range(2)
            ]
            original = handler.handoff
            cached = handler.repeat_handoff() if original is not None else None
            with factory() as session:
                jobs = session.scalars(select(Job)).all()
                outboxes = session.scalars(select(JobOutbox)).all()
                evidence = session.scalars(select(GroceryEvidence)).all()
                handoffs = session.scalars(select(ShoppingHandoff)).all()
            plan = (handler.planning or {}).get("plan")
            total = plan.get("total_cents") if isinstance(plan, dict) else None
            gold = cast(dict[str, object], case["expected"])
            calls = cast(list[dict[str, object]], gold["domain_calls"])
            delivery = next(call for call in calls if call.get("name") == "process_one")
            gold_args = cast(dict[str, object], delivery["expectation"])
            checks = {
                "deliveries": outcomes == ["succeeded", "terminal"],
                "handler_once": handler.handler_calls == 1,
                "one_job": created and len(jobs) == 1,
                "job_succeeded": jobs[0].status == "succeeded",
                "job_attempts": jobs[0].attempts == 1,
                "outbox": published == 1 and len(outboxes) == 1,
                "outbox_sent": outboxes[0].published_at is not None,
                "one_revision": len(evidence) == 1,
                "revision": evidence[0].id == handler.evidence_revision_id,
                "one_handoff": len(handoffs) == 1,
                "handoff_succeeded": handoffs[0].state == "succeeded",
                "handoff_attempts": handoffs[0].attempts == 1,
                "provider_once": handler.provider.calls == 1,
                "cache": cached == original and cached is not None,
                "artifact_once": handler.artifact_attempts == 1,
                "artifact_saved": handler.artifact is not None,
                "gold_total": total == gold.get("total_cents"),
                "gold_deliveries": gold_args.get("delivery_attempts") == len(outcomes),
            }
            observed = jobs[0].result or {}
            observed["handler_calls"] = handler.handler_calls
            observed["provider_calls"] = handler.provider.calls
            observed["artifact_attempts"] = handler.artifact_attempts
            observed["worker_outcomes"] = outcomes
            observed["job_count"] = len(jobs)
            observed["job_status"] = jobs[0].status
            observed["outbox_count"] = len(outboxes)
            observed["evidence_count"] = len(evidence)
            observed["handoff_count"] = len(handoffs)
        return {
            "case_id": "P05",
            "status": "passed" if all(checks.values()) else "failed",
            "evidence_class": "local_postgresql",
            "model_quality_applicable": False,
            "evidence_paths": [
                "local_postgresql",
                "worker",
                "deterministic_fake_queue" if fake else "floci_sqs",
                "deterministic_fake_artifact" if fake else "floci_s3",
                "deterministic_fake_provider",
            ],
            "checks": checks,
            "observed": observed,
        }
    except Exception:  # noqa: BLE001
        return failure
