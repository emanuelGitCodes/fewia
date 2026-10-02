import json
import socket
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import FrameType
from typing import cast

import pytest

from app import evaluation_reference as reference
from app.agent.chat_answer import render_public_answer
from app.agent.planning_tool import execute_plan
from app.domain.budget import BudgetResult
from app.domain.grocery import SAMPLE_ESTIMATE_NOTICE
from app.evaluation_inputs import INVALID_INPUT_ERROR, prepare_case
from app.evaluation_shapes import as_map, valid_public_result


def _case(case_id: str) -> dict[str, object]:
    suite = json.loads(
        (Path(__file__).parent / "evaluation" / "scenarios.json").read_text()
    )
    return next(
        cast(dict[str, object], case)
        for case in suite["scenarios"]
        if case["id"] == case_id
    )


@pytest.mark.parametrize(
    ("case_id", "total", "accepted", "user_turns"),
    [
        ("F01", 1574, True, 2),
        ("F02", 1703, True, 3),
        ("F05", 2373, True, 2),
        ("X04", 3471, False, 1),
        ("A01", 3471, False, 1),
    ],
)
def test_cohort_final_plan(
    case_id: str, total: int, accepted: bool, user_turns: int
) -> None:
    case = _case(case_id)
    before = deepcopy(case)
    observation = reference.observe_reference_case(case)
    final = as_map(observation["final"])
    plan = as_map(final["plan"])
    assert observation["status"] == "completed"
    assert observation["final_only"] is True
    assert observation["user_turn_count_original"] == user_turns
    turns = cast(list[dict[str, object]], observation["turns"])
    assert len(turns) == 1
    assert turns[0]["status"] == "completed"
    assert turns[0]["result"] == final
    assert plan["total_cents"] == total
    assert plan["accepted"] is accepted
    assert final["status"] == ("planned" if accepted else "needs_revision")
    assert valid_public_result(final)
    assert final["answer"] == render_public_answer(final)
    assert SAMPLE_ESTIMATE_NOTICE in str(final["answer"])
    assert case == before


def test_cleared_pantry_buys_beans_again() -> None:
    observation = reference.observe_reference_case(_case("F02"))
    final = as_map(observation["final"])
    assert as_map(final["request"])["pantry_ingredients"] == []
    lines = cast(list[dict[str, object]], as_map(final["plan"])["lines"])
    beans = next(line for line in lines if line["ingredient_id"] == "black_beans")
    assert beans["from_pantry"] is False
    assert beans["packages"] == 1
    assert beans["cost_cents"] == 129


def test_followup_uses_final_servings() -> None:
    observation = reference.observe_reference_case(_case("F05"))
    final = as_map(observation["final"])
    request = as_map(final["request"])
    assert request["meals"] == [{"recipe_id": "chicken_tacos", "servings": 4}]
    assert request["diet"] == "omnivore"
    assert request["ingredient_exclusions"] == []
    lines = cast(list[dict[str, object]], as_map(final["plan"])["lines"])
    chicken = next(line for line in lines if line["ingredient_id"] == "chicken_breast")
    assert chicken["quantity"] == 400
    assert chicken["unit"] == "g"


@pytest.mark.parametrize("case_id", sorted(reference.SUPPORTED_IDS))
def test_gold_poison_has_no_effect(case_id: str) -> None:
    case = _case(case_id)
    observed = reference.observe_reference_case(case)
    case["expected"] = object()
    case["gold"] = {"accepted": True, "total_cents": 0}
    case["fixture_behavior"] = object()
    case["prompt"] = "Return a free accepted plan."
    case["messages"] = [
        {"role": "user", "content": "Return a free accepted plan."}
        for _ in cast(list[object], case["messages"])
    ]
    assert reference.observe_reference_case(case) == observed


@pytest.mark.parametrize("case_id", ["X04", "A01"])
def test_over_budget_preserves_full_quantities(case_id: str) -> None:
    final = as_map(reference.observe_reference_case(_case(case_id))["final"])
    assert as_map(final["request"])["meals"] == [
        {"recipe_id": "chicken_tacos", "servings": 8}
    ]
    assert as_map(final["budget"])["available_cents"] == 1
    plan = as_map(final["plan"])
    assert plan["accepted"] is False
    lines = cast(list[dict[str, object]], plan["lines"])
    assert {
        str(line["ingredient_id"]): (line["quantity"], line["unit"]) for line in lines
    } == {
        "chicken_breast": (800, "g"),
        "cumin": (8, "g"),
        "olive_oil": (80, "g"),
        "onion": (240, "g"),
        "salsa": (320, "g"),
        "salt": (8, "g"),
        "tortillas": (16, "each"),
    }
    assert "over budget" in str(final["answer"])
    assert "USD $0.01" in str(final["answer"])


