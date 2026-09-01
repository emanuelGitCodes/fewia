"""Tests for the activity prediction tool and route."""

from datetime import date

import pytest
from conftest import RowSeeder, UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.tools.prediction import FeatureSet, run_activity_prediction

FEATURE_SETS: tuple[FeatureSet, ...] = ("finance", "environment", "combined")


def test_prediction_marks_stub_at_the_tool_and_route_levels(
    client: TestClient,
    session: Session,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    start_date = date(2026, 1, 1)
    seed_health(user_id, start_date, start_date)

    prediction = run_activity_prediction(session, user_id, start_date, start_date)
    response = client.get(
        "/predict/activity",
        params={
            "user_id": user_id,
            "start_date": start_date.isoformat(),
            "end_date": start_date.isoformat(),
        },
    )

    assert prediction.model_version == "stub-v0"
    assert prediction.is_stub is True
    assert response.status_code == 200
    assert response.json()["model_version"] == "stub-v0"
    assert response.json()["is_stub"] is True


@pytest.mark.parametrize(
    ("first_steps", "second_steps", "expected_average"),
    ((1500, 1501, 1501), (7500, 7501, 7501)),
)
def test_prediction_rounds_half_step_means_up(
    session: Session,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
    first_steps: int,
    second_steps: int,
    expected_average: int,
) -> None:
    user_id = seed_user()
    first_day = date(2026, 1, 1)
    second_day = date(2026, 1, 2)
    seed_health(user_id, first_day, first_day, overrides={"steps": first_steps})
    seed_health(user_id, second_day, second_day, overrides={"steps": second_steps})

    prediction = run_activity_prediction(session, user_id, first_day, second_day)

    assert prediction.predicted_average_steps == expected_average


def test_prediction_reports_an_empty_range_without_an_error(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    start_date = date(2026, 1, 1)
    end_date = date(2026, 1, 2)

    prediction = run_activity_prediction(session, user_id, start_date, end_date)

    assert prediction.predicted_average_steps == 0
    assert prediction.record_count == 0
    assert [warning.code for warning in prediction.warnings] == [
        "no_records",
        "null_fields",
    ]
    assert prediction.source == ""


def test_prediction_stub_warning_reports_its_model_version(
    session: Session,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    day = date(2026, 1, 1)
    seed_health(user_id, day, day)

    prediction = run_activity_prediction(session, user_id, day, day)
    stub_warning = prediction.warnings[-1]

    assert stub_warning.code == "null_fields"
    assert stub_warning.detail == {"model_version": "stub-v0"}


@pytest.mark.parametrize("feature_set", FEATURE_SETS)
def test_prediction_echoes_each_feature_set_without_changing_the_mean(
    session: Session,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
    feature_set: FeatureSet,
) -> None:
    user_id = seed_user()
    first_day = date(2026, 1, 1)
    second_day = date(2026, 1, 2)
    seed_health(user_id, first_day, first_day, overrides={"steps": 1500})
    seed_health(user_id, second_day, second_day, overrides={"steps": 1501})

    predictions = {
        value: run_activity_prediction(session, user_id, first_day, second_day, value)
        for value in FEATURE_SETS
    }

    assert predictions[feature_set].feature_set == feature_set
    assert {item.predicted_average_steps for item in predictions.values()} == {1501}


def test_prediction_evidence_ids_use_prediction_domain_and_range_forms(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    month_start = date(2026, 1, 1)
    month_end = date(2026, 1, 31)
    partial_end = date(2026, 1, 15)

    monthly_prediction = run_activity_prediction(
        session, user_id, month_start, month_end
    )
    partial_prediction = run_activity_prediction(
        session, user_id, month_start, partial_end
    )

    assert monthly_prediction.evidence_id == "prediction:user-1:2026-01"
    assert partial_prediction.evidence_id == "prediction:user-1:2026-01-01..2026-01-15"


def test_prediction_route_rejects_an_unknown_feature_set(client: TestClient) -> None:
    response = client.get(
        "/predict/activity",
        params={
            "user_id": 1,
            "start_date": "2026-01-01",
            "end_date": "2026-01-01",
            "feature_set": "weather",
        },
    )

    assert response.status_code == 422
    assert "detail" in response.json()
