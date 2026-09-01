"""Tests for the deterministic environment context tool."""

from datetime import date

import pytest
from conftest import RowSeeder, UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.tools.base import ToolError
from app.tools.environment import get_environment_context


def test_environment_context_uses_month_and_span_evidence_ids(
    session: Session, seed_environment: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    month_start = date(2026, 8, 1)
    month_end = date(2026, 8, 31)
    seed_environment(user_id, month_start, month_end)

    month_result = get_environment_context(session, user_id, month_start, month_end)
    span_result = get_environment_context(
        session, user_id, month_start, date(2026, 8, 30)
    )

    assert month_result.evidence_id == "environment:user-1:2026-08"
    assert span_result.evidence_id == "environment:user-1:2026-08-01..2026-08-30"


def test_environment_context_rounds_all_place_count_averages_half_up(
    session: Session, seed_environment: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    start_date = date(2026, 8, 1)
    end_date = date(2026, 8, 8)
    seed_environment(
        user_id,
        start_date,
        date(2026, 8, 7),
        overrides={
            "park_count": 1,
            "gym_count": 2,
            "grocery_store_count": 3,
            "restaurant_count": 4,
        },
    )
    seed_environment(
        user_id,
        end_date,
        end_date,
        overrides={
            "park_count": 2,
            "gym_count": 3,
            "grocery_store_count": 4,
            "restaurant_count": 5,
        },
    )

    result = get_environment_context(session, user_id, start_date, end_date)

    assert result.record_count == 8
    assert result.average_park_count == 1.13
    assert result.average_gym_count == 2.13
    assert result.average_grocery_store_count == 3.13
    assert result.average_restaurant_count == 4.13


def test_environment_context_sorts_distinct_location_types(
    session: Session, seed_environment: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    start_date = date(2026, 8, 1)
    end_date = date(2026, 8, 6)
    seed_environment(
        user_id,
        start_date,
        date(2026, 8, 2),
        overrides={"location_type": "urban"},
    )
    seed_environment(
        user_id,
        date(2026, 8, 3),
        date(2026, 8, 4),
        overrides={"location_type": "rural"},
    )
    seed_environment(
        user_id,
        date(2026, 8, 5),
        end_date,
        overrides={"location_type": "suburban"},
    )

    result = get_environment_context(session, user_id, start_date, end_date)

    assert result.location_types == ["rural", "suburban", "urban"]


def test_environment_context_reports_missing_days_with_counts(
    session: Session, seed_environment: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    start_date = date(2026, 8, 1)
    end_date = date(2026, 8, 5)
    seed_environment(
        user_id,
        start_date,
        end_date,
        skip_days={date(2026, 8, 2), date(2026, 8, 4)},
    )

    result = get_environment_context(session, user_id, start_date, end_date)

    assert [warning.code for warning in result.warnings] == ["missing_days"]
    assert result.warnings[0].detail == {"record_count": "3", "day_count": "5"}


def test_environment_context_returns_empty_values_for_an_empty_range(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    result = get_environment_context(
        session, user_id, date(2026, 8, 1), date(2026, 8, 31)
    )

    assert result.record_count == 0
    assert result.average_park_count == 0.0
    assert result.average_gym_count == 0.0
    assert result.average_grocery_store_count == 0.0
    assert result.average_restaurant_count == 0.0
    assert result.location_types == []
    assert [warning.code for warning in result.warnings] == ["no_records"]
    assert result.source == ""


def test_environment_route_matches_the_tool_for_month_and_span_ranges(
    client: TestClient,
    session: Session,
    seed_environment: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    month_start = date(2026, 8, 1)
    month_end = date(2026, 8, 31)
    seed_environment(user_id, month_start, month_end)

    for start_date, end_date in (
        (month_start, month_end),
        (month_start, date(2026, 8, 30)),
    ):
        result = get_environment_context(session, user_id, start_date, end_date)
        response = client.get(
            "/context/environment",
            params={
                "user_id": user_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["evidence_id"] == result.evidence_id
        assert body["record_count"] == result.record_count
        assert body["average_park_count"] == result.average_park_count
        assert body["average_gym_count"] == result.average_gym_count
        assert body["average_grocery_store_count"] == result.average_grocery_store_count
        assert body["average_restaurant_count"] == result.average_restaurant_count
        assert body["location_types"] == result.location_types


def test_environment_tool_reports_an_invalid_range(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        get_environment_context(session, 1, date(2026, 8, 2), date(2026, 8, 1))

    assert caught.value.code == "invalid_range"
    assert caught.value.status_code == 422


def test_environment_route_reports_an_invalid_range(client: TestClient) -> None:
    response = client.get(
        "/context/environment",
        params={
            "user_id": 1,
            "start_date": "2026-08-02",
            "end_date": "2026-08-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_range"


def test_environment_tool_reports_an_unknown_user(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        get_environment_context(session, 999, date(2026, 8, 1), date(2026, 8, 31))

    assert caught.value.code == "user_not_found"
    assert caught.value.status_code == 404


def test_environment_route_reports_an_unknown_user(client: TestClient) -> None:
    response = client.get(
        "/context/environment",
        params={
            "user_id": 999,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"
