from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from app.evaluation_handoff import (
    FakeUncertainHandoffProvider,
    evaluate_handoff_case,
)
from app.providers.instacart import InstacartUncertain

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
DRIVER_PATH = Path(__file__).resolve().parents[1] / "app" / "evaluation_handoff.py"
SECRET_MARKER = "FIXTURE_SECRET_MARKER"
SUCCESS_URL = "https://www.instacart.com/store/lists/demo"
UNASSESSED_MARKERS = (
    "live_providers",
    "local_postgresql",
    "live_instacart_development",
    "plan_rows",
    "concurrency",
    "model_quality",
    "hidden_reasoning",
)


def _p02() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "P02":
            return row
    raise AssertionError("P02 missing")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def test_baseline_gold_matches() -> None:
    report = evaluate_handoff_case(_p02())
    assert report["case_id"] == "P02"
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert report["storage"] == "sqlite_in_memory"
    assert report["evidence_target"] == "live_instacart_development"
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert checks == {
        "accepted": True,
        "outcome": True,
        "same_intent": True,
        "state_uncertain": True,
        "error_code_uncertain": True,
        "url_absent": True,
        "retry_allowed": True,
        "attempts": True,
        "provider_calls": True,
        "automatic_duplicate": True,
        "total_cents": True,
    }
    assert observed["accepted"] is True
    assert observed["total_cents"] == 1703
    assert observed["outcome"] == "uncertain_handoff"
    assert observed["same_intent"] is True
    assert observed["state_uncertain"] is True
    assert observed["error_code_uncertain"] is True
    assert observed["url_absent"] is True
    assert observed["retry_allowed"] is True
    assert observed["attempts"] == 1
    assert observed["provider_calls"] == 1
    assert observed["automatic_duplicate"] is False
    assert observed["storage"] == "sqlite_in_memory"
    assert observed["evidence_class"] == "deterministic_fake_provider"
    assert "url" not in observed
    assert "id" not in observed
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    for marker in UNASSESSED_MARKERS:
        assert marker in unassessed
    assert "success_score" not in report
    assert "pass_rate" not in report
    prompt = _p02()["prompt"]
    assert isinstance(prompt, str)
    assert prompt not in _blob(report)


def test_gold_mutations_flip_checks() -> None:
    case = copy.deepcopy(_p02())
    expected = _mapping(case["expected"], "expected")
    expected["allowed_outcomes"] = ["accept_plan"]
    expected["accepted"] = False
    expected["total_cents"] = 0
    case["expected"] = expected
    report = evaluate_handoff_case(case)
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["accepted"] is True
    assert observed["total_cents"] == 1703
    assert observed["outcome"] == "uncertain_handoff"
    assert checks["accepted"] is False
    assert checks["total_cents"] is False
    assert checks["outcome"] is False
    assert checks["state_uncertain"] is True
    assert checks["provider_calls"] is True


def test_unexpected_link_success_fails_uncertain_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _ok(
        self: FakeUncertainHandoffProvider,
        payload: dict[str, object],
    ) -> str:
        del payload
        self.calls += 1
        return SUCCESS_URL

    monkeypatch.setattr(FakeUncertainHandoffProvider, "create_link", _ok)
    report = evaluate_handoff_case(_p02())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    blob = _blob(report)
    assert observed["state_uncertain"] is False
    assert observed["error_code_uncertain"] is False
    assert observed["url_absent"] is False
    assert observed["retry_allowed"] is False
    assert observed["provider_calls"] == 1
    assert checks["state_uncertain"] is False
    assert checks["error_code_uncertain"] is False
    assert checks["url_absent"] is False
    assert checks["retry_allowed"] is False
    assert checks["outcome"] is False
    assert SUCCESS_URL not in blob
    assert "url" not in observed


def test_duplicate_call_mutation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _double(
        self: FakeUncertainHandoffProvider,
        payload: dict[str, object],
    ) -> str:
        del payload
        self.calls += 2
        raise InstacartUncertain()

    monkeypatch.setattr(FakeUncertainHandoffProvider, "create_link", _double)
    report = evaluate_handoff_case(_p02())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["provider_calls"] == 2
    assert observed["automatic_duplicate"] is True
    assert observed["state_uncertain"] is True
    assert checks["provider_calls"] is False
    assert checks["automatic_duplicate"] is False
    assert not all(value is True for value in checks.values())


