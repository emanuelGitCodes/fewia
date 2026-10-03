import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app import evaluation_refresh
from app.domain.budget import STALE_SPENDING_ERROR, STALE_SPENDING_WARNING
from app.evaluation_refresh_fixture import UNAVAILABLE_SENTINEL, RefreshFixture
from app.plaid_models import PlaidTransaction
from app.providers.plaid import PlaidUnavailable
from app.services.plaid_sync import SyncProvider, sync_item


def _case(*, nonzero: bool = True) -> dict[str, object]:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    data = cast(dict[str, object], json.loads(path.read_text()))
    cases = cast(list[dict[str, object]], data["scenarios"])
    case = next(case for case in cases if case["id"] == "P01")
    inputs = cast(dict[str, object], case["inputs"])
    if nonzero:
        inputs.update(
            posted_cents=3700, pending_cents=825, cursor="synthetic-prior-cursor"
        )
    return case


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def test_released_p01_scenario() -> None:
    report = evaluation_refresh.evaluate_refresh_case(_case(nonzero=False))
    assert report["case_id"] == "P01"
    assert report["status"] == "passed"
    assert _map(report["observed"])["outcome"] == "refresh_required"


def test_failed_refresh_preserves_cursor_time_and_spending() -> None:
    report = evaluation_refresh.evaluate_refresh_case(_case())
    observed = _map(report["observed"])
    before = _map(observed["before"])
    after = _map(observed["after"])
    assert report["status"] == "passed"
    assert before == after
    assert after == {
        "cursor": "synthetic-prior-cursor",
        "last_synced_at": "2026-09-04T16:00:00+00:00",
        "posted_cents": 3700,
        "pending_cents": 825,
        "refreshed_at": "2026-09-04T16:00:00+00:00",
    }
    assert observed["sync_failed"] is True
    assert observed["provider_calls"] == 1
    assert report["evidence_class"] == "deterministic_fake_provider"
    assert report["evidence_paths"] == ["deterministic_fake_provider", "local_sqlite"]
    assert report["model_quality_applicable"] is False


def test_stale_uncapped_budget_requires_refresh() -> None:
    report = evaluation_refresh.evaluate_refresh_case(_case())
    observed = _map(report["observed"])
    assert report["status"] == "passed"
    assert observed["outcome"] == "refresh_required"
    assert observed["budget_path"] == "stale_reject"
    assert observed["budget_accepted"] is False
    assert observed["accepted"] is False
    assert observed["available_cents"] is None
    assert observed["stale"] is True
    assert observed["warnings"] == [STALE_SPENDING_ERROR]


@pytest.mark.parametrize("cap", [0, 1900, 12000])
def test_explicit_cap_keeps_stale_warning(cap: int) -> None:
    case = _case()
    _map(case["inputs"])["plan_cap_cents"] = cap
    _map(case["expected"])["allowed_outcomes"] = ["temporary_cap_accepted"]
    report = evaluation_refresh.evaluate_refresh_case(case)
    observed = _map(report["observed"])
    assert report["status"] == "passed"
    assert observed["outcome"] == "temporary_cap_accepted"
    assert observed["budget_accepted"] is True
    assert observed["available_cents"] == cap
    assert observed["stale"] is True
    assert observed["warnings"] == [STALE_SPENDING_WARNING]
    assert observed["before"] == observed["after"]