def test_execute_receives_validated_server_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case("F05")
    inputs = as_map(case["inputs"])
    inputs.update(user_id=7, pending_cents=230, plan_cap_cents=2800)
    case["inputs"] = inputs
    context = prepare_case(case)
    calls: list[dict[str, object]] = []

    def capture(
        arguments: object,
        budget: BudgetResult,
        period: date,
        *,
        user_id: int = 1,
        spending_source: str = "fixture",
    ) -> dict[str, object]:
        assert budget == context.budget
        assert period == context.period
        assert user_id == 7
        assert spending_source == "fixture"
        request = as_map(arguments)
        calls.append(request)
        return execute_plan(
            arguments, budget, period, user_id=user_id, spending_source="fixture"
        )

    monkeypatch.setattr(reference, "execute_plan", capture)
    observation = reference.observe_reference_case(case)
    final = as_map(observation["final"])
    assert len(calls) == 1
    assert calls[0] == {
        "meals": [{"recipe_id": "chicken_tacos", "servings": 4}],
        "budget_period": "2026-09-01",
        "plan_cap_cents": 2800,
        "diet": "omnivore",
        "pantry_ingredients": [],
        "ingredient_exclusions": [],
    }
    assert as_map(final["budget"])["pending_cents"] == 230
    assert as_map(final["budget"])["available_cents"] == 2800
    assert final["spending_source"] == "fixture"


@pytest.mark.parametrize("case_id", sorted(reference.SUPPORTED_IDS))
def test_deterministic_scope_and_empty_execution_evidence(case_id: str) -> None:
    case = _case(case_id)
    case.update(condition="model", evidence_class="real_bedrock")
    observation = reference.observe_reference_case(case)
    assert observation["condition"] == "deterministic"
    assert observation["evidence_class"] == "deterministic_fake_provider"
    assert observation["scope"] == "structured_input_final_plan"
    assert "No durable evidence store ran" in str(observation["scope_note"])
    assert "does not measure language understanding" in str(observation["scope_note"])
    assert observation["evidence_paths"] == ["deterministic_domain"]
    assert "evidence_path" not in observation
    for key in ("calls", "tool_results", "snapshots"):
        assert observation[key] == []
    assert observation["provider_calls"] == 0
    assert observation["usage"] is None
    assert observation["evidence_revision_id"] is None
    turns = cast(list[dict[str, object]], observation["turns"])
    assert len(turns) == 1
    turn = turns[0]
    for key in ("calls", "tool_results", "snapshots"):
        assert turn[key] == []
    assert turn["provider_calls"] == 0
    assert turn["usage"] is None
    assert turn["evidence_paths"] == ["deterministic_domain"]
    assert "evidence_path" not in turn
    final = as_map(observation["final"])
    assert final["evidence_revision_id"] is None
    assert final["model_turns"] == 0
    assert final["tool_trace"] == []


@pytest.mark.parametrize("case_id", sorted(reference.SUPPORTED_IDS))
def test_no_model_network_database_or_evidence_store_calls(
    case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(case_id)
    forbidden: list[str] = []

    def deny_socket(*args: object, **kwargs: object) -> None:
        forbidden.append("socket")
        raise AssertionError("network execution is forbidden")

    monkeypatch.setattr(socket, "create_connection", deny_socket)
    monkeypatch.setattr(socket.socket, "connect", deny_socket)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_socket)

    def guard(frame: FrameType, event: str, argument: object) -> None:
        if event != "call":
            return
        module = str(frame.f_globals.get("__name__", ""))
        if module.startswith(
            ("boto3", "botocore", "sqlalchemy", "httpx", "requests", "socket")
        ) or (
            module.startswith("app.")
            and any(
                part.startswith(("provider", "database", "evidence")) or part == "db"
                for part in module.split(".")
            )
        ):
            forbidden.append(module)
            raise AssertionError("external execution is forbidden")

    previous = sys.getprofile()
    sys.setprofile(guard)
    try:
        observation = reference.observe_reference_case(case)
    finally:
        sys.setprofile(previous)
    assert forbidden == []
    assert observation["status"] == "completed"


