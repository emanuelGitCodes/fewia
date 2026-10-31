import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_plan_facts import plan_integrity
from app.evaluation_plan_score import score_plan

_IDS = ("F01", "F02", "F05", "X04", "A01")
_NOTICE = (
    "Estimated from the demo price catalog. Store prices, availability, taxes, "
    "delivery fees, and tips are not verified."
)


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    assert type(value) is list
    return cast(list[object], value)


def _case(case_id: str) -> dict[str, object]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    suite = _map(json.loads(path.read_text()))
    return next(
        _map(case) for case in _list(suite["scenarios"]) if _map(case)["id"] == case_id
    )


def _result(inputs: dict[str, object]) -> dict[str, object]:
    meals = _list(inputs.get("followup_meals", inputs["meals"]))
    meal = _map(meals[0])
    servings = cast(int, meal["servings"])
    chicken = meal["recipe_id"] == "chicken_tacos"
    pantry = _list(inputs["pantry_ingredients"])
    protein = (
        ("chicken_breast", "chicken breast", "g", 100, 500, 799)
        if chicken
        else ("black_beans", "black beans", "g", 120, 400, 129)
    )
    ingredients = (
        protein,
        ("cumin", "ground cumin", "g", 1, 40, 199),
        ("olive_oil", "olive oil", "g", 10, 500, 599),
        ("onion", "onion", "g", 30, 500, 129),
        ("salsa", "salsa", "g", 40, 454, 249),
        ("salt", "salt", "g", 1, 737, 99),
        ("tortillas", "corn tortillas", "each", 2, 12, 299),
    )
    lines: list[dict[str, object]] = []
    total = 0
    for ingredient_id, name, unit, amount, package_quantity, price in ingredients:
        quantity = amount * servings
        from_pantry = ingredient_id in pantry
        packages = (
            0 if from_pantry else (quantity + package_quantity - 1) // package_quantity
        )
        cost = packages * price
        total += cost
        lines.append(
            {
                "ingredient_id": ingredient_id,
                "name": name,
                "unit": unit,
                "quantity": quantity,
                "packages": packages,
                "cost_cents": cost,
                "from_pantry": from_pantry,
            }
        )
    limit = cast(int, inputs["monthly_limit_cents"])
    posted = cast(int, inputs["posted_cents"])
    pending = cast(int, inputs["pending_cents"])
    remaining = max(0, limit - posted)
    budget = fixture_budget(inputs)
    available = budget.available_cents
    accepted = total <= available
    request = {
        key: deepcopy(inputs[key])
        for key in (
            "diet",
            "budget_period",
            "plan_cap_cents",
            "pantry_ingredients",
            "ingredient_exclusions",
        )
    }
    request["meals"] = deepcopy(meals)
    return {
        "status": "planned" if accepted else "needs_revision",
        "answer": "Sample estimate.",
        "request": request,
        "plan": {
            "accepted": accepted,
            "total_cents": total,
            "lines": lines,
            "notice": _NOTICE,
            "catalog_version": "sample-prices-v2",
            "warnings": []
            if accepted
            else ["The estimate exceeds the available budget."],
        },
        "budget": {
            "monthly_limit_cents": limit,
            "posted_cents": posted,
            "pending_cents": pending,
            "remaining_cents": remaining,
            "available_cents": available,
            "stale": budget.stale,
        },
    }


def _observation(
    case: dict[str, object], condition: str = "tool_enabled"
) -> dict[str, object]:
    result = _result(_map(case["inputs"]))
    return {
        "case_id": case["id"],
        "condition": condition,
        "status": "completed",
        "turns": [
            {"status": "completed", "result": deepcopy(result)}
            for _ in _list(case["messages"])
        ],
    }


def _final(observation: dict[str, object]) -> dict[str, object]:
    return _map(_map(_list(observation["turns"])[-1])["result"])


def _checks(score: dict[str, object]) -> dict[str, object]:
    return _map(score["checks"])


@pytest.mark.parametrize("case_id", _IDS)
@pytest.mark.parametrize("condition", ("deterministic", "tool_enabled", "no_tool"))
def test_complete_final_plan(case_id: str, condition: str) -> None:
    case = _case(case_id)
    observation = _observation(case, condition)
    assert all(plan_integrity(_final(observation)).values())
    score = score_plan(case, observation)
    assert score["status"] == "passed", score
    assert score["scope"] == "final_plan"
    assert score["constraint_violations"] == []
    assert "durable evidence ownership" in str(score["scope_note"])