def test_expected_poison_cannot_change_execution() -> None:
    case = _case()
    baseline = evaluation_refresh.evaluate_refresh_case(case)
    case["expected"] = {
        "accepted": True,
        "allowed_outcomes": ["gold-only-success"],
        "provider_calls": 0,
        "posted_cents": 0,
        "fixture_behavior": {"kind": "success"},
        "evidence_class": "plaid_sandbox",
    }
    poisoned = evaluation_refresh.evaluate_refresh_case(case)
    assert poisoned["observed"] == baseline["observed"]
    assert poisoned["evidence_paths"] == baseline["evidence_paths"]
    assert poisoned["status"] == "failed"
    assert _map(poisoned["checks"])["accepted"] is False
    assert _map(poisoned["checks"])["outcome"] is False


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("id", "P02"),
        ("fixture_behavior", {"kind": "other"}),
        ("fixture_behavior", []),
        ("inputs", []),
    ],
)
def test_wrong_case_does_not_execute(
    monkeypatch: pytest.MonkeyPatch, key: str, value: object
) -> None:
    def forbidden(ctx: RefreshFixture) -> dict[str, object]:
        pytest.fail("Wrong cases MUST NOT execute the driver.")

    monkeypatch.setattr(evaluation_refresh, "_run", forbidden)
    case = _case()
    case[key] = value
    report = evaluation_refresh.evaluate_refresh_case(case)
    assert report["status"] == "failed"
    assert report["observed"] == {"outcome": "invalid_input"}


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("posted_cents", True),
        ("pending_cents", "825"),
        ("monthly_limit_cents", -1),
        ("plan_cap_cents", 1.5),
        ("user_id", False),
        ("now", "2026-09-06T16:00:00"),
        ("budget_period", "2026-09-02"),
        ("spending_refreshed_at", None),
        ("cursor", 42),
    ],
)
def test_malformed_input_fails_closed(key: str, value: object) -> None:
    case = _case()
    _map(case["inputs"])[key] = value
    report = evaluation_refresh.evaluate_refresh_case(case)
    assert report["status"] == "failed"
    assert report["observed"] == {"outcome": "invalid_input"}


@pytest.mark.parametrize("invalid", [None, [], True, "P01"])
def test_malformed_case_type_fails_closed(invalid: object) -> None:
    report = evaluation_refresh.evaluate_refresh_case(cast(dict[str, object], invalid))
    assert report["case_id"] == "invalid_case"
    assert report["status"] == "failed"


@pytest.mark.parametrize("expected", [None, [], {"accepted": 0}])
def test_malformed_expected_fails_after_observation(expected: object) -> None:
    case = _case()
    case["expected"] = expected
    report = evaluation_refresh.evaluate_refresh_case(case)
    assert report["status"] == "failed"
    assert _map(report["observed"])["provider_calls"] == 1


def test_provider_exception_sentinel_is_redacted(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    report = evaluation_refresh.evaluate_refresh_case(_case())
    assert report["status"] == "passed"
    captured = capsys.readouterr()
    assert UNAVAILABLE_SENTINEL not in json.dumps(report)
    assert UNAVAILABLE_SENTINEL not in caplog.text + captured.out + captured.err


def test_unexpected_exception_text_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "synthetic-unexpected-exception"

    def explode(ctx: RefreshFixture) -> dict[str, object]:
        raise RuntimeError(sentinel)

    monkeypatch.setattr(evaluation_refresh, "_run", explode)
    report = evaluation_refresh.evaluate_refresh_case(_case())
    assert report["status"] == "failed"
    assert report["observed"] == {"outcome": "unexpected_error"}
    assert sentinel not in json.dumps(report)


def test_zeroing_spending_after_failure_fails_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def zero_after_failure(
        factory: sessionmaker[Session],
        item_id: str,
        provider: SyncProvider,
        *,
        user_id: int,
        now: Callable[[], datetime],
    ) -> int:
        try:
            return sync_item(factory, item_id, provider, user_id=user_id, now=now)
        except PlaidUnavailable:
            with factory.begin() as session:
                session.execute(
                    delete(PlaidTransaction).where(PlaidTransaction.item_id == item_id)
                )
            raise

    monkeypatch.setattr(evaluation_refresh, "sync_item", zero_after_failure)
    report = evaluation_refresh.evaluate_refresh_case(_case())
    observed = _map(report["observed"])
    assert report["status"] == "failed"
    assert _map(report["checks"])["ledger_unchanged"] is False
    assert _map(observed["before"])["posted_cents"] == 3700
    assert _map(observed["after"])["posted_cents"] == 0
    assert _map(observed["after"])["pending_cents"] == 0
    assert observed["provider_calls"] == 1
