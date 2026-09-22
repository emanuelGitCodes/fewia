from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

from app.evaluation_reference import observe_reference_case

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
SUPPORTED = ("F01", "F02", "F05", "X04", "A01")
SECRET_MARKER = "FIXTURE_SECRET_MARKER"
COMPLETED_KEYS = {
    "case_id",
    "condition",
    "status",
    "request",
    "plan",
    "budget",
    "catalog_version",
    "metrics_status",
    "scope_note",
}
FAKE_FIELDS = (
    "evidence_id",
    "evidence_revision_id",
    "model_turns",
    "planner_revisions",
    "tokens",
    "input_tokens",
    "output_tokens",
    "latency",
    "usage",
    "model_quality",
    "model_quality_score",
    "evidence_class",
    "elapsed_seconds",
)


def _load_case(case_id: str) -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == case_id:
            return copy.deepcopy(row)
    raise AssertionError(f"missing case {case_id}")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def _plan(obs: dict[str, object]) -> dict[str, object]:
    return _mapping(obs["plan"], "plan")


def _request(obs: dict[str, object]) -> dict[str, object]:
    return _mapping(obs["request"], "request")


def _assert_no_fake(obs: dict[str, object]) -> None:
    blob = _blob(obs)
    for field in FAKE_FIELDS:
        assert field not in obs
        assert f'"{field}"' not in blob


def test_all_five_correct_totals_and_acceptance() -> None:
    for case_id in SUPPORTED:
        case = _load_case(case_id)
        obs = observe_reference_case(case)
        gold = _mapping(case["expected"], "expected")
        plan = _plan(obs)
        assert obs["case_id"] == case_id
        assert obs["condition"] == "deterministic_structured_input"
        assert obs["status"] == "completed"
        assert obs["metrics_status"] == "unassessed"
        assert obs["catalog_version"] == "sample-prices-v1"
        assert set(obs) == COMPLETED_KEYS
        assert plan["total_cents"] == gold["total_cents"]
        assert plan["accepted"] == gold["accepted"]
        _assert_no_fake(obs)


def test_f05_final_four_servings() -> None:
    obs = observe_reference_case(_load_case("F05"))
    request = _request(obs)
    meals = request["meals"]
    assert meals == [{"recipe_id": "chicken_tacos", "servings": 4}]
    plan = _plan(obs)
    assert plan["accepted"] is True
    assert plan["total_cents"] == 2373


def test_a01_cap_one_rejected_3471() -> None:
    obs = observe_reference_case(_load_case("A01"))
    request = _request(obs)
    plan = _plan(obs)
    assert request["plan_cap_cents"] == 1
    assert plan["accepted"] is False
    assert plan["total_cents"] == 3471


def test_gold_mutation_unchanged_reference() -> None:
    case = _load_case("F01")
    first = observe_reference_case(case)
    gold = _mapping(case["expected"], "expected")
    gold["total_cents"] = 1
    gold["accepted"] = False
    second = observe_reference_case(case)
    assert first == second
    assert _plan(second)["total_cents"] == 1574
    assert _plan(second)["accepted"] is True


def test_input_total_cents_ignored() -> None:
    case = _load_case("F01")
    inputs = _mapping(case["inputs"], "inputs")
    inputs["total_cents"] = 1
    obs = observe_reference_case(case)
    request = _request(obs)
    assert "total_cents" not in request
    assert _plan(obs)["total_cents"] == 1574


def test_read_only_input() -> None:
    case = _load_case("F01")
    before = copy.deepcopy(case)
    observe_reference_case(case)
    assert case == before


def test_repeated_determinism() -> None:
    case = _load_case("X04")
    first = observe_reference_case(case)
    second = observe_reference_case(copy.deepcopy(case))
    assert first == second
    assert _plan(first)["total_cents"] == 3471
    assert _request(first)["plan_cap_cents"] == 1


def test_deepcopy_raises_static_failed_no_marker() -> None:
    marker = "DEEPCOPY_RUNTIME_MARKER"

    class Boom:
        def __deepcopy__(self, memo: object) -> object:
            raise RuntimeError(marker)

    case = _load_case("F01")
    inputs = _mapping(case["inputs"], "inputs")
    inputs["meals"] = Boom()
    obs = observe_reference_case(case)
    blob = _blob(obs)
    assert obs["status"] == "failed"
    assert obs["reason"] == "inputs are invalid"
    assert marker not in blob
    assert "Traceback" not in blob
    assert "RuntimeError" not in blob
    _assert_no_fake(obs)


def test_malformed_recipe_diet_cap_clock_static_no_marker() -> None:
    rows: list[dict[str, object]] = []
    recipe_case = _load_case("F01")
    recipe_inputs = _mapping(recipe_case["inputs"], "inputs")
    meals = recipe_inputs["meals"]
    assert isinstance(meals, list)
    meal = meals[0]
    assert isinstance(meal, dict)
    meal["recipe_id"] = "salmon_tacos"
    rows.append(observe_reference_case(recipe_case))
    diet_case = _load_case("F01")
    diet_inputs = _mapping(diet_case["inputs"], "inputs")
    diet_inputs["diet"] = "carnivore"
    rows.append(observe_reference_case(diet_case))
    cap_case = _load_case("A01")
    cap_inputs = _mapping(cap_case["inputs"], "inputs")
    cap_inputs["plan_cap_cents"] = "1"
    rows.append(observe_reference_case(cap_case))
    clock_case = _load_case("F02")
    clock_inputs = _mapping(clock_case["inputs"], "inputs")
    clock_inputs["now"] = "not-a-clock"
    rows.append(observe_reference_case(clock_case))
    for obs in rows:
        blob = _blob(obs)
        assert obs["status"] == "failed"
        assert obs["reason"] == "inputs are invalid"
        assert obs["metrics_status"] == "unassessed"
        assert SECRET_MARKER not in blob
        assert "Traceback" not in blob
        assert "TypeError" not in blob
        assert "ValidationError" not in blob
        assert "Exception" not in blob
        _assert_no_fake(obs)


def test_unsupported_ids_unassessed_without_id_echo() -> None:
    for case_id in ("M01", "F03", "P04", "ZZ99"):
        if case_id == "ZZ99":
            case: dict[str, object] = {"id": case_id, "inputs": {"user_id": 1}}
        else:
            case = _load_case(case_id)
        obs = observe_reference_case(case)
        blob = _blob(obs)
        assert obs["case_id"] == "invalid_case"
        assert obs["status"] == "unassessed"
        assert obs["metrics_status"] == "unassessed"
        assert case_id not in blob
        assert "reason" not in obs
        _assert_no_fake(obs)


def test_no_fake_model_usage_or_evidence_fields() -> None:
    for case_id in SUPPORTED:
        obs = observe_reference_case(_load_case(case_id))
        _assert_no_fake(obs)
        assert "turns" not in obs
        assert "prompt" not in obs
        assert "messages" not in obs
        assert obs["metrics_status"] == "unassessed"
