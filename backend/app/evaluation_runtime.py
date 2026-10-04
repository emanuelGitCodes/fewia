from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, cast

from app.agent.provider import LLMProvider
from app.evaluation_matrix import EvaluationSlot
from app.evaluation_summary_check_records import validate_checks


@dataclass(frozen=True)
class EvaluationRuntime:
    provider_factory: Callable[[], LLMProvider] = field(repr=False)
    model_id: str
    evidence_class: Literal["deterministic_fake_provider", "real_bedrock"]
    database_url: str | None = field(default=None, repr=False)
    endpoint: str | None = field(default=None, repr=False)


def fixture_result(
    slot: EvaluationSlot, report: dict[str, object]
) -> dict[str, object]:
    checks: dict[str, bool] = {}
    paths: list[str] = []
    evidence = "unknown"
    execution = "failed"
    status = "failed"
    reason: str | None = "invalid_fixture_report"
    try:
        if type(report) is not dict or any(type(key) is not str for key in report):
            raise ValueError
        reported_status = report.get("status")
        if "status" in report and (
            type(reported_status) is not str
            or reported_status not in ("passed", "scored", "failed", "unassessed")
        ):
            raise ValueError
        validated = validate_checks(report.get("checks"))
        reported_paths = report.get("evidence_paths", [])
        if type(reported_paths) is not list or any(
            type(path) is not str for path in reported_paths
        ):
            raise ValueError
        checks = validated
        paths = list(cast(list[str], reported_paths))
        label = report.get("evidence_class")
        if type(label) is str and label in (
            "deterministic_fake_provider",
            "real_bedrock",
            "local_postgresql",
        ):
            evidence = label
        execution = "completed"
        reason = None
        if reported_status == "failed":
            execution = status = "failed"
            reason = "fixture_failed"
        elif reported_status == "unassessed":
            execution = status = "unassessed"
            reason = "fixture_unassessed"
        elif not checks:
            status = "unassessed"
            reason = "fixture_checks_missing"
        elif all(checks.values()):
            status = "passed"
        else:
            status = "failed"
            reason = "fixture_checks_failed"
    except ValueError:
        pass
    observation: dict[str, object] = {
        "case_id": slot.case_id,
        "condition": slot.condition,
        "status": execution,
        "model_id": None,
        "evidence_class": evidence,
        "evidence_paths": paths,
        "turns": [],
        "model_quality_applicable": False,
    }
    fixture: dict[str, object] = {
        "status": status,
        "scope": "fixture_guard",
        "checks": checks,
    }
    if reason is not None:
        observation["reason_code"] = reason
        fixture["reason_code"] = reason
    return {
        "observation": observation,
        "assessments": {"fixture": fixture},
        "report": report,
    }
