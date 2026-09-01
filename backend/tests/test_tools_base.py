"""Tests for the shared tool helpers."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app
from app.tools.base import (
    ToolError,
    build_evidence_id,
    missing_day_warnings,
    round_money,
    validate_range,
)


def test_evidence_id_uses_month_form_for_a_whole_month() -> None:
    got = build_evidence_id("health", 1, date(2026, 8, 1), date(2026, 8, 31))
    assert got == "health:user-1:2026-08"


def test_evidence_id_uses_day_form_for_any_other_range() -> None:
    got = build_evidence_id("health", 1, date(2026, 7, 15), date(2026, 8, 4))
    assert got == "health:user-1:2026-07-15..2026-08-04"


def test_evidence_id_uses_day_form_for_a_partial_month() -> None:
    got = build_evidence_id("finance", 2, date(2026, 8, 1), date(2026, 8, 30))
    assert got == "finance:user-2:2026-08-01..2026-08-30"


def test_validate_range_accepts_a_single_day() -> None:
    validate_range(date(2026, 8, 1), date(2026, 8, 1))


def test_validate_range_rejects_a_reversed_range() -> None:
    with pytest.raises(ToolError) as caught:
        validate_range(date(2026, 8, 2), date(2026, 8, 1))
    assert caught.value.code == "invalid_range"
    assert caught.value.status_code == 422


def test_validate_range_rejects_a_long_range() -> None:
    with pytest.raises(ToolError):
        validate_range(date(2024, 1, 1), date(2025, 1, 5))


def test_missing_day_warnings_reports_an_empty_range() -> None:
    warnings = missing_day_warnings(0, date(2026, 8, 1), date(2026, 8, 31))
    assert [w.code for w in warnings] == ["no_records"]
    assert warnings[0].detail == {"record_count": "0", "day_count": "31"}


def test_missing_day_warnings_reports_missing_days() -> None:
    warnings = missing_day_warnings(30, date(2026, 8, 1), date(2026, 8, 31))
    assert [w.code for w in warnings] == ["missing_days"]


def test_missing_day_warnings_stays_empty_for_a_full_range() -> None:
    assert missing_day_warnings(31, date(2026, 8, 1), date(2026, 8, 31)) == []


def test_round_money_rounds_to_two_decimals() -> None:
    assert round_money(10.005) == 10.01
    assert round_money(3.14159) == 3.14


def test_tool_error_handler_returns_the_error_body() -> None:
    test_app = FastAPI()
    for exc_class, handler in app.exception_handlers.items():
        test_app.add_exception_handler(exc_class, handler)  # type: ignore[arg-type]

    @test_app.get("/boom")
    def boom() -> None:
        raise ToolError(code="user_not_found", message="No user.", status_code=404)

    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "user_not_found", "message": "No user."}
    }
