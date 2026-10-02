from copy import deepcopy
from datetime import date, datetime

import pytest

from app.domain.grocery import GroceryRequest, MealRequest
from app.evaluation_plan_schema import (
    ObservedBudget,
    ObservedPlan,
    PlanLine,
    PlanObservation,
    parse_plan_observation,
)


@pytest.fixture
def observation() -> dict[str, object]:
    return {
        "request": {
            "meals": [{"recipe_id": "bean_tacos", "servings": 2}],
            "budget_period": "2026-10-01",
            "plan_cap_cents": 1000,
            "pantry_ingredients": [],
            "ingredient_exclusions": [],
            "diet": "omnivore",
        },
        "plan": {
            "lines": [
                {
                    "ingredient_id": "beans",
                    "name": "Beans",
                    "unit": "g",
                    "quantity": 200,
                    "packages": 1,
                    "cost_cents": 150,
                    "from_pantry": False,
                }
            ],
            "total_cents": 150,
            "accepted": True,
            "catalog_version": "sample-v1",
            "notice": "Sample estimate",
        },
        "budget": {"available_cents": 1000, "pending_cents": 0, "stale": False},
    }


def _section(observation: dict[str, object], key: str) -> dict[str, object]:
    section = observation[key]
    assert isinstance(section, dict)
    return section


def _line(observation: dict[str, object]) -> dict[str, object]:
    lines = _section(observation, "plan")["lines"]
    assert isinstance(lines, list)
    line = lines[0]
    assert isinstance(line, dict)
    return line


def test_complete_observation_has_typed_values(observation: dict[str, object]) -> None:
    parsed = parse_plan_observation(observation)
    assert isinstance(parsed, PlanObservation)
    assert isinstance(parsed.request, GroceryRequest)
    assert isinstance(parsed.request.meals[0], MealRequest)
    assert type(parsed.request.budget_period) is date
    assert parsed.request.budget_period == date(2026, 10, 1)
    assert parsed.request.meals[0].servings == 2
    assert parsed.request.plan_cap_cents == 1000
    assert isinstance(parsed.plan, ObservedPlan)
    assert isinstance(parsed.plan.lines[0], PlanLine)
    assert parsed.plan.lines[0].quantity == 200
    assert parsed.plan.total_cents == 150
    assert parsed.plan.accepted is True
    assert isinstance(parsed.budget, ObservedBudget)
    assert parsed.budget.available_cents == 1000
    assert parsed.budget.stale is False


@pytest.mark.parametrize("field", list(GroceryRequest.model_fields))
def test_missing_request_field_is_rejected(
    observation: dict[str, object], field: str
) -> None:
    del _section(observation, "request")[field]
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize(
    "period",
    [
        1790812800,
        1790812800.0,
        True,
        False,
        date(2026, 10, 1),
        datetime(2026, 10, 1),
        "20261001",
        "2026-1-01",
        "2026-10-1",
        "2026-10-01T00:00:00",
        "2026-10-01 ",
        "２０２６-１０-０１",
        "2026-13-01",
        "2026-10-02",
        None,
    ],
)
def test_noncanonical_or_invalid_period_is_rejected(
    observation: dict[str, object], period: object
) -> None:
    _section(observation, "request")["budget_period"] = period
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize("value", ["1", 1.0, True, False, -1])
def test_request_cap_is_strict(observation: dict[str, object], value: object) -> None:
    _section(observation, "request")["plan_cap_cents"] = value
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize("value", ["1", 1.0, True, False, 0, 9])
def test_request_servings_are_strict(
    observation: dict[str, object], value: object
) -> None:
    _section(observation, "request")["meals"] = [
        {"recipe_id": "bean_tacos", "servings": value}
    ]
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("diet", True),
        ("pantry_ingredients", [True]),
        ("ingredient_exclusions", [1]),
        ("meals", [{"recipe_id": True, "servings": 1}]),
        ("unexpected", False),
    ],
)
def test_invalid_request_values_are_rejected(
    observation: dict[str, object], field: str, value: object
) -> None:
    _section(observation, "request")[field] = value
    assert parse_plan_observation(observation) is None


