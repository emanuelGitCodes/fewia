"""Tests for the deterministic period comparison tool."""

from datetime import date
from decimal import Decimal

import pytest
from conftest import RowSeeder, UserSeeder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.tools.base import ToolError
from app.tools.compare import compare_periods


def test_compare_drops_empty_child_sources(
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    seed_health(user_id, *period_a, source="synthetic-v1")
    seed_finance(user_id, *period_a, source="synthetic-v1")

    result = compare_periods(session, user_id, period_a, period_b)

    assert result.source == "synthetic-v1"
    assert not result.source.startswith(",")
    assert ",," not in result.source


def test_compare_returns_an_empty_source_when_all_children_are_empty(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    result = compare_periods(
        session,
        user_id,
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    )

    assert result.source == ""


def test_compare_evidence_id_does_not_order_the_two_periods(
    session: Session, seed_user: UserSeeder
) -> None:
    user_id = seed_user()

    result = compare_periods(
        session,
        user_id,
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 7, 1), date(2026, 7, 31)),
    )

    assert result.evidence_id == "compare:user-1:2026-08-01..2026-07-31"


def test_compare_evidence_id_collides_for_two_january_periods(
    session: Session, seed_user: UserSeeder
) -> None:
    """The ID does not distinguish the two periods."""
    user_id = seed_user()

    result = compare_periods(
        session,
        user_id,
        (date(2026, 1, 1), date(2026, 1, 15)),
        (date(2026, 1, 16), date(2026, 1, 31)),
    )

    assert result.evidence_id == "compare:user-1:2026-01"


