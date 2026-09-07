"""Tests for grocery HTTP models without the router."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.api.grocery_models import (
    CatalogRef,
    CreateGroceryJobBody,
    GroceryConfig,
    GroceryJobAccepted,
    GroceryJobView,
)
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE


def valid_body() -> dict[str, object]:
    return {
        "request": {
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": "2026-09-01",
        },
        "monthly_limit_cents": 40000,
    }


def test_create_body_accepts_caller_fields() -> None:
    body = CreateGroceryJobBody.model_validate(valid_body())
    dumped = body.model_dump(mode="json")

    assert body.monthly_limit_cents == 40000
    assert body.request.budget_period == date(2026, 9, 1)
    assert set(dumped) == {"request", "monthly_limit_cents"}
    assert body.caller_fields() == {
        "monthly_limit_cents": 40000,
        "request": body.request.model_dump(mode="json"),
    }


def test_caller_fields_match_stored_payload_not_spending() -> None:
    body = CreateGroceryJobBody.model_validate(valid_body())
    request = body.request.model_dump(mode="json")
    same = {
        "request": request,
        "monthly_limit_cents": 40000,
        "spending": {"posted_cents": 1, "refreshed_at": "2026-09-07T00:00:00Z"},
    }
    changed_limit = {
        "request": request,
        "monthly_limit_cents": 1,
        "spending": same["spending"],
    }

    one = CreateGroceryJobBody.model_validate(
        {**valid_body(), "monthly_limit_cents": 1}
    )
    bool_limit = {"request": request, "monthly_limit_cents": True}

    assert body.matches_stored_caller_fields(same) is True
    assert body.matches_stored_caller_fields(changed_limit) is False
    assert body.matches_stored_caller_fields("job") is False
    assert body.matches_stored_caller_fields({"monthly_limit_cents": 40000}) is False
    assert one.matches_stored_caller_fields(bool_limit) is False


def test_create_body_rejects_caller_user_and_spending() -> None:
    with pytest.raises(ValidationError):
        CreateGroceryJobBody.model_validate({**valid_body(), "user_id": 9})
    with pytest.raises(ValidationError):
        CreateGroceryJobBody.model_validate({**valid_body(), "spending": {}})


@pytest.mark.parametrize("value", [-1, True, 1.5, "100"])
def test_create_body_rejects_invalid_monthly_limit(value: object) -> None:
    payload = valid_body()
    payload["monthly_limit_cents"] = value
    with pytest.raises(ValidationError):
        CreateGroceryJobBody.model_validate(payload)


def test_catalog_ref_fields_exclude_price() -> None:
    item = CatalogRef(id="bean_tacos", name="bean tacos")

    assert set(CatalogRef.model_fields) == {"id", "name"}
    assert item.model_dump() == {"id": "bean_tacos", "name": "bean tacos"}
    assert "price" not in item.model_dump()


def test_config_keeps_sample_price_notice() -> None:
    config = GroceryConfig(
        budget_period=date(2026, 9, 1),
        source="fixture",
        posted_cents=18000,
        pending_cents=1200,
        notice=SAMPLE_ESTIMATE_NOTICE,
        recipes=[CatalogRef(id="bean_tacos", name="bean tacos")],
        ingredients=[CatalogRef(id="beans", name="beans")],
    )
    dumped = config.model_dump(mode="json")

    assert dumped["notice"] == SAMPLE_ESTIMATE_NOTICE
    assert dumped["source"] == "fixture"
    for item in dumped["recipes"] + dumped["ingredients"]:
        assert set(item) == {"id", "name"}
        assert "price" not in item


def test_job_view_exposes_public_fields_only() -> None:
    view = GroceryJobView(id="job-1", status="queued", result=None, error_code=None)

    assert set(view.model_dump()) == {"id", "status", "result", "error_code"}
    accepted = GroceryJobAccepted(job_id="job-1", status="queued")
    assert set(accepted.model_dump()) == {"job_id", "status"}