def test_no_consent_or_rejected_budget_never_calls_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []

    def _spy(
        self: FakeUncertainHandoffProvider,
        payload: dict[str, object],
    ) -> str:
        del payload
        seen.append(1)
        self.calls += 1
        raise InstacartUncertain()

    monkeypatch.setattr(FakeUncertainHandoffProvider, "create_link", _spy)
    denied = copy.deepcopy(_p02())
    inputs = dict(_mapping(denied["inputs"], "inputs"))
    inputs["plan_accepted"] = False
    denied["inputs"] = inputs
    denied_report = evaluate_handoff_case(denied)
    denied_observed = _mapping(denied_report["observed"], "observed")
    assert denied_observed["outcome"] == "unexpected_error"
    assert seen == []

    rejected = copy.deepcopy(_p02())
    rejected_inputs = dict(_mapping(rejected["inputs"], "inputs"))
    rejected_inputs["plan_cap_cents"] = 100
    rejected["inputs"] = rejected_inputs
    rejected_report = evaluate_handoff_case(rejected)
    rejected_observed = _mapping(rejected_report["observed"], "observed")
    assert rejected_observed["outcome"] == "unexpected_error"
    assert seen == []
    assert "accepted" not in denied_observed
    assert "accepted" not in rejected_observed


def test_isolated_repeat() -> None:
    first = evaluate_handoff_case(_p02())
    second = evaluate_handoff_case(_p02())
    for report in (first, second):
        checks = _mapping(report["checks"], "checks")
        observed = _mapping(report["observed"], "observed")
        assert all(value is True for value in checks.values())
        assert observed["provider_calls"] == 1
        assert observed["attempts"] == 1
        assert observed["same_intent"] is True
        assert observed["automatic_duplicate"] is False


def test_secret_marker_stays_out_of_metadata() -> None:
    case = copy.deepcopy(_p02())
    marker = f"{SECRET_MARKER}-handoff"
    expected = _mapping(case["expected"], "expected")
    expected["evidence_class"] = marker
    expected["path_classes"] = [marker]
    expected["domain_calls"] = [{"name": marker, "token": "access_token"}]
    case["expected"] = expected
    case["prompt"] = marker
    report = evaluate_handoff_case(case)
    blob = _blob(report)
    assert "evidence_target" not in report
    assert marker not in blob
    assert SECRET_MARKER not in blob
    assert "access_token" not in blob
    prompt = _p02()["prompt"]
    assert isinstance(prompt, str)
    assert prompt not in blob


def test_malformed_inputs_are_static_unexpected_error() -> None:
    case = copy.deepcopy(_p02())
    marker = f"{SECRET_MARKER}-not-a-clock"
    inputs = dict(_mapping(case["inputs"], "inputs"))
    inputs["now"] = marker
    case["inputs"] = inputs
    report = evaluate_handoff_case(case)
    observed = _mapping(report["observed"], "observed")
    checks = _mapping(report["checks"], "checks")
    blob = _blob(report)
    assert observed["outcome"] == "unexpected_error"
    assert "accepted" not in observed
    assert checks["outcome"] is False
    assert checks["accepted"] is False
    assert marker not in blob
    assert SECRET_MARKER not in blob
    assert "Traceback" not in blob


def test_non_p02_case_id_is_invalid_without_leak() -> None:
    case = copy.deepcopy(_p02())
    marker = f"{SECRET_MARKER}-case-id"
    case["id"] = marker
    report = evaluate_handoff_case(case)
    blob = _blob(report)
    assert report["case_id"] == "invalid_case"
    assert marker not in blob
    assert SECRET_MARKER not in blob


def test_case_inputs_and_gold_are_readonly() -> None:
    case = _p02()
    before = copy.deepcopy(case)
    evaluate_handoff_case(case)
    assert case == before


def test_driver_stays_on_fake_sqlite_without_network() -> None:
    text = DRIVER_PATH.read_text(encoding="utf-8")
    assert text.count("\n") + 1 <= 130
    for forbidden in (
        "InstacartDevelopmentProvider",
        "boto3",
        "httpx",
        "SessionLocal",
        "create_app_engine",
        "os.environ",
        "from app.config",
        "connect.dev.instacart",
        "retry=True",
    ):
        assert forbidden not in text
    report = evaluate_handoff_case(_p02())
    assert report["evidence_class"] != "live_instacart_development"
    assert report["evidence_class"] != "local_postgresql"
    assert report["storage"] == "sqlite_in_memory"
