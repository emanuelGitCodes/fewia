"""Tests for Instacart handoff request and plan snapshot types."""

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.api.handoff_types import (
    CreateHandoffBody,
    PlanLine,
    RetryHandoffBody,
    SnapshotPlan,
)

LINE: dict[str, object] = {
    "ingredient_id": "black_beans",
    "name": "black beans",
    "unit": "g",
    "quantity": 400,
    "packages": 1,
    "cost_cents": 189,
    "from_pantry": False,
}


def snapshot_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "lines": [dict(LINE)],
        "total_cents": 189,
        "accepted": True,
        "warnings": ["Estimated from the demo price catalog."],
        "catalog_version": "catalog-v1",
        "notice": "Estimated from the demo price catalog.",
    }
    values.update(overrides)
    return values


def test_create_body_accepts_job_id_and_forbids_extra() -> None:
    job_id = uuid4()
    body = CreateHandoffBody.model_validate({"job_id": str(job_id)})
    dumped = body.model_dump(mode="json")

    assert body.job_id == job_id
    assert isinstance(body.job_id, UUID)
    assert set(CreateHandoffBody.model_fields) == {"job_id"}
    assert dumped == {"job_id": str(job_id)}
    with pytest.raises(ValidationError):
        CreateHandoffBody.model_validate({"job_id": str(job_id), "url": "https://x"})


def test_retry_body_requires_positive_strict_attempt() -> None:
    body = RetryHandoffBody.model_validate({"expected_attempt": 1})

    assert body.expected_attempt == 1
    assert set(RetryHandoffBody.model_fields) == {"expected_attempt"}
    with pytest.raises(ValidationError):
        RetryHandoffBody.model_validate({"expected_attempt": 1, "retry": True})
    for value in (0, -1, True, 1.5, "1"):
        with pytest.raises(ValidationError):
            RetryHandoffBody.model_validate({"expected_attempt": value})


def test_plan_line_forbids_extra_and_non_strict_values() -> None:
    item = PlanLine.model_validate(LINE)
    dumped = item.model_dump()

    assert dumped == LINE
    assert set(PlanLine.model_fields) == set(LINE)
    none_cost = PlanLine.model_validate({**LINE, "cost_cents": None})
    assert none_cost.cost_cents is None
    with pytest.raises(ValidationError):
        PlanLine.model_validate({**LINE, "price_cents": 189})
    for field, value in (
        ("quantity", True),
        ("packages", 1.0),
        ("from_pantry", 1),
        ("cost_cents", True),
    ):
        with pytest.raises(ValidationError):
            PlanLine.model_validate({**LINE, field: value})


def test_snapshot_plan_round_trip_allows_missing_total() -> None:
    plan = SnapshotPlan.model_validate(snapshot_values())
    dumped = plan.model_dump()

    assert dumped["lines"] == [LINE]
    assert dumped["accepted"] is True
    assert dumped["total_cents"] == 189
    assert dumped["catalog_version"] == "catalog-v1"
    assert dumped["notice"] == "Estimated from the demo price catalog."
    incomplete = SnapshotPlan.model_validate(snapshot_values(total_cents=None))
    assert incomplete.total_cents is None
    assert incomplete.accepted is True
    with pytest.raises(ValidationError):
        SnapshotPlan.model_validate(snapshot_values(checkout=True))
    with pytest.raises(ValidationError):
        SnapshotPlan.model_validate(snapshot_values(accepted=1))