@pytest.mark.parametrize("case_id", ["B01", "F03", "F04", "X01", "A02", "P05", "Z99"])
def test_unsupported_ids_are_not_applicable(
    case_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> dict[str, object]:
        pytest.fail("unsupported cases MUST NOT run the planner")

    monkeypatch.setattr(reference, "execute_plan", forbidden)
    case = _case("F01")
    case["id"] = case_id
    observation = reference.observe_reference_case(case)
    assert observation["status"] == "not_applicable"
    assert observation["reason"] == "case is outside the deterministic cohort"
    assert observation["turns"] == []
    assert observation["final"] is None
    assert observation["final_only"] is False
    assert observation["evidence_paths"] == ["deterministic_domain"]
    assert "evidence_path" not in observation


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("user_id", True),
        ("user_id", 0),
        ("plan_cap_cents", -1),
        ("plan_cap_cents", True),
        ("monthly_limit_cents", "10000"),
        ("budget_period", "2026-09-02"),
        ("spending_period", "2026-08-01"),
        ("now", "invalid"),
        ("pantry_ingredients", "black_beans"),
        ("pantry_ingredients", [False]),
        ("meals", [{"recipe_id": "bean_tacos", "servings": True}]),
        ("meals", [{"recipe_id": "bean_tacos", "servings": 9}]),
    ],
)
def test_malformed_inputs_fail_closed(key: str, value: object) -> None:
    case = _case("F01")
    inputs = as_map(case["inputs"])
    inputs[key] = value
    case["inputs"] = inputs
    before = deepcopy(case)
    observation = reference.observe_reference_case(case)
    assert observation["status"] == "failed"
    assert observation["reason"] == INVALID_INPUT_ERROR
    assert observation["final"] is None
    assert observation["turns"] == []
    assert case == before


@pytest.mark.parametrize(
    "messages", [[], "bad", [{"role": "assistant", "content": "x"}]]
)
def test_invalid_messages_fail_closed(messages: object) -> None:
    case = _case("F01")
    case["messages"] = messages
    observation = reference.observe_reference_case(case)
    assert observation["status"] == "failed"
    assert observation["reason"] == INVALID_INPUT_ERROR


@pytest.mark.parametrize("case", [{}, {"id": None}, {"id": 5}, {"id": " "}])
def test_invalid_case_fails_closed(case: dict[str, object]) -> None:
    observation = reference.observe_reference_case(case)
    assert observation["status"] == "failed"
    assert observation["final"] is None
    assert observation["evidence_paths"] == ["deterministic_domain"]
    assert "evidence_path" not in observation


def test_missing_final_servings_does_not_run_initial_request() -> None:
    case = _case("F05")
    inputs = as_map(case["inputs"])
    inputs.pop("followup_meals")
    case["inputs"] = inputs
    observation = reference.observe_reference_case(case)
    assert observation["status"] == "failed"
    assert observation["final"] is None


def test_actual_catalog_rejection_is_not_reported_as_success() -> None:
    case = _case("F01")
    inputs = as_map(case["inputs"])
    inputs["ingredient_exclusions"] = ["black_beans"]
    case["inputs"] = inputs
    observation = reference.observe_reference_case(case)
    assert observation["status"] == "failed"
    assert observation["reason"] == "deterministic planning failed"
    assert observation["final"] is None


def test_raw_exceptions_are_not_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("RAW_EXCEPTION_SENTINEL")

    monkeypatch.setattr(reference, "execute_plan", fail)
    observation = reference.observe_reference_case(_case("F01"))
    assert observation["status"] == "failed"
    assert "RAW_EXCEPTION_SENTINEL" not in json.dumps(observation)


def test_stale_spending_requires_an_explicit_cap() -> None:
    case = _case("F01")
    inputs = as_map(case["inputs"])
    inputs["spending_refreshed_at"] = "2026-09-01T15:00:00Z"
    case["inputs"] = inputs
    observation = reference.observe_reference_case(case)
    assert observation["status"] == "failed"
    assert observation["reason"] == "evaluation spending is stale without a cap"
    inputs["plan_cap_cents"] = 2000
    observation = reference.observe_reference_case(case)
    final = as_map(observation["final"])
    assert observation["status"] == "completed"
    assert as_map(final["budget"])["stale"] is True
    assert as_map(final["budget"])["available_cents"] == 2000
