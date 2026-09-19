"""Snapshot validation and shopping-payload reconstruction for handoff."""

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.api.handoff_types import SnapshotPlan
from app.job_models import Job
from app.services.evidence_contract import canonical_json
from app.services.evidence_store import load_evidence
from app.services.grocery_planner import PlanEstimate, ShoppingLine
from app.services.handoff_intents import HandoffView
from app.services.shopping_payload import NoShoppingItems, build_shopping_payload

PLANNING_KEYS: tuple[str, ...] = (
    "request",
    "plan",
    "budget",
    "spending_source",
    "evidence_id",
)
DEMO_USER_ID = 1
JOB_MISSING = "Job not found"
REBUILD = "Plan requires a rebuild."
DENIED = "Plan is not ready for shopping handoff."
NO_ITEMS = "shopping list has no items"
_HEX = "0123456789abcdef"


class HandoffRouteError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def planning_fields(result: dict[str, object]) -> dict[str, object] | None:
    if any(key not in result for key in PLANNING_KEYS):
        return None
    fields: dict[str, object] = {key: result[key] for key in PLANNING_KEYS}
    if "meal_nutrition" in result:
        fields["meal_nutrition"] = result["meal_nutrition"]
    return fields


def revision_id(value: object) -> str | None:
    if not isinstance(value, str) or len(value) != 64 or value.strip(_HEX):
        return None
    return value


def estimate_from_snapshot(plan: SnapshotPlan) -> PlanEstimate:
    rows = tuple(
        ShoppingLine(
            item.ingredient_id,
            item.name,
            item.unit,
            item.quantity,
            item.packages,
            item.cost_cents,
            item.from_pantry,
        )
        for item in plan.lines
    )
    return PlanEstimate(
        rows,
        plan.total_cents,
        plan.accepted,
        tuple(plan.warnings),
        plan.catalog_version,
        plan.notice,
    )


def may_retry(view: HandoffView, expected_attempt: int) -> bool:
    if expected_attempt != view.attempts:
        return False
    if view.state in {"uncertain", "failed"}:
        return True
    return view.state == "succeeded" and view.retry_allowed


def job_shopping_payload(
    factory: sessionmaker[Session], job_id: str
) -> dict[str, object]:
    with factory() as session:
        job = session.get(Job, job_id)
        owned = (DEMO_USER_ID, "agent", "succeeded")
        if job is None or (job.user_id, job.kind, job.status) != owned:
            raise HandoffRouteError(404, JOB_MISSING)
        raw_result = job.result
        if not isinstance(raw_result, dict):
            raise HandoffRouteError(409, REBUILD)
        result: dict[str, object] = dict(raw_result)
    revision = revision_id(result.get("evidence_revision_id"))
    if revision is None:
        raise HandoffRouteError(409, REBUILD)
    snapshot = load_evidence(factory, DEMO_USER_ID, revision)
    stored = None if snapshot is None else snapshot.get("planning")
    current = planning_fields(result)
    matched = False
    compare_failed = False
    try:
        matched = (
            isinstance(stored, dict)
            and current is not None
            and canonical_json(current) == canonical_json(stored)
        )
    except (TypeError, ValueError):
        compare_failed = True
    if compare_failed or not matched or not isinstance(stored, dict):
        raise HandoffRouteError(409, REBUILD)
    empty = False
    denied = False
    payload: dict[str, object] | None = None
    try:
        estimate = estimate_from_snapshot(
            SnapshotPlan.model_validate(stored.get("plan"))
        )
        if not estimate.accepted or estimate.total_cents is None:
            raise ValueError(DENIED)
        payload = build_shopping_payload(estimate)
    except NoShoppingItems:
        empty = True
    except (TypeError, ValueError, ValidationError):
        denied = True
    if empty:
        raise HandoffRouteError(409, NO_ITEMS)
    if denied or payload is None:
        raise HandoffRouteError(409, DENIED)
    return payload
