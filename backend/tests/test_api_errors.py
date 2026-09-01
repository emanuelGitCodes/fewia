"""Tests for API error responses."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import NamedTuple

import pytest
from conftest import UserSeeder
from fastapi.testclient import TestClient

type QueryParameters = dict[str, int | str]
type RangeParameterBuilder = Callable[[date, date], QueryParameters]


def _context_parameters(start_date: date, end_date: date) -> QueryParameters:
    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }


def _compare_parameters(start_date: date, end_date: date) -> QueryParameters:
    return {
        "period_a_start": start_date.isoformat(),
        "period_a_end": end_date.isoformat(),
        "period_b_start": start_date.isoformat(),
        "period_b_end": end_date.isoformat(),
    }


class Endpoint(NamedTuple):
    path: str
    parameters: RangeParameterBuilder
    missing_parameter: str


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("/context/health", _context_parameters, "end_date"),
    Endpoint("/context/financial", _context_parameters, "end_date"),
    Endpoint("/context/environment", _context_parameters, "end_date"),
    Endpoint("/context/compare", _compare_parameters, "period_b_end"),
    Endpoint("/predict/activity", _context_parameters, "end_date"),
)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_endpoints_report_an_unknown_user_with_the_error_contract(
    client: TestClient, endpoint: Endpoint
) -> None:
    params = {
        "user_id": 999,
        **endpoint.parameters(date(2026, 1, 1), date(2026, 1, 1)),
    }

    response = client.get(endpoint.path, params=params)
    body = response.json()

    assert response.status_code == 404
    assert body == {
        "error": {
            "code": "user_not_found",
            "message": "No user has the id 999.",
        }
    }
    assert isinstance(body["error"]["message"], str)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_endpoints_report_a_reversed_range_with_the_error_contract(
    client: TestClient, endpoint: Endpoint
) -> None:
    params = {
        "user_id": 999,
        **endpoint.parameters(date(2026, 1, 2), date(2026, 1, 1)),
    }

    response = client.get(endpoint.path, params=params)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_range",
            "message": "start_date MUST NOT come after end_date.",
        }
    }


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_endpoints_reject_367_days_and_accept_366_days(
    client: TestClient, endpoint: Endpoint, seed_user: UserSeeder
) -> None:
    start_date = date(2024, 1, 1)
    accepted_end_date = start_date + timedelta(days=365)
    rejected_end_date = start_date + timedelta(days=366)
    rejected_params = {
        "user_id": 999,
        **endpoint.parameters(start_date, rejected_end_date),
    }

    rejected_response = client.get(endpoint.path, params=rejected_params)
    user_id = seed_user()
    accepted_params = {
        "user_id": user_id,
        **endpoint.parameters(start_date, accepted_end_date),
    }
    accepted_response = client.get(endpoint.path, params=accepted_params)

    assert rejected_response.status_code == 422
    assert rejected_response.json()["error"]["code"] == "invalid_range"
    assert accepted_response.status_code == 200


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_endpoints_keep_fastapi_and_tool_error_422_bodies_distinct(
    client: TestClient, endpoint: Endpoint
) -> None:
    valid_params = {
        "user_id": 999,
        **endpoint.parameters(date(2026, 1, 1), date(2026, 1, 2)),
    }
    valid_params.pop(endpoint.missing_parameter)
    tool_error_params = {
        "user_id": 999,
        **endpoint.parameters(date(2026, 1, 2), date(2026, 1, 1)),
    }

    validation_response = client.get(endpoint.path, params=valid_params)
    tool_error_response = client.get(endpoint.path, params=tool_error_params)
    validation_body = validation_response.json()
    tool_error_body = tool_error_response.json()

    assert validation_response.status_code == 422
    assert "detail" in validation_body
    assert "error" not in validation_body
    assert tool_error_response.status_code == 422
    assert "error" in tool_error_body
    assert "detail" not in tool_error_body