@pytest.mark.parametrize("case_id", _IDS)
def test_deterministic_explicit_final_only(case_id: str) -> None:
    case = _case(case_id)
    observation = _observation(case, "deterministic")
    observation["user_turn_count_original"] = len(_list(case["messages"]))
    observation["final_only"] = True
    observation["turns"] = [_list(observation["turns"])[-1]]
    assert score_plan(case, observation)["status"] == "passed"


@pytest.mark.parametrize("condition", ("tool_enabled", "no_tool"))
@pytest.mark.parametrize("case_id", _IDS)
def test_other_conditions_cannot_use_final_only(case_id: str, condition: str) -> None:
    case = _case(case_id)
    observation = _observation(case, condition)
    observation.update(
        final_only=True, user_turn_count_original=len(_list(case["messages"]))
    )
    observation["turns"] = [_list(observation["turns"])[-1]]
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert "final_scope" in _list(score["constraint_violations"])


@pytest.mark.parametrize("count", (None, True, 1, 3, "2"))
def test_final_only_requires_original_count(count: object) -> None:
    case = _case("F01")
    observation = _observation(case, "deterministic")
    observation.update(final_only=True, user_turn_count_original=count)
    observation["turns"] = [_list(observation["turns"])[-1]]
    assert score_plan(case, observation)["status"] == "failed"


def test_final_only_is_limited_to_named_cases() -> None:
    case = _case("F01")
    case["id"] = "OTHER"
    observation = _observation(case, "deterministic")
    observation.update(final_only=True, user_turn_count_original=2)
    observation["turns"] = [_list(observation["turns"])[-1]]
    assert _checks(score_plan(case, observation))["final_scope"] is False


def test_old_turn_count_alias_cannot_satisfy_final_scope() -> None:
    case = _case("F01")
    observation = _observation(case, "deterministic")
    observation.update(final_only=True, user_turn_count=len(_list(case["messages"])))
    observation["turns"] = [_list(observation["turns"])[-1]]
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["final_scope"] is False


