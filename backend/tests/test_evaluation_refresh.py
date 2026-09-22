from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.domain.budget import StaleSpendingError
from app.evaluation_budget_inputs import fixture_budget
from app.evaluation_refresh import (
    FakeUnavailableSyncProvider,
    evaluate_refresh_case,
)
from app.plaid_models import PlaidItem
from app.providers.plaid import PlaidUnavailable
from app.providers.plaid_contract import SyncPage

CORPUS_PATH = Path(__file__).parent / "evaluation" / "scenarios.json"
DRIVER_PATH = Path(__file__).resolve().parents[1] / "app" / "evaluation_refresh.py"
SECRET_MARKER = "FIXTURE_SECRET_MARKER"
UNASSESSED_MARKERS = (
    "tool_selection",
    "model_quality",
    "answer_claims",
    "hidden_reasoning",
    "live_providers",
    "local_postgresql",
    "plaid_sandbox",
    "real_bedrock",
    "deployed_aws",
    "plan_acceptance",
)


def _p01() -> dict[str, object]:
    payload: object = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    rows = payload["scenarios"]
    assert isinstance(rows, list)
    for item in rows:
        assert isinstance(item, dict)
        row = cast(dict[str, object], item)
        if row.get("id") == "P01":
            return row
    raise AssertionError("P01 missing")


def _mapping(value: object, name: str) -> dict[str, object]:
    assert isinstance(value, dict), name
    return cast(dict[str, object], value)


def _blob(value: object) -> str:
    return json.dumps(value, default=str)


def test_corpus_p01_refresh_failure_matches_gold() -> None:
    report = evaluate_refresh_case(_p01())
    assert report["case_id"] == "P01"
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert report["storage"] == "sqlite_in_memory"
    assert report["evidence_target"] == "plaid_sandbox"
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert checks == {
        "accepted": True,
        "outcome": True,
        "sync_failed": True,
        "cursor_unchanged": True,
        "last_synced_unchanged": True,
        "ledger_unchanged": True,
        "provider_calls": True,
        "database_freshness_preserved": True,
    }
    assert observed["accepted"] is False
    assert observed["outcome"] == "refresh_required"
    assert observed["budget_path"] == "stale_reject"
    assert observed["provider_calls"] == 1
    assert observed["sync_failed"] is True
    assert observed["cursor_unchanged"] is True
    assert observed["last_synced_unchanged"] is True
    assert observed["ledger_unchanged"] is True
    assert observed["database_freshness_preserved"] is True
    assert observed["storage"] == "sqlite_in_memory"
    assert observed["evidence_class"] == "deterministic_fake_provider"
    assert "fresh_claim_forbidden" not in checks
    assert "answer" not in observed
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    for marker in UNASSESSED_MARKERS:
        assert marker in unassessed
    assert "success_score" not in report
    assert "pass_rate" not in report
    prompt = _p01()["prompt"]
    assert isinstance(prompt, str)
    assert prompt not in _blob(report)


def test_p01_stale_uncapped_budget_raises() -> None:
    case = _p01()
    with pytest.raises(StaleSpendingError):
        fixture_budget(_mapping(case["inputs"], "inputs"))
    observed = _mapping(evaluate_refresh_case(case)["observed"], "observed")
    assert observed["outcome"] == "refresh_required"
    assert observed["budget_path"] == "stale_reject"
    assert observed["accepted"] is False


def test_mutation_of_allowed_outcomes_flips_check() -> None:
    case = copy.deepcopy(_p01())
    expected = _mapping(case["expected"], "expected")
    expected["allowed_outcomes"] = ["accept_plan"]
    expected["accepted"] = True
    case["expected"] = expected
    checks = _mapping(evaluate_refresh_case(case)["checks"], "checks")
    assert checks["outcome"] is False
    assert checks["accepted"] is False


def test_gold_is_not_executed_or_copied() -> None:
    case = copy.deepcopy(_p01())
    original = copy.deepcopy(case)
    expected = _mapping(case["expected"], "expected")
    expected["domain_calls"] = [{"name": SECRET_MARKER, "token": "access_token"}]
    expected["posted_cents"] = 99999
    case["expected"] = expected
    report = evaluate_refresh_case(case)
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert all(value is True for value in checks.values())
    assert observed["ledger_unchanged"] is True
    blob = _blob(report)
    assert SECRET_MARKER not in blob
    assert "access_token" not in blob
    assert case["inputs"] == original["inputs"]


def test_case_inputs_and_gold_are_readonly() -> None:
    case = _p01()
    before = copy.deepcopy(case)
    evaluate_refresh_case(case)
    assert case == before


def test_unknown_input_marker_is_static_failure_without_leak() -> None:
    case = copy.deepcopy(_p01())
    marker = f"{SECRET_MARKER}-refresh-input"
    inputs = dict(_mapping(case["inputs"], "inputs"))
    inputs["now"] = marker
    inputs["spending_refreshed_at"] = marker
    inputs["monthly_limit_cents"] = marker
    case["inputs"] = inputs
    report = evaluate_refresh_case(case)
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


def test_repeated_runs_are_isolated() -> None:
    first = evaluate_refresh_case(_p01())
    second = evaluate_refresh_case(_p01())
    other = copy.deepcopy(_p01())
    inputs = dict(_mapping(other["inputs"], "inputs"))
    inputs["posted_cents"] = 12000
    inputs["pending_cents"] = 4000
    other["inputs"] = inputs
    third = evaluate_refresh_case(other)
    for report in (first, second, third):
        checks = _mapping(report["checks"], "checks")
        assert all(value is True for value in checks.values())
        observed = _mapping(report["observed"], "observed")
        assert observed["outcome"] == "refresh_required"
        assert observed["ledger_unchanged"] is True
        assert observed["sync_failed"] is True