def test_compare_calculates_deltas_from_period_a_to_period_b(
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    seed_health(user_id, *period_a, overrides={"steps": 5000})
    seed_health(user_id, *period_b, overrides={"steps": 8000})
    seed_finance(user_id, *period_a, overrides={"total_spending": Decimal("100.00")})
    seed_finance(user_id, *period_b, overrides={"total_spending": Decimal("50.00")})

    result = compare_periods(session, user_id, period_a, period_b)

    assert result.steps_delta == 3000
    assert result.spending_delta == -1600.0


def test_compare_returns_none_for_percent_changes_with_zero_baselines(
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    seed_health(user_id, *period_a, overrides={"steps": 0})
    seed_health(user_id, *period_b, overrides={"steps": 8000})
    seed_finance(user_id, *period_a, overrides={"total_spending": Decimal("0.00")})
    seed_finance(user_id, *period_b, overrides={"total_spending": Decimal("100.00")})

    result = compare_periods(session, user_id, period_a, period_b)

    assert result.steps_percent_change is None
    assert result.spending_percent_change is None


def test_compare_calculates_percent_changes_with_nonzero_baselines(
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    seed_health(user_id, *period_a, overrides={"steps": 5000})
    seed_health(user_id, *period_b, overrides={"steps": 8000})
    seed_finance(user_id, *period_a, overrides={"total_spending": Decimal("100.00")})
    seed_finance(user_id, *period_b, overrides={"total_spending": Decimal("50.00")})

    result = compare_periods(session, user_id, period_a, period_b)

    assert result.steps_percent_change == 60.0
    assert result.spending_percent_change == -51.61


def test_compare_concatenates_warnings_in_child_order(
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    skipped_a = {date(2026, 8, 4)}
    skipped_b = {date(2026, 9, 4), date(2026, 9, 18)}
    seed_health(
        user_id,
        *period_a,
        skip_days=skipped_a,
        null_fields=("stress_score",),
    )
    seed_finance(user_id, *period_a, skip_days=skipped_a)
    seed_health(user_id, *period_b, skip_days=skipped_b)
    seed_finance(user_id, *period_b, skip_days=skipped_b)

    result = compare_periods(session, user_id, period_a, period_b)

    assert [warning.code for warning in result.warnings] == [
        "missing_days",
        "null_fields",
        "missing_days",
        "missing_days",
        "missing_days",
    ]
    assert result.warnings[0].detail["day_count"] == "31"
    assert result.warnings[1].detail == {"columns": "stress_score"}
    assert result.warnings[2].detail["day_count"] == "31"
    # The two period B warnings are byte-identical.
    # Assert the count and position, not identity.
    assert [warning.detail["day_count"] for warning in result.warnings[3:]] == [
        "30",
        "30",
    ]


def test_compare_period_summaries_mix_health_evidence_with_finance_values(
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    """The summary mixes a health evidence ID with a finance value."""
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    seed_health(user_id, *period_a)
    seed_finance(user_id, *period_a)
    seed_health(user_id, *period_b)
    seed_finance(user_id, *period_b)

    result = compare_periods(session, user_id, period_a, period_b)

    assert result.period_a.evidence_id == "health:user-1:2026-08"
    assert result.period_a.total_spending == 3100.0
    assert result.period_b.evidence_id == "health:user-1:2026-09"
    assert result.period_b.total_spending == 3000.0


def test_compare_period_summary_record_count_comes_from_health(
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    seed_health(user_id, *period_a)
    seed_finance(user_id, *period_a, skip_days={date(2026, 8, 31)})

    result = compare_periods(session, user_id, period_a, period_b)

    assert result.period_a.record_count == 31


def test_compare_route_matches_the_tool(
    client: TestClient,
    session: Session,
    seed_finance: RowSeeder,
    seed_health: RowSeeder,
    seed_user: UserSeeder,
) -> None:
    user_id = seed_user()
    period_a = (date(2026, 8, 1), date(2026, 8, 31))
    period_b = (date(2026, 9, 1), date(2026, 9, 30))
    seed_health(user_id, *period_a, skip_days={date(2026, 8, 31)})
    seed_finance(user_id, *period_a, skip_days={date(2026, 8, 31)})
    seed_health(user_id, *period_b, overrides={"steps": 9000})
    seed_finance(user_id, *period_b, overrides={"total_spending": Decimal("50.00")})
    result = compare_periods(session, user_id, period_a, period_b)
    response = client.get(
        "/context/compare",
        params={
            "user_id": user_id,
            "period_a_start": period_a[0].isoformat(),
            "period_a_end": period_a[1].isoformat(),
            "period_b_start": period_b[0].isoformat(),
            "period_b_end": period_b[1].isoformat(),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evidence_id"] == result.evidence_id
    assert body["source"] == result.source
    assert body["steps_delta"] == result.steps_delta
    assert body["spending_delta"] == result.spending_delta
    assert [warning["code"] for warning in body["warnings"]] == [
        warning.code for warning in result.warnings
    ]


def test_compare_tool_reports_an_invalid_period_a_range(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        compare_periods(
            session,
            1,
            (date(2026, 8, 2), date(2026, 8, 1)),
            (date(2026, 9, 1), date(2026, 9, 30)),
        )

    assert caught.value.code == "invalid_range"
    assert caught.value.status_code == 422


def test_compare_route_reports_an_invalid_period_a_range(client: TestClient) -> None:
    response = client.get(
        "/context/compare",
        params={
            "user_id": 1,
            "period_a_start": "2026-08-02",
            "period_a_end": "2026-08-01",
            "period_b_start": "2026-09-01",
            "period_b_end": "2026-09-30",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_range"


def test_compare_tool_reports_an_invalid_period_b_range(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        compare_periods(
            session,
            1,
            (date(2026, 8, 1), date(2026, 8, 31)),
            (date(2026, 9, 2), date(2026, 9, 1)),
        )

    assert caught.value.code == "invalid_range"
    assert caught.value.status_code == 422


def test_compare_route_reports_an_invalid_period_b_range(client: TestClient) -> None:
    response = client.get(
        "/context/compare",
        params={
            "user_id": 1,
            "period_a_start": "2026-08-01",
            "period_a_end": "2026-08-31",
            "period_b_start": "2026-09-02",
            "period_b_end": "2026-09-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_range"


def test_compare_tool_reports_an_unknown_user(session: Session) -> None:
    with pytest.raises(ToolError) as caught:
        compare_periods(
            session,
            999,
            (date(2026, 8, 1), date(2026, 8, 31)),
            (date(2026, 9, 1), date(2026, 9, 30)),
        )

    assert caught.value.code == "user_not_found"
    assert caught.value.status_code == 404


def test_compare_route_reports_an_unknown_user(client: TestClient) -> None:
    response = client.get(
        "/context/compare",
        params={
            "user_id": 999,
            "period_a_start": "2026-08-01",
            "period_a_end": "2026-08-31",
            "period_b_start": "2026-09-01",
            "period_b_end": "2026-09-30",
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"
