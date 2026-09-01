"""Tests for the financial context tool and route."""

from datetime import date
from decimal import Decimal

import pytest
from conftest import RowSeeder, UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.tools.base import ToolError
from app.tools.finance import get_financial_context


def test_finance_route_uses_month_evidence_id_for_a_full_calendar_month(
    client: TestClient, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_finance(user_id, date(2026, 8, 1), date(2026, 8, 31))

    response = client.get(
        "/context/financial",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-31",
        },
    )

    assert response.status_code == 200
    assert response.json()["evidence_id"] == "finance:user-1:2026-08"


def test_finance_tool_uses_span_evidence_id_for_a_partial_range(
    session: Session, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_finance(user_id, date(2026, 8, 1), date(2026, 8, 10))

    context = get_financial_context(
        session, user_id, date(2026, 8, 1), date(2026, 8, 10)
    )

    assert context.evidence_id == "finance:user-1:2026-08-01..2026-08-10"


def test_finance_tool_rounds_averages_and_totals_over_seeded_subranges(
    session: Session, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    first_day = date(2026, 8, 1)
    second_day = date(2026, 8, 2)
    seed_finance(
        user_id,
        first_day,
        first_day,
        overrides={
            "total_spending": Decimal("10.00"),
            "cash_flow": Decimal("1.00"),
            "grocery_spending": Decimal("1.00"),
            "restaurant_spending": Decimal("2.00"),
            "transportation_spending": Decimal("3.00"),
            "fitness_spending": Decimal("4.00"),
            "discretionary_spending": Decimal("0.00"),
        },
    )
    seed_finance(
        user_id,
        second_day,
        second_day,
        overrides={
            "total_spending": Decimal("10.01"),
            "cash_flow": Decimal("1.01"),
            "grocery_spending": Decimal("1.01"),
            "restaurant_spending": Decimal("2.00"),
            "transportation_spending": Decimal("3.00"),
            "fitness_spending": Decimal("4.00"),
            "discretionary_spending": Decimal("0.00"),
        },
    )

    context = get_financial_context(session, user_id, first_day, second_day)

    assert context.record_count == 2
    assert context.total_spending == 20.01
    assert context.average_daily_spending == 10.01
    assert context.average_cash_flow == 1.01
    assert context.category_totals == {
        "grocery": 2.01,
        "restaurant": 4.0,
        "transportation": 6.0,
        "fitness": 8.0,
        "discretionary": 0.0,
    }


def test_finance_route_reports_one_missing_days_warning_with_counts(
    client: TestClient, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_finance(
        user_id,
        date(2026, 8, 1),
        date(2026, 8, 3),
        skip_days={date(2026, 8, 2)},
    )

    response = client.get(
        "/context/financial",
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


def test_finance_tool_returns_zero_values_and_categories_for_an_empty_range(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    context = get_financial_context(
        session, user_id, date(2026, 8, 1), date(2026, 8, 2)
    )

    assert context.record_count == 0
    assert context.source == ""
    assert context.total_spending == 0.0
    assert context.average_daily_spending == 0.0
    assert context.average_cash_flow == 0.0
    assert context.category_totals == {
        "grocery": 0.0,
        "restaurant": 0.0,
        "transportation": 0.0,
        "fitness": 0.0,
        "discretionary": 0.0,
    }
    assert [warning.code for warning in context.warnings] == ["no_records"]


def test_finance_route_sorts_distinct_sources_from_seeded_subranges(
    client: TestClient, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_finance(user_id, date(2026, 8, 1), date(2026, 8, 5), source="synthetic-v2")
    seed_finance(user_id, date(2026, 8, 6), date(2026, 8, 10), source="synthetic-v1")

    response = client.get(
        "/context/financial",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
    )

    assert response.status_code == 200
    assert response.json()["source"] == "synthetic-v1,synthetic-v2"


def test_finance_tool_rejects_an_unknown_user(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        get_financial_context(session, 999, date(2026, 8, 1), date(2026, 8, 1))

    assert caught.value.code == "user_not_found"
    assert caught.value.status_code == 404


def test_finance_route_rejects_an_unknown_user(client: TestClient) -> None:
    response = client.get(
        "/context/financial",
        params={
            "user_id": 999,
            "start_date": "2026-08-01",
            "end_date": "2026-08-01",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"


def test_finance_tool_rejects_a_reversed_range(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    with pytest.raises(ToolError) as caught:
        get_financial_context(session, user_id, date(2026, 8, 2), date(2026, 8, 1))

    assert caught.value.code == "invalid_range"
    assert caught.value.status_code == 422


def test_finance_route_rejects_a_reversed_range(
    client: TestClient, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    response = client.get(
        "/context/financial",
        params={
            "user_id": user_id,
            "start_date": "2026-08-02",
            "end_date": "2026-08-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_range"


def test_finance_tool_reads_only_the_requested_users_rows(
    session: Session, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    first_user_id = seed_user(user_id=1)
    second_user_id = seed_user(user_id=2)
    start_date = date(2026, 8, 1)
    end_date = date(2026, 8, 3)
    seed_finance(
        first_user_id,
        start_date,
        end_date,
        overrides={"total_spending": Decimal("10.00"), "cash_flow": Decimal("1.00")},
    )
    seed_finance(
        second_user_id,
        start_date,
        end_date,
        overrides={"total_spending": Decimal("90.00"), "cash_flow": Decimal("9.00")},
    )

    context = get_financial_context(session, first_user_id, start_date, end_date)

    assert context.record_count == 3
    assert context.total_spending == 30.0
    assert context.average_daily_spending == 10.0
    assert context.average_cash_flow == 1.0


def test_finance_tool_includes_both_requested_range_boundaries(
    session: Session, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    start_date = date(2026, 8, 2)
    end_date = date(2026, 8, 4)
    seed_finance(
        user_id,
        date(2026, 8, 1),
        date(2026, 8, 1),
        overrides={"total_spending": Decimal("999.00")},
    )
    seed_finance(
        user_id,
        start_date,
        start_date,
        overrides={"total_spending": Decimal("10.00")},
    )
    seed_finance(
        user_id,
        date(2026, 8, 3),
        date(2026, 8, 3),
        overrides={"total_spending": Decimal("20.00")},
    )
    seed_finance(
        user_id,
        end_date,
        end_date,
        overrides={"total_spending": Decimal("30.00")},
    )
    seed_finance(
        user_id,
        date(2026, 8, 5),
        date(2026, 8, 5),
        overrides={"total_spending": Decimal("888.00")},
    )

    context = get_financial_context(session, user_id, start_date, end_date)

    assert context.record_count == 3
    assert context.total_spending == 60.0


def test_finance_tool_uses_month_evidence_id_for_a_full_calendar_month(
    session: Session, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_finance(user_id, date(2026, 8, 1), date(2026, 8, 31))

    context = get_financial_context(
        session, user_id, date(2026, 8, 1), date(2026, 8, 31)
    )

    assert context.evidence_id == "finance:user-1:2026-08"


def test_finance_route_uses_span_evidence_id_for_a_partial_range(
    client: TestClient, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    seed_finance(user_id, date(2026, 8, 1), date(2026, 8, 10))

    response = client.get(
        "/context/financial",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
    )

    assert response.status_code == 200
    assert response.json()["evidence_id"] == "finance:user-1:2026-08-01..2026-08-10"


def test_finance_route_returns_zero_values_and_categories_for_an_empty_range(
    client: TestClient, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    response = client.get(
        "/context/financial",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
        },
    )

    assert response.status_code == 200
    assert response.json()["record_count"] == 0
    assert response.json()["source"] == ""
    assert response.json()["total_spending"] == 0.0
    assert response.json()["average_daily_spending"] == 0.0
    assert response.json()["average_cash_flow"] == 0.0
    assert response.json()["category_totals"] == {
        "grocery": 0.0,
        "restaurant": 0.0,
        "transportation": 0.0,
        "fitness": 0.0,
        "discretionary": 0.0,
    }
    assert [warning["code"] for warning in response.json()["warnings"]] == [
        "no_records"
    ]


def test_finance_route_rounds_averages_and_totals_over_seeded_subranges(
    client: TestClient, seed_finance: RowSeeder, seed_user: UserSeeder
) -> None:
    user_id = seed_user()
    first_day = date(2026, 8, 1)
    second_day = date(2026, 8, 2)
    seed_finance(
        user_id,
        first_day,
        first_day,
        overrides={
            "total_spending": Decimal("10.00"),
            "cash_flow": Decimal("1.00"),
            "grocery_spending": Decimal("1.00"),
            "restaurant_spending": Decimal("2.00"),
            "transportation_spending": Decimal("3.00"),
            "fitness_spending": Decimal("4.00"),
            "discretionary_spending": Decimal("0.00"),
        },
    )
    seed_finance(
        user_id,
        second_day,
        second_day,
        overrides={
            "total_spending": Decimal("10.01"),
            "cash_flow": Decimal("1.01"),
            "grocery_spending": Decimal("1.01"),
            "restaurant_spending": Decimal("2.00"),
            "transportation_spending": Decimal("3.00"),
            "fitness_spending": Decimal("4.00"),
            "discretionary_spending": Decimal("0.00"),
        },
    )

    response = client.get(
        "/context/financial",
        params={
            "user_id": user_id,
            "start_date": "2026-08-01",
            "end_date": "2026-08-02",
        },
    )

    assert response.status_code == 200
    assert response.json()["total_spending"] == 20.01
    assert response.json()["average_daily_spending"] == 10.01
    assert response.json()["average_cash_flow"] == 1.01
    assert response.json()["category_totals"] == {
        "grocery": 2.01,
        "restaurant": 4.0,
        "transportation": 6.0,
        "fitness": 8.0,
        "discretionary": 0.0,
    }