def test_monkeypatch_advancing_cursor_fails_freshness_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _advance(
        factory: sessionmaker[Session],
        item_id: str,
        provider: object,
        **kwargs: object,
    ) -> int:
        del kwargs
        with factory.begin() as session:
            item = session.get(PlaidItem, item_id)
            assert item is not None
            item.cursor = "advanced-cursor"
            item.last_synced_at = datetime(2026, 9, 6, 16, 0, tzinfo=UTC)
        raise PlaidUnavailable()

    monkeypatch.setattr("app.evaluation_refresh.sync_item", _advance)
    report = evaluate_refresh_case(_p01())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["cursor_unchanged"] is False
    assert observed["last_synced_unchanged"] is False
    assert observed["database_freshness_preserved"] is False
    assert checks["cursor_unchanged"] is False
    assert checks["last_synced_unchanged"] is False
    assert checks["database_freshness_preserved"] is False


def test_unexpected_sync_success_fails_unchanged_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _ok(
        self: FakeUnavailableSyncProvider,
        credential_ref: str,
        cursor: str | None,
    ) -> SyncPage:
        del credential_ref, cursor
        self.calls += 1
        return SyncPage((), (), (), "advanced-cursor", False)

    monkeypatch.setattr(FakeUnavailableSyncProvider, "sync_page", _ok)
    report = evaluate_refresh_case(_p01())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["provider_calls"] == 1
    assert observed["sync_failed"] is False
    assert observed["cursor_unchanged"] is False
    assert observed["last_synced_unchanged"] is False
    assert observed["accepted"] is False
    assert observed["outcome"] == "budget_ready"
    assert observed["budget_path"] == "accept_budget"
    assert checks["sync_failed"] is False
    assert checks["cursor_unchanged"] is False
    assert checks["database_freshness_preserved"] is False
    assert checks["outcome"] is False


def test_unexpected_sync_success_without_database_changes_fails_sync_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _ok(
        factory: sessionmaker[Session],
        item_id: str,
        provider: object,
        **kwargs: object,
    ) -> int:
        del factory, item_id, kwargs
        if isinstance(provider, FakeUnavailableSyncProvider):
            provider.calls += 1
        return 0

    monkeypatch.setattr("app.evaluation_refresh.sync_item", _ok)
    report = evaluate_refresh_case(_p01())
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["sync_failed"] is False
    assert observed["cursor_unchanged"] is True
    assert observed["last_synced_unchanged"] is True
    assert observed["database_freshness_preserved"] is True
    assert observed["provider_calls"] == 1
    assert observed["outcome"] == "refresh_required"
    assert checks["sync_failed"] is False
    assert checks["cursor_unchanged"] is True
    assert checks["database_freshness_preserved"] is True
    assert checks["outcome"] is True


def test_temporary_cap_is_not_plan_acceptance() -> None:
    case = copy.deepcopy(_p01())
    inputs = dict(_mapping(case["inputs"], "inputs"))
    inputs["plan_cap_cents"] = 2000
    case["inputs"] = inputs
    report = evaluate_refresh_case(case)
    observed = _mapping(report["observed"], "observed")
    checks = _mapping(report["checks"], "checks")
    unassessed = report["unassessed"]
    assert isinstance(unassessed, list)
    assert observed["accepted"] is False
    assert observed["outcome"] == "temporary_cap_accepted"
    assert observed["budget_path"] == "stale_cap_accept"
    assert checks["outcome"] is False
    assert "plan_acceptance" in unassessed
    assert "answer_claims" in unassessed


def test_fresh_snapshot_budget_ready_is_not_plan_acceptance() -> None:
    case = copy.deepcopy(_p01())
    inputs = dict(_mapping(case["inputs"], "inputs"))
    inputs["spending_refreshed_at"] = "2026-09-06T15:00:00Z"
    case["inputs"] = inputs
    report = evaluate_refresh_case(case)
    checks = _mapping(report["checks"], "checks")
    observed = _mapping(report["observed"], "observed")
    assert observed["accepted"] is False
    assert observed["outcome"] == "budget_ready"
    assert observed["budget_path"] == "accept_budget"
    assert checks["outcome"] is False
    assert checks["accepted"] is True


def test_gold_evidence_target_is_allowlisted() -> None:
    case = copy.deepcopy(_p01())
    expected = _mapping(case["expected"], "expected")
    expected["evidence_class"] = SECRET_MARKER
    expected["path_classes"] = [SECRET_MARKER]
    case["expected"] = expected
    report = evaluate_refresh_case(case)
    blob = _blob(report)
    assert "evidence_target" not in report
    assert SECRET_MARKER not in blob


def test_non_p01_case_id_is_invalid_without_leak() -> None:
    case = copy.deepcopy(_p01())
    marker = f"{SECRET_MARKER}-case-id"
    case["id"] = marker
    report = evaluate_refresh_case(case)
    blob = _blob(report)
    assert report["case_id"] == "invalid_case"
    assert marker not in blob
    assert SECRET_MARKER not in blob


def test_driver_stays_on_fake_sqlite_without_credentials() -> None:
    text = DRIVER_PATH.read_text(encoding="utf-8")
    assert text.count("\n") + 1 <= 150
    assert "PlaidUnavailable" in text
    for forbidden in (
        "PlaidSandboxProvider",
        "boto3",
        "httpx",
        "SessionLocal",
        "create_app_engine",
        "os.environ",
        "sandbox.plaid.com",
        "from app.config",
    ):
        assert forbidden not in text
    report = evaluate_refresh_case(_p01())
    assert report["evidence_class"] != "plaid_sandbox"
    assert report["evidence_class"] != "local_postgresql"
    assert report["storage"] == "sqlite_in_memory"
