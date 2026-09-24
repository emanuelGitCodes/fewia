"""On-demand Spoonacular estimate for a succeeded grocery job."""

from time import monotonic
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.grocery import DEMO_USER_ID
from app.deps import (
    get_provider_settings as require_provider_settings,
)
from app.deps import (
    get_session,
)
from app.job_models import Job
from app.provider_runtime import build_spoonacular
from app.provider_settings import GroceryProviderSettings, ProviderConfigurationError
from app.providers.spoonacular import SpoonacularUnavailable
from app.services.supermarket_overlay import (
    IngredientCostEstimator,
    estimate_supermarket_cost,
)
from app.services.supermarket_plan import plan_from_result

router = APIRouter(prefix="/grocery", tags=["grocery"])
_NO_STORE = {"Cache-Control": "no-store"}
_JOB_MISSING = "Job not found"
_PLAN_UNREADY = "Plan is not ready for a supermarket estimate."
_UNAVAILABLE = "Spoonacular is unavailable."


class _Deadline:
    def __init__(self, inner: IngredientCostEstimator, started: float) -> None:
        self._inner = inner
        self._started = started

    def estimate_ingredient_cents(
        self, ingredient_id: int, amount: int, unit: str
    ) -> int | None:
        if monotonic() - self._started >= 20.0:
            raise SpoonacularUnavailable()
        return self._inner.estimate_ingredient_cents(ingredient_id, amount, unit)


def _fail(status: int, detail: str) -> NoReturn:
    raise HTTPException(status_code=status, detail=detail, headers=_NO_STORE)


def get_provider_settings() -> GroceryProviderSettings:
    try:
        return require_provider_settings()
    except HTTPException:
        raise HTTPException(
            status_code=503, detail=_UNAVAILABLE, headers=_NO_STORE
        ) from None


@router.get("/jobs/{job_id}/supermarket-estimate")
def read_supermarket_estimate(
    job_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[GroceryProviderSettings, Depends(get_provider_settings)],
) -> JSONResponse:
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        _fail(404, _JOB_MISSING)
    job = session.get(Job, str(job_uuid))
    if job is None or job.user_id != DEMO_USER_ID or job.kind != "agent":
        _fail(404, _JOB_MISSING)
    if job.status != "succeeded" or not isinstance(job.result, dict):
        _fail(409, _PLAN_UNREADY)
    try:
        plan = plan_from_result(dict(job.result).get("plan"))
    except (TypeError, ValueError):
        _fail(409, _PLAN_UNREADY)
    provider = None
    try:
        provider = build_spoonacular(settings)
    except ProviderConfigurationError:
        provider = None
    if provider is None:
        _fail(503, _UNAVAILABLE)
    try:
        overlay = estimate_supermarket_cost(plan, _Deadline(provider, monotonic()))
    finally:
        provider.close()
    return JSONResponse(
        content={"total_cents": overlay.total_cents, "notice": overlay.notice},
        headers=_NO_STORE,
    )
