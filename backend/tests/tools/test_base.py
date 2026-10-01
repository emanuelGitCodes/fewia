"""Foundation tests for session seed fixtures."""

from datetime import date
from decimal import Decimal

from conftest import RowSeeder, UserSeeder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DailyHealth, User


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
