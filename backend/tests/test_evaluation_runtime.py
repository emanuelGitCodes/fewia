from copy import deepcopy
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from app.agent.provider import LLMProvider
from app.evaluation_matrix import EvaluationSlot
from app.evaluation_runtime import EvaluationRuntime, fixture_result


def _slot(driver: str = "budget", case_id: str = "B01") -> EvaluationSlot:
    condition = "deterministic_fixture"
    if driver in ("refresh", "handoff", "protocol", "duplicate"):
        condition = "controlled_fixture"
    return EvaluationSlot(case_id, 2, condition, driver, {})


def _fixture(result: dict[str, object]) -> dict[str, object]:
    assessments = cast(dict[str, object], result["assessments"])
    return cast(dict[str, object], assessments["fixture"])


class _UnusedFactory:
    def __call__(self) -> LLMProvider:
        raise AssertionError("factory MUST remain unused")

    def __repr__(self) -> str:
        raise AssertionError("factory MUST remain private")


def test_runtime_construction_and_repr_keep_private_fields_unused() -> None:
    factory = _UnusedFactory()
    runtime = EvaluationRuntime(
        factory,
        "evaluation-model",
        "real_bedrock",
        "private-database-marker",
        "private-endpoint-marker",
    )
    assert runtime.provider_factory is factory
    assert repr(runtime) == (
        "EvaluationRuntime(model_id='evaluation-model', evidence_class='real_bedrock')"
    )
    defaults = EvaluationRuntime(factory, "fake", "deterministic_fake_provider")
    assert defaults.database_url is None
    assert defaults.endpoint is None


@pytest.mark.parametrize(
    "name",
    ["provider_factory", "model_id", "evidence_class", "database_url", "endpoint"],
)
def test_runtime_is_frozen(name: str) -> None:
    runtime = EvaluationRuntime(_UnusedFactory(), "fake", "deterministic_fake_provider")
    with pytest.raises(FrozenInstanceError):
        setattr(runtime, name, None)


@pytest.mark.parametrize(
    "driver,case_id,extra",
    [
        ("budget", "B01", {"unassessed": ["model_quality"]}),
        ("meals", "M01", {"unassessed": ["model_quality"]}),
        ("followup", "F03", {"unassessed": ["model_quality"]}),
        ("missing", "X01", {"unassessed": ["model_quality"]}),
        ("refresh", "P01", {"status": "passed", "evidence_paths": ["local_sqlite"]}),
        ("handoff", "P02", {"status": "scored", "storage": "sqlite_in_memory"}),
        ("protocol", "P03", {"status": "scored", "controlled_fault": True}),
        ("protocol", "P04", {"status": "scored", "controlled_fault": True}),
        (
            "duplicate",
            "P05",
            {
                "status": "passed",
                "evidence_class": "local_postgresql",
                "evidence_paths": ["local_postgresql", "worker", "floci_sqs"],
            },
        ),
    ],
)
def test_existing_fixture_shapes(
    driver: str, case_id: str, extra: dict[str, object]
) -> None:
    slot = _slot(driver, case_id)
    report: dict[str, object] = {
        "case_id": case_id,
        "checks": {"outcome": True, "B01a.available_cents": True},
        "observed": {"outcome": "fixture_result"},
        "evidence_class": "deterministic_fake_provider",
        "model_quality_applicable": False,
        **extra,
    }
    original = deepcopy(report)
    result = fixture_result(slot, report)
    assert set(result) == {"observation", "assessments", "report"}
    assert result["report"] is report
    assert report == original
    assert result["observation"] == {
        "case_id": case_id,
        "condition": slot.condition,
        "status": "completed",
        "model_id": None,
        "evidence_class": report["evidence_class"],
        "evidence_paths": report.get("evidence_paths", []),
        "turns": [],
        "model_quality_applicable": False,
    }
    fixture = _fixture(result)
    assert fixture == {
        "status": "passed",
        "scope": "fixture_guard",
        "checks": report["checks"],
    }
    assert fixture["checks"] is not report["checks"]
    observation = cast(dict[str, object], result["observation"])
    if "evidence_paths" in report:
        assert observation["evidence_paths"] is not report["evidence_paths"]
    cast(dict[str, bool], fixture["checks"])["outcome"] = False
    cast(list[str], observation["evidence_paths"]).append("copied_path")
    assert report == original