def test_raw_request_requires_exact_dict(observation: dict[str, object]) -> None:
    class RequestDict(dict[str, object]):
        pass

    request = _section(observation, "request")
    observation["request"] = RequestDict(request)
    assert parse_plan_observation(observation) is None
    observation["request"] = GroceryRequest.model_validate(request)
    assert parse_plan_observation(observation) is None


def test_raw_period_requires_exact_string(observation: dict[str, object]) -> None:
    class Period(str):
        pass

    _section(observation, "request")["budget_period"] = Period("2026-10-01")
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ingredient_id", 1),
        ("name", True),
        ("unit", 1),
        ("quantity", "1"),
        ("quantity", 1.0),
        ("quantity", True),
        ("quantity", 0),
        ("packages", "1"),
        ("packages", 1.0),
        ("packages", False),
        ("packages", -1),
        ("cost_cents", "1"),
        ("cost_cents", 1.0),
        ("cost_cents", True),
        ("cost_cents", -1),
        ("from_pantry", 0),
        ("from_pantry", "false"),
    ],
)
def test_plan_line_values_are_strict(
    observation: dict[str, object], field: str, value: object
) -> None:
    _line(observation)[field] = value
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize("field", list(PlanLine.model_fields))
def test_missing_plan_line_field_is_rejected(
    observation: dict[str, object], field: str
) -> None:
    del _line(observation)[field]
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("plan", "lines", ()),
        ("plan", "total_cents", "1"),
        ("plan", "total_cents", 1.0),
        ("plan", "total_cents", True),
        ("plan", "total_cents", -1),
        ("plan", "accepted", 1),
        ("plan", "accepted", "true"),
        ("plan", "catalog_version", 1),
        ("plan", "notice", True),
        ("budget", "available_cents", "1"),
        ("budget", "available_cents", 1.0),
        ("budget", "available_cents", True),
        ("budget", "available_cents", -1),
        ("budget", "pending_cents", "1"),
        ("budget", "pending_cents", 1.0),
        ("budget", "pending_cents", False),
        ("budget", "stale", 0),
        ("budget", "stale", "false"),
    ],
)
def test_plan_and_budget_values_are_strict(
    observation: dict[str, object], section: str, field: str, value: object
) -> None:
    _section(observation, section)[field] = value
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize(
    ("section", "field"),
    [("plan", field) for field in ObservedPlan.model_fields]
    + [("budget", field) for field in ObservedBudget.model_fields],
)
def test_missing_plan_or_budget_field_is_rejected(
    observation: dict[str, object], section: str, field: str
) -> None:
    del _section(observation, section)[field]
    assert parse_plan_observation(observation) is None


@pytest.mark.parametrize("section", ["request", "plan", "budget"])
def test_missing_observation_section_is_rejected(
    observation: dict[str, object], section: str
) -> None:
    del observation[section]
    assert parse_plan_observation(observation) is None


def test_nullable_costs_and_negative_pending_are_preserved(
    observation: dict[str, object],
) -> None:
    _section(observation, "request")["plan_cap_cents"] = None
    _line(observation)["cost_cents"] = None
    _section(observation, "plan")["total_cents"] = None
    _section(observation, "plan")["accepted"] = False
    _section(observation, "budget")["pending_cents"] = -100
    parsed = parse_plan_observation(observation)
    assert parsed is not None
    assert parsed.request.plan_cap_cents is None
    assert parsed.plan.lines[0].cost_cents is None
    assert parsed.plan.total_cents is None
    assert parsed.plan.accepted is False
    assert parsed.budget.pending_cents == -100


@pytest.mark.parametrize("case", ["valid", "missing", "date", "plan"])
def test_input_is_not_mutated(observation: dict[str, object], case: str) -> None:
    if case == "missing":
        del _section(observation, "request")["diet"]
    elif case == "date":
        _section(observation, "request")["budget_period"] = date(2026, 10, 1)
    elif case == "plan":
        _line(observation)["quantity"] = True
    original = deepcopy(observation)
    parsed = parse_plan_observation(observation)
    assert (parsed is not None) == (case == "valid")
    assert observation == original
