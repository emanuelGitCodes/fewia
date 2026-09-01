"""Tests for the health context tool and route."""

from datetime import date
from decimal import Decimal

import pytest
from conftest import RowSeeder, UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.tools.base import ToolError
from app.tools.health import get_health_context


def test_health_tool_uses_month_evidence_id_for_a_full_calendar_month(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(user_id, date(2026, 8, 1), date(2026, 8, 31))

    context = get_health_context(session, user_id, date(2026, 8, 1), date(2026, 8, 31))

    assert context.evidence_id == "health:user-1:2026-08"


def test_health_route_uses_span_evidence_id_for_a_partial_range(
    client: TestClient, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(user_id, date(2026, 8, 1), date(2026, 8, 10))

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
    )

    assert response.status_code == 200
    assert response.json()["evidence_id"] == "health:user-1:2026-08-01..2026-08-10"


def test_health_tool_rounds_averages_and_totals_over_seeded_subranges(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    first_day = date(2026, 8, 1)
    second_day = date(2026, 8, 2)
    seed_health(
        user_id,
        first_day,
        first_day,
        overrides={
            "steps": 8000,
            "sleep_minutes": 420,
            "resting_heart_rate": Decimal("60.00"),
            "stress_score": Decimal("25.00"),
        },
    )
    seed_health(
        user_id,
        second_day,
        second_day,
        overrides={
            "steps": 8001,
            "sleep_minutes": 421,
            "resting_heart_rate": Decimal("60.01"),
            "stress_score": Decimal("25.01"),
        },
    )

    context = get_health_context(session, user_id, first_day, second_day)

    assert context.record_count == 2
    assert context.average_steps == 8001
    assert context.total_steps == 16001
    assert context.average_sleep_minutes == 420.5
    assert context.average_resting_heart_rate == 60.01
    assert context.average_stress_score == 25.01


def test_health_route_reports_one_missing_days_warning_with_counts(
    client: TestClient, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(
        user_id,
        date(2026, 8, 1),
        date(2026, 8, 3),
        skip_days={date(2026, 8, 2)},
    )

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-03",
        },
    )

    assert response.status_code == 200
    assert response.json()["warnings"] == [
        {
            "code": "missing_days",
            "message": "The range misses one or more days.",
            "detail": {"record_count": "2", "day_count": "3"},
        }
    ]


def test_health_tool_returns_zero_values_for_an_empty_range(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    context = get_health_context(session, user_id, date(2026, 8, 1), date(2026, 8, 2))

    assert context.record_count == 0
    assert context.source == ""
    assert context.average_steps == 0
    assert context.total_steps == 0
    assert context.average_sleep_minutes is None
    assert context.average_resting_heart_rate is None
    assert context.average_stress_score is None
    assert [warning.code for warning in context.warnings] == ["no_records"]


def test_health_route_sorts_distinct_sources_from_seeded_subranges(
    client: TestClient, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(user_id, date(2026, 8, 1), date(2026, 8, 5), source="synthetic-v2")
    seed_health(user_id, date(2026, 8, 6), date(2026, 8, 10), source="synthetic-v1")

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
    )

    assert response.status_code == 200
    assert response.json()["source"] == "synthetic-v1,synthetic-v2"


def test_health_tool_returns_none_for_an_average_with_only_null_values(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    requested_day = date(2026, 8, 1)
    seed_health(
        user_id,
        requested_day,
        requested_day,
        null_fields={"resting_heart_rate"},
    )

    context = get_health_context(session, user_id, requested_day, requested_day)

    assert context.average_resting_heart_rate is None
    assert context.warnings[0].code == "null_fields"
    assert context.warnings[0].detail["columns"] == "resting_heart_rate"


def test_health_route_reports_intensity_nulls_without_an_intensity_average(
    client: TestClient, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    requested_day = date(2026, 8, 1)
    seed_health(
        user_id, requested_day, requested_day, null_fields={"intensity_minutes"}
    )

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-01",
        },
    )

    assert response.status_code == 200
    assert response.json()["warnings"] == [
        {
            "code": "null_fields",
            "message": "One or more days hold no value in a nullable column.",
            "detail": {"columns": "intensity_minutes"},
        }
    ]
    assert "average_intensity_minutes" not in response.json()


def test_health_tool_rejects_an_unknown_user(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        get_health_context(session, 999, date(2026, 8, 1), date(2026, 8, 1))

    assert caught.value.code == "user_not_found"
    assert caught.value.status_code == 404


def test_health_route_rejects_an_unknown_user(client: TestClient) -> None:
    response = client.get(
        "/context/health",
        params={
            "user_id": 999,
            "start_date": "2026-08-01",
            "end_date": "2026-08-01",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"


def test_health_tool_rejects_a_reversed_range(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    with pytest.raises(ToolError) as caught:
        get_health_context(session, user_id, date(2026, 8, 2), date(2026, 8, 1))

    assert caught.value.code == "invalid_range"
    assert caught.value.status_code == 422


def test_health_route_rejects_a_reversed_range(
    client: TestClient, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-02",
            "end_date": "2026-08-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_range"


def test_health_tool_reads_only_the_requested_users_rows(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    first_user_id = seed_user(user_id=1)
    second_user_id = seed_user(user_id=2)
    start_date = date(2026, 8, 1)
    end_date = date(2026, 8, 3)
    seed_health(first_user_id, start_date, end_date, overrides={"steps": 1000})
    seed_health(second_user_id, start_date, end_date, overrides={"steps": 9000})

    context = get_health_context(session, first_user_id, start_date, end_date)

    assert context.record_count == 3
    assert context.total_steps == 3000
    assert context.average_steps == 1000


def test_health_tool_includes_both_requested_range_boundaries(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    start_date = date(2026, 8, 2)
    end_date = date(2026, 8, 4)
    seed_health(user_id, date(2026, 8, 1), date(2026, 8, 1), overrides={"steps": 9999})
    seed_health(user_id, start_date, start_date, overrides={"steps": 100})
    seed_health(user_id, date(2026, 8, 3), date(2026, 8, 3), overrides={"steps": 200})
    seed_health(user_id, end_date, end_date, overrides={"steps": 300})
    seed_health(user_id, date(2026, 8, 5), date(2026, 8, 5), overrides={"steps": 8888})

    context = get_health_context(session, user_id, start_date, end_date)

    assert context.record_count == 3
    assert context.total_steps == 600


def test_health_route_uses_month_evidence_id_for_a_full_calendar_month(
    client: TestClient, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(user_id, date(2026, 8, 1), date(2026, 8, 31))

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        },
    )

    assert response.status_code == 200
    assert response.json()["evidence_id"] == "health:user-1:2026-08"


def test_health_tool_uses_span_evidence_id_for_a_partial_range(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(user_id, date(2026, 8, 1), date(2026, 8, 10))

    context = get_health_context(session, user_id, date(2026, 8, 1), date(2026, 8, 10))

    assert context.evidence_id == "health:user-1:2026-08-01..2026-08-10"


def test_health_route_returns_zero_values_for_an_empty_range(
    client: TestClient, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
        },
    )

    assert response.status_code == 200
    assert response.json()["record_count"] == 0
    assert response.json()["source"] == ""
    assert response.json()["average_steps"] == 0
    assert response.json()["total_steps"] == 0
    assert response.json()["average_sleep_minutes"] is None
    assert response.json()["average_resting_heart_rate"] is None
    assert response.json()["average_stress_score"] is None
    assert [warning["code"] for warning in response.json()["warnings"]] == [
        "no_records"
    ]


def test_health_route_rounds_averages_and_totals_over_seeded_subranges(
    client: TestClient, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    first_day = date(2026, 8, 1)
    second_day = date(2026, 8, 2)
    seed_health(
        user_id,
        first_day,
        first_day,
        overrides={
            "steps": 8000,
            "sleep_minutes": 420,
            "resting_heart_rate": Decimal("60.00"),
            "stress_score": Decimal("25.00"),
        },
    )
    seed_health(
        user_id,
        second_day,
        second_day,
        overrides={
            "steps": 8001,
            "sleep_minutes": 421,
            "resting_heart_rate": Decimal("60.01"),
            "stress_score": Decimal("25.01"),
        },
    )

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
        },
    )

    assert response.status_code == 200
    assert response.json()["average_steps"] == 8001
    assert isinstance(response.json()["average_steps"], int)
    assert response.json()["total_steps"] == 16001
    assert response.json()["average_sleep_minutes"] == 420.5
    assert response.json()["average_resting_heart_rate"] == 60.01
    assert response.json()["average_stress_score"] == 25.01


def test_health_tool_averages_only_present_nullable_values(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    first_day = date(2026, 8, 1)
    second_day = date(2026, 8, 2)
    seed_health(
        user_id,
        first_day,
        first_day,
        null_fields={"resting_heart_rate"},
    )
    seed_health(
        user_id,
        second_day,
        second_day,
        overrides={"resting_heart_rate": Decimal("60.50")},
    )

    context = get_health_context(session, user_id, first_day, second_day)

    assert context.average_resting_heart_rate == 60.5
    assert [warning.code for warning in context.warnings] == ["null_fields"]


def test_health_tool_reports_nullable_columns_in_declaration_order(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    requested_day = date(2026, 8, 1)
    seed_health(
        user_id,
        requested_day,
        requested_day,
        null_fields={"resting_heart_rate", "stress_score"},
    )

    context = get_health_context(session, user_id, requested_day, requested_day)

    assert context.warnings[0].detail["columns"] == "resting_heart_rate,stress_score"