@pytest.mark.parametrize("key", ("case_id", "condition", "status", "turns"))
def test_missing_observation_fields_fail(key: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    observation.pop(key)
    assert score_plan(case, observation)["status"] == "failed"


@pytest.mark.parametrize("status", ("failed", "partial", "running", None))
def test_incomplete_observation_cannot_pass(status: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    observation["status"] = status
    assert _checks(score_plan(case, observation))["observation_complete"] is False


@pytest.mark.parametrize("condition", ("model", "unknown", None, [], True, "MODEL"))
def test_invalid_condition(condition: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    observation["condition"] = condition
    assert _checks(score_plan(case, observation))["condition"] is False


def test_case_mismatch_fails() -> None:
    case = _case("F01")
    observation = _observation(case)
    observation["case_id"] = "F02"
    assert _checks(score_plan(case, observation))["case_identity"] is False


@pytest.mark.parametrize("case_id", ("", " ", "\t\n", "\u2003"))
def test_matching_blank_case_ids_fail(case_id: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    case["id"] = observation["case_id"] = case_id
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["case_identity"] is False
    assert "case_identity" in _list(score["constraint_violations"])


def test_matching_normal_case_id_passes() -> None:
    case = _case("F01")
    observation = _observation(case)
    score = score_plan(case, observation)
    assert score["status"] == "passed"
    assert _checks(score)["case_identity"] is True
    assert score["constraint_violations"] == []


@pytest.mark.parametrize("turns", (None, {}, [], [{"status": "completed"}]))
def test_missing_or_malformed_turns(turns: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    observation["turns"] = turns
    assert _checks(score_plan(case, observation))["turns_complete"] is False


@pytest.mark.parametrize("index", (0, -1))
@pytest.mark.parametrize("problem", ("partial", "missing_result", "bad_result"))
def test_each_turn_must_complete(index: int, problem: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    turn = _map(_list(observation["turns"])[index])
    if problem == "partial":
        turn["status"] = "partial"
    elif problem == "missing_result":
        turn.pop("result")
    else:
        _map(turn["result"]).pop("answer")
    assert _checks(score_plan(case, observation))["turns_complete"] is False


@pytest.mark.parametrize("size", (1, 3))
def test_wrong_turn_count(size: int) -> None:
    case = _case("F01")
    observation = _observation(case)
    turn = _list(observation["turns"])[-1]
    observation["turns"] = [deepcopy(turn) for _ in range(size)]
    assert score_plan(case, observation)["status"] == "failed"


def test_prior_turn_intent_is_outside_final_plan_scope() -> None:
    case = _case("F01")
    observation = _observation(case)
    prior = _map(_map(_list(observation["turns"])[0])["result"])
    _map(prior["request"])["pantry_ingredients"] = []
    prior["answer"] = "This earlier language is outside final-plan scope."
    assert score_plan(case, observation)["status"] == "passed"


@pytest.mark.parametrize(
    ("case_id", "field", "value", "check"),
    (
        ("F01", "diet", "vegetarian", "request_diet"),
        ("F01", "budget_period", "2026-10-01", "request_budget_period"),
        ("F01", "plan_cap_cents", 5000, "request_plan_cap_cents"),
        ("F01", "pantry_ingredients", [], "request_pantry_ingredients"),
        ("F01", "ingredient_exclusions", ["eggs"], "request_ingredient_exclusions"),
        (
            "F05",
            "followup_meals",
            [{"recipe_id": "chicken_tacos", "servings": 2}],
            "request_meals",
        ),
        (
            "F02",
            "meals",
            [{"recipe_id": "chicken_tacos", "servings": 2}],
            "request_meals",
        ),
    ),
)
def test_wrong_intent_despite_correct_arithmetic(
    case_id: str, field: str, value: object, check: str
) -> None:
    case = _case(case_id)
    observation = _observation(case)
    altered = deepcopy(_map(case["inputs"]))
    if field == "budget_period":
        altered["spending_period"] = altered.get("spending_period", altered[field])
    altered[field] = value
    _map(_list(observation["turns"])[-1])["result"] = _result(altered)
    assert all(plan_integrity(_final(observation)).values())
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)[check] is False
    assert check in _list(score["constraint_violations"])


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("plan_cap_cents", True),
        ("diet", False),
        ("meals", [{"recipe_id": "chicken_tacos", "servings": True}]),
        ("pantry_ingredients", [True]),
        ("ingredient_exclusions", [1]),
    ),
)
def test_wrong_request_types_and_bool_spoof(field: str, value: object) -> None:
    case = _case("A01")
    observation = _observation(case)
    _map(_final(observation)["request"])[field] = value
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)[f"request_{field}"] is False


@pytest.mark.parametrize("field", ("pantry_ingredients", "ingredient_exclusions"))
@pytest.mark.parametrize("value", (["black_beans", "black_beans"], "black_beans", [1]))
def test_duplicate_or_invalid_constraints(field: str, value: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    _map(_final(observation)["request"])[field] = deepcopy(value)
    assert _checks(score_plan(case, observation))[f"request_{field}"] is False


def test_constraint_and_golden_line_order_is_irrelevant() -> None:
    case = _case("F01")
    inputs = _map(case["inputs"])
    inputs["pantry_ingredients"] = ["black_beans", "salt"]
    inputs["ingredient_exclusions"] = ["eggs", "chicken_breast"]
    observation = _observation(case)
    final = _final(observation)
    plan = _map(final["plan"])
    expected = _map(case["expected"])
    expected["lines"] = deepcopy(plan["lines"])
    expected["total_cents"] = plan["total_cents"]
    request = _map(final["request"])
    request["pantry_ingredients"] = ["salt", "black_beans"]
    request["ingredient_exclusions"] = ["chicken_breast", "eggs"]
    plan["lines"] = list(reversed(_list(plan["lines"])))
    assert score_plan(case, observation)["status"] == "passed"


@pytest.mark.parametrize(
    ("field", "value", "check"),
    (
        ("quantity", 239, "integrity_quantities"),
        ("packages", 1, "integrity_package_rounding"),
        ("cost_cents", 1, "integrity_sample_costs"),
        ("from_pantry", False, "integrity_quantities"),
        ("unit", "each", "integrity_quantities"),
    ),
)
def test_independent_line_checks(field: str, value: object, check: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    line = _map(_list(_map(_final(observation)["plan"])["lines"])[0])
    line[field] = value
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)[check] is False
    assert _checks(score)["golden_lines"] is False


def test_duplicate_lines_fail() -> None:
    case = _case("F01")
    observation = _observation(case)
    lines = _list(_map(_final(observation)["plan"])["lines"])
    lines.append(deepcopy(lines[0]))
    score = score_plan(case, observation)
    assert _checks(score)["golden_lines"] is False
    assert _checks(score)["integrity_ingredient_coverage"] is False


def test_golden_mismatch_is_separate_from_arithmetic() -> None:
    case = _case("F01")
    observation = _observation(case)
    golden = _map(_list(_map(case["expected"])["lines"])[0])
    golden["quantity"] = 999
    score = score_plan(case, observation)
    assert _checks(score)["golden_lines"] is False
    assert _checks(score)["integrity_quantities"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("total_cents", True),
        ("accepted", 1),
        ("notice", "Live retailer quote"),
        ("catalog_version", "other"),
    ),
)
def test_wrong_plan_expectations(field: str, value: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    _map(_final(observation)["plan"])[field] = value
    assert score_plan(case, observation)["status"] == "failed"


@pytest.mark.parametrize(
    "fields",
    (
        ("accepted",),
        ("total_cents",),
        ("notice",),
        ("catalog_version",),
        ("accepted", "total_cents", "notice", "catalog_version"),
    ),
)
def test_missing_optional_plan_gold_is_skipped(fields: tuple[str, ...]) -> None:
    case = _case("F01")
    observation = _observation(case)
    expected = _map(case["expected"])
    catalog = _map(_map(expected.get("evidence_ids", {})).get("when_plan_returned", {}))
    for field in fields:
        expected.pop(field, None)
        if field == "catalog_version":
            catalog.pop(field, None)
    assert "lines" in expected
    original_case, original_observation = deepcopy(case), deepcopy(observation)
    score = score_plan(case, observation)
    assert score["status"] == "passed", score
    assert _checks(score)["golden_lines"] is True
    assert all(plan_integrity(_final(observation)).values())
    assert all(f"expected_{field}" not in _checks(score) for field in fields)
    assert case == original_case
    assert observation == original_observation


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("accepted", None),
        ("accepted", 1),
        ("total_cents", None),
        ("total_cents", True),
        ("total_cents", "1248"),
        ("notice", None),
        ("notice", []),
        ("catalog_version", None),
        ("catalog_version", 2),
    ),
)
def test_explicit_malformed_plan_gold_fails(field: str, value: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    _map(case["expected"])[field] = value
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)[f"expected_{field}"] is False
    assert all(plan_integrity(_final(observation)).values())


@pytest.mark.parametrize("value", (None, 2, "other", "sample-prices-v2"))
def test_nested_catalog_gold_compares_when_present(value: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    expected = _map(case["expected"])
    expected.pop("catalog_version", None)
    catalog = _map(
        _map(expected.setdefault("evidence_ids", {})).setdefault(
            "when_plan_returned", {}
        )
    )
    catalog["catalog_version"] = value
    score = score_plan(case, observation)
    matches = value == "sample-prices-v2"
    assert score["status"] == ("passed" if matches else "failed")
    assert _checks(score)["expected_catalog_version"] is matches
    assert all(plan_integrity(_final(observation)).values())


@pytest.mark.parametrize("direct", (None, "sample-prices-v2"))
def test_direct_catalog_gold_takes_precedence(direct: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    expected = _map(case["expected"])
    expected["catalog_version"] = direct
    catalog = _map(
        _map(expected.setdefault("evidence_ids", {})).setdefault(
            "when_plan_returned", {}
        )
    )
    catalog["catalog_version"] = "sample-prices-v2" if direct is None else "other"
    score = score_plan(case, observation)
    assert score["status"] == ("failed" if direct is None else "passed")
    assert _checks(score)["expected_catalog_version"] is (direct is not None)


@pytest.mark.parametrize("field", ("notice", "catalog_version"))
def test_plan_integrity_still_checks_absent_optional_gold(field: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    expected = _map(case["expected"])
    expected.pop("notice", None)
    expected.pop("catalog_version", None)
    catalog = _map(_map(expected.get("evidence_ids", {})).get("when_plan_returned", {}))
    catalog.pop("catalog_version", None)
    assert score_plan(case, observation)["status"] == "passed"
    _map(_final(observation)["plan"])[field] = "Unverified retailer quote"
    integrity = plan_integrity(_final(observation))
    assert not all(integrity.values())
    original_case, original_observation = deepcopy(case), deepcopy(observation)
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert "expected_notice" not in _checks(score)
    assert "expected_catalog_version" not in _checks(score)
    assert _checks(score)["golden_lines"] is True
    assert all(
        _checks(score)[f"integrity_{key}"] is value for key, value in integrity.items()
    )
    assert all(
        str(check).startswith("integrity_")
        for check in _list(score["constraint_violations"])
    )
    assert case == original_case
    assert observation == original_observation


def test_available_budget_uses_scenario_when_gold_omits_it() -> None:
    case = _case("F05")
    observation = _observation(case)
    _map(_final(observation)["budget"])["available_cents"] = 20000
    score = score_plan(case, observation)
    assert _checks(score)["budget_arithmetic"] is False
    assert _checks(score)["integrity_acceptance"] is True


def test_fresh_spending_keeps_pending_separate() -> None:
    case = _case("F01")
    _map(case["inputs"]).update(
        monthly_limit_cents=10000,
        posted_cents=2000,
        pending_cents=3000,
        plan_cap_cents=None,
        budget_period="2026-07-01",
        spending_period="2026-07-01",
        now="2026-07-10T12:00:00Z",
        spending_refreshed_at="2026-07-10T11:00:00Z",
    )
    _map(case["expected"]).update(
        monthly_limit_cents=10000,
        posted_cents=2000,
        pending_cents=3000,
        remaining_cents=8000,
        available_cents=8000,
        stale=False,
    )
    observation = _observation(case)
    budget = _map(_final(observation)["budget"])
    assert budget["available_cents"] == 8000
    assert budget["pending_cents"] == 3000
    assert budget["stale"] is False
    score = score_plan(case, observation)
    assert score["status"] == "passed", score
    budget["available_cents"] = 5000
    score = score_plan(case, observation)
    assert _checks(score)["budget_arithmetic"] is False
    assert all(plan_integrity(_final(observation)).values())


def test_pending_budget_uses_scenario_when_expected_omits_it() -> None:
    case = _case("F01")
    _map(case["inputs"]).update(
        monthly_limit_cents=10000,
        posted_cents=2000,
        pending_cents=3000,
        plan_cap_cents=None,
        budget_period="2026-07-01",
        spending_period="2026-07-01",
        now="2026-07-10T12:00:00Z",
        spending_refreshed_at="2026-07-10T11:00:00Z",
    )
    expected = _map(case["expected"])
    expected.update(
        monthly_limit_cents=10000,
        posted_cents=2000,
        remaining_cents=8000,
        available_cents=8000,
        stale=False,
    )
    expected.pop("pending_cents", None)
    observation = _observation(case)
    budget = _map(_final(observation)["budget"])
    assert _map(case["inputs"])["pending_cents"] == 3000
    assert "pending_cents" not in expected
    assert budget["pending_cents"] == 3000
    score = score_plan(case, observation)
    assert score["status"] == "passed", score
    assert _checks(score)["budget_pending"] is True
    budget["pending_cents"] = 0
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["budget_pending"] is False
    assert "budget_pending" in _list(score["constraint_violations"])
    assert _checks(score)["budget_arithmetic"] is True
    assert _checks(score)["budget_stale"] is True


def test_stale_snapshot_uses_explicit_cap_with_pending_spending() -> None:
    case = _case("F01")
    _map(case["inputs"]).update(
        monthly_limit_cents=10000,
        posted_cents=2000,
        pending_cents=3000,
        plan_cap_cents=10000,
        budget_period="2026-07-01",
        spending_period="2026-07-01",
        now="2026-07-10T12:00:00Z",
        spending_refreshed_at="2026-07-08T11:00:00Z",
    )
    _map(case["expected"]).update(
        monthly_limit_cents=10000,
        posted_cents=2000,
        pending_cents=3000,
        remaining_cents=8000,
        available_cents=10000,
        stale=True,
    )
    observation = _observation(case)
    budget = _map(_final(observation)["budget"])
    assert budget["available_cents"] == 10000
    assert budget["pending_cents"] == 3000
    assert budget["stale"] is True
    score = score_plan(case, observation)
    assert score["status"] == "passed", score
    budget["available_cents"] = 8000
    assert _checks(score_plan(case, observation))["budget_arithmetic"] is False
    budget["available_cents"] = 10000
    budget["stale"] = False
    assert _checks(score_plan(case, observation))["budget_stale"] is False


@pytest.mark.parametrize("field", ("available_cents", "pending_cents", "stale"))
def test_budget_values_compare_to_frozen_expectations(field: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    expected = _map(case["expected"])
    expected[field] = _map(_final(observation)["budget"])[field]
    _map(_final(observation)["budget"])[field] = "wrong"
    score = score_plan(case, observation)
    assert _checks(score)[f"expected_budget_{field}"] is False


def test_over_budget_plan_cannot_claim_acceptance() -> None:
    case = _case("A01")
    observation = _observation(case)
    final = _final(observation)
    final["status"] = "planned"
    _map(final["plan"])["accepted"] = True
    score = score_plan(case, observation)
    assert _checks(score)["expected_accepted"] is False
    assert _checks(score)["integrity_acceptance"] is False
    assert _checks(score)["integrity_budget_cap"] is False


def test_final_plan_missing_cannot_pass() -> None:
    case = _case("F01")
    observation = _observation(case)
    _map(_list(observation["turns"])[-1])["result"] = {
        "status": "clarification",
        "answer": "Which recipe?",
        "request": None,
        "plan": None,
        "budget": None,
    }
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["final_plan_present"] is False


@pytest.mark.parametrize("case_id", ("X02", "A04"))
def test_no_plan_outcomes_are_not_applicable(case_id: str) -> None:
    case = _case(case_id)
    observation: dict[str, object] = {
        "case_id": case_id,
        "condition": "tool_enabled",
        "status": "completed",
        "turns": [
            {
                "status": "completed",
                "result": {
                    "status": "clarification",
                    "answer": "Please clarify the request.",
                    "request": None,
                    "plan": None,
                    "budget": None,
                },
            }
            for _ in _list(case["messages"])
        ],
    }
    score = score_plan(case, observation)
    assert score["status"] == "not_applicable"
    assert "score_outcome" in str(score["reason"])
    observation["status"] = "partial"
    assert score_plan(case, observation)["status"] == "failed"


def test_unexpected_plan_cannot_be_not_applicable() -> None:
    case = _case("A04")
    observation = _observation(case)
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["no_unexpected_plan"] is False


@pytest.mark.parametrize("key", ("inputs", "expected", "messages"))
def test_missing_scenario_context_is_unassessed(key: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    case.pop(key)
    score = score_plan(case, observation)
    assert score["status"] == "unassessed"
    assert score["reason"]


def test_missing_price_scenario_requires_a_plan() -> None:
    case = _case("X01")
    observation = _observation(case)
    _map(_list(observation["turns"])[-1])["result"] = {
        "status": "clarification",
        "answer": "A sample price is missing.",
        "request": None,
        "plan": None,
        "budget": None,
    }
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["final_plan_present"] is False


@pytest.mark.parametrize("key", ("posted_cents", "pending_cents"))
def test_unknown_spending_is_not_zero(key: str) -> None:
    case = _case("F01")
    observation = _observation(case)
    _map(case["inputs"])[key] = None
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["budget_inputs"] is False


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("monthly_limit_cents", True),
        ("monthly_limit_cents", -1),
        ("plan_cap_cents", True),
        ("plan_cap_cents", -1),
        ("now", "invalid"),
        ("spending_refreshed_at", "invalid"),
        ("spending_period", "invalid"),
    ),
)
def test_invalid_budget_facts_fail_without_raising(key: str, value: object) -> None:
    case = _case("F01")
    observation = _observation(case)
    _map(case["inputs"])[key] = value
    score = score_plan(case, observation)
    assert score["status"] == "failed"
    assert _checks(score)["budget_inputs"] is False


def test_inputs_are_immutable_on_success_and_failure() -> None:
    case = _case("F01")
    observation = _observation(case)
    for bad in (False, True):
        if bad:
            _map(_final(observation)["request"])["pantry_ingredients"] = ["wrong"]
        original_case, original_observation = deepcopy(case), deepcopy(observation)
        score_plan(case, observation)
        assert case == original_case
        assert observation == original_observation
