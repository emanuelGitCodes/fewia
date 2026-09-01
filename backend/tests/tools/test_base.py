"""Foundation tests for deterministic context tool helpers."""

from datetime import date
from decimal import Decimal

import pytest
from conftest import RowSeeder, UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyHealth, User
from app.tools.base import (
    ToolError,
    missing_day_warnings,
    require_user,
    round_money,
    validate_range,
)


def test_require_user_returns_none_for_an_existing_user(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    require_user(session, user_id)


def test_require_user_raises_not_found_for_an_unknown_user(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        require_user(session, 999)

    assert caught.value.code == "user_not_found"
    assert caught.value.status_code == 404


def test_require_user_does_not_find_a_different_seeded_user(
    session: Session, seed_user: UserSeeder
) -> None:
    seed_user(user_id=1)

    with pytest.raises(ToolError) as caught:
        require_user(session, 2)

    assert caught.value.code == "user_not_found"


def test_validate_range_accepts_exactly_366_days() -> None:
    validate_range(date(2026, 1, 1), date(2027, 1, 1))


def test_validate_range_rejects_exactly_367_days() -> None:
    with pytest.raises(ToolError) as caught:
        validate_range(date(2026, 1, 1), date(2027, 1, 2))

    assert caught.value.code == "invalid_range"
    assert caught.value.status_code == 422
    assert "366" in caught.value.message


def test_validate_range_uses_distinct_messages_for_its_error_branches() -> None:
    with pytest.raises(ToolError) as reversed_range:
        validate_range(date(2026, 1, 2), date(2026, 1, 1))
    with pytest.raises(ToolError) as long_range:
        validate_range(date(2026, 1, 1), date(2027, 1, 2))

    assert "start_date" in reversed_range.value.message
    assert "end_date" in reversed_range.value.message
    assert reversed_range.value.message != long_range.value.message


def test_missing_day_warnings_reports_a_single_day_without_records() -> None:
    warnings = missing_day_warnings(0, date(2026, 1, 1), date(2026, 1, 1))

    assert [warning.code for warning in warnings] == ["no_records"]
    assert warnings[0].detail == {"record_count": "0", "day_count": "1"}


def test_missing_day_warnings_includes_counts_for_missing_days() -> None:
    warnings = missing_day_warnings(1, date(2026, 1, 1), date(2026, 1, 3))

    assert [warning.code for warning in warnings] == ["missing_days"]
    assert warnings[0].detail == {"record_count": "1", "day_count": "3"}


def test_missing_day_warnings_ignores_record_counts_above_the_day_count() -> None:
    assert missing_day_warnings(4, date(2026, 1, 1), date(2026, 1, 3)) == []


def test_round_money_rounds_exact_halves_away_from_zero() -> None:
    assert round_money(2.675) == 2.68
    assert round_money(Decimal("0.125")) == 0.13
    assert round_money(-2.675) == -2.68


def test_round_money_accepts_decimal_and_float_values() -> None:
    assert round_money(Decimal("1.234")) == 1.23
    assert round_money(1.234) == 1.23


def test_health_route_returns_not_found_through_the_real_app(
    client: TestClient,
) -> None:
    response = client.get(
        "/context/health",
        params={
            "user_id": 999,
            "start_date": "2026-01-01",
            "end_date": "2026-01-01",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "user_not_found", "message": "No user has the id 999."}
    }


def test_health_route_returns_invalid_range_through_the_real_app(
    client: TestClient,
) -> None:
    response = client.get(
        "/context/health",
        params={
            "user_id": 999,
            "start_date": "2026-01-02",
            "end_date": "2026-01-01",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_range",
            "message": "start_date MUST NOT come after end_date.",
        }
    }


def test_session_fixture_seeds_a_user_and_health_rows(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(user_id, date(2026, 1, 1), date(2026, 1, 1))

    assert session.scalar(select(func.count()).select_from(User)) == 1
    assert session.scalar(select(func.count()).select_from(DailyHealth)) == 1


def test_session_fixture_starts_with_empty_tables(session: Session) -> None:
    user_count = session.scalar(select(func.count()).select_from(User))
    health_count = session.scalar(select(func.count()).select_from(DailyHealth))

    assert user_count == 0
    assert health_count == 0


def test_client_and_health_tool_read_seeded_rows(
    client: TestClient, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_health(user_id, date(2026, 1, 1), date(2026, 1, 1))

    response = client.get(
        "/context/health",
        params={
            "user_id": user_id,
            "start_date": "2026-01-01",
            "end_date": "2026-01-01",
        },
    )

    assert response.status_code == 200
    assert response.json()["record_count"] == 1


def test_seed_health_supports_multiple_ranges_with_distinct_null_fields(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    first_day = date(2026, 1, 1)
    second_day = date(2026, 1, 2)
    seed_health(user_id, first_day, first_day, null_fields={"sleep_minutes"})
    seed_health(user_id, second_day, second_day, null_fields={"stress_score"})

    rows = list(
        session.scalars(select(DailyHealth).order_by(DailyHealth.observation_date))
    )

    assert [row.observation_date for row in rows] == [first_day, second_day]
    assert [row.sleep_minutes for row in rows] == [None, 420]
    assert [row.stress_score for row in rows] == [Decimal("25.00"), None]


def test_seed_health_skips_days_and_returns_only_inserted_dates(
    session: Session, seed_health: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    first_day = date(2026, 1, 1)
    skipped_day = date(2026, 1, 2)
    last_day = date(2026, 1, 3)

    inserted_dates = seed_health(user_id, first_day, last_day, skip_days={skipped_day})
    row_count = session.scalar(select(func.count()).select_from(DailyHealth))

    assert inserted_dates == [first_day, last_day]
    assert row_count == 2