@pytest.mark.parametrize("status", [None, "passed", "scored"])
@pytest.mark.parametrize(
    "checks,assessment,execution,reason",
    [
        ({"guard": True}, "passed", "completed", None),
        ({"guard": False}, "failed", "completed", "fixture_checks_failed"),
        ({}, "unassessed", "completed", "fixture_checks_missing"),
        ({"guard": 1}, "failed", "failed", "invalid_fixture_report"),
        ({"guard": "true"}, "failed", "failed", "invalid_fixture_report"),
    ],
)
def test_guard_derived_status(
    status: str | None,
    checks: dict[str, object],
    assessment: str,
    execution: str,
    reason: str | None,
) -> None:
    report: dict[str, object] = {"checks": checks}
    if status is not None:
        report["status"] = status
    result = fixture_result(_slot(), report)
    fixture = _fixture(result)
    observation = cast(dict[str, object], result["observation"])
    assert fixture["status"] == assessment
    assert observation["status"] == execution
    assert observation.get("reason_code") == reason
    expected_checks = {} if reason == "invalid_fixture_report" else checks
    assert fixture["checks"] == expected_checks


@pytest.mark.parametrize(
    "status,checks",
    [
        ("failed", {"guard": True}),
        ("failed", {"guard": False}),
        ("failed", {}),
        ("unassessed", {}),
        ("unassessed", {"guard": True}),
    ],
)
def test_explicit_failed_and_unassessed_status_is_preserved(
    status: str, checks: dict[str, bool]
) -> None:
    report: dict[str, object] = {
        "status": status,
        "checks": checks,
        "reason": "arbitrary-report-marker",
        "reason_code": "arbitrary-report-marker",
    }
    original = deepcopy(report)
    result = fixture_result(_slot("duplicate", "P05"), report)
    assert _fixture(result)["status"] == status
    observation = cast(dict[str, object], result["observation"])
    assert observation["status"] == status
    assert observation["evidence_class"] == "unknown"
    assert observation["reason_code"] == f"fixture_{status}"
    assert "arbitrary-report-marker" not in repr(observation)
    assert result["report"] is report
    assert report == original


@pytest.mark.parametrize(
    "report",
    [
        None,
        [],
        {},
        {"checks": None},
        {"checks": []},
        {"checks": {1: True}},
        {"checks": {"bad.name": True}},
        {"checks": {"x" * 65: True}},
        {"checks": {"guard": True}, "status": "completed"},
        {"checks": {"guard": True}, "status": None},
        {"checks": {"guard": True}, "status": []},
        {"checks": {"guard": True}, "evidence_paths": "local_postgresql"},
        {"checks": {"guard": True}, "evidence_paths": [1]},
        {"checks": {"guard": True}, 1: "invalid_key"},
    ],
)
def test_malformed_report_boundary_fails_with_static_reason(report: object) -> None:
    original = deepcopy(report)
    result = fixture_result(_slot(), cast(dict[str, object], report))
    fixture = _fixture(result)
    observation = cast(dict[str, object], result["observation"])
    assert fixture["status"] == observation["status"] == "failed"
    assert fixture["checks"] == {}
    assert observation["evidence_class"] == "unknown"
    assert observation["evidence_paths"] == []
    assert observation["reason_code"] == "invalid_fixture_report"
    assert result["report"] is report
    assert report == original


@pytest.mark.parametrize(
    "label,normalized",
    [
        ("deterministic_fake_provider", "deterministic_fake_provider"),
        ("real_bedrock", "real_bedrock"),
        ("local_postgresql", "local_postgresql"),
        ("live_providers", "unknown"),
        ("deployed_aws", "unknown"),
        ("unknown", "unknown"),
        (None, "unknown"),
        (1, "unknown"),
        ([], "unknown"),
    ],
)
def test_evidence_comes_only_from_allowed_report_labels(
    label: object, normalized: str
) -> None:
    slot = _slot()
    slot.case["expected"] = {"evidence_class": "real_bedrock", "guard": False}
    report: dict[str, object] = {
        "checks": {"guard": True},
        "evidence_class": label,
        "reason": "arbitrary-report-marker",
    }
    result = fixture_result(slot, report)
    observation = cast(dict[str, object], result["observation"])
    assert observation["evidence_class"] == normalized
    assert "reason" not in observation
    assert "reason_code" not in observation
    assert _fixture(result)["status"] == "passed"
