"""Check isolated uncertain shopping handoff recovery."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import evaluation_handoff as evaluator
from app.evaluation_database import FixtureDatabase, fixture_database
from app.handoff_models import ShoppingHandoff
from app.models import User
from app.services.handoff_dispatch import HandoffLinkProvider, dispatch_handoff
from app.services.handoff_intents import HandoffNotFound, HandoffView


@pytest.fixture
def case() -> dict[str, object]:
    corpus = json.loads(
        Path(__file__).with_name("evaluation").joinpath("scenarios.json").read_text()
    )
    return cast(
        dict[str, object], next(c for c in corpus["scenarios"] if c["id"] == "P02")
    )


def _map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def test_corpus_recovery_and_evidence(case: dict[str, object]) -> None:
    original = deepcopy(case)
    result = evaluator.evaluate_handoff_case(case)
    assert case == original
    assert result["case_id"] == "P02"
    assert result["status"] == "scored"
    assert all(_map(result["checks"]).values())
    assert result["evidence_class"] == "deterministic_fake_provider"
    assert result["storage"] == "sqlite_in_memory"
    assert result["model_quality_applicable"] is False
    observed = _map(result["observed"])
    assert observed["accepted"] is True
    assert observed["total_cents"] == 1703
    assert observed["first_dispatch"] == observed["before_retry"]
    assert observed["after_retry"] == observed["stale_retry"]
    assert _map(observed["before_retry"])["provider_calls"] == 1
    assert _map(observed["after_retry"])["provider_calls"] == 2
    for stage in ("before_retry", "after_retry", "stale_retry"):
        assert _map(observed[stage])["state"] == "uncertain"
        assert _map(observed[stage])["url_absent"] is True
        assert _map(observed[stage])["retry_allowed"] is True
    assert "SYNTHETIC_HANDOFF_MARKER" not in json.dumps(result)


@pytest.mark.parametrize(
    ("section", "key", "value", "reason"),
    [
        (None, "id", "P01", "invalid_case"),
        ("fixture_behavior", "kind", "other", "invalid_fixture"),
        ("fixture_behavior", "provider", "live", "invalid_fixture"),
        ("inputs", "plan_accepted", False, "consent_required"),
        ("inputs", "plan_accepted", 1, "consent_required"),
        ("inputs", "user_id", True, "invalid_owner"),
        ("inputs", "user_id", 0, "invalid_owner"),
        ("inputs", "user_id", -1, "invalid_owner"),
        ("inputs", "user_id", "1", "invalid_owner"),
        ("inputs", "meals", [], "invalid_inputs"),
        (
            "inputs",
            "meals",
            [{"recipe_id": "unknown", "servings": 2}],
            "invalid_inputs",
        ),
        (
            "inputs",
            "meals",
            [{"recipe_id": "bean_tacos", "servings": 0}],
            "invalid_inputs",
        ),
        ("inputs", "now", "bad", "invalid_inputs"),
        ("inputs", "spending_refreshed_at", "2025-01-01T00:00:00Z", "invalid_inputs"),
        ("inputs", "budget_period", "2026-08-01", "invalid_inputs"),
        ("inputs", "posted_cents", True, "invalid_inputs"),
        (None, "inputs", None, "invalid_inputs"),
        (None, "fixture_behavior", None, "invalid_fixture"),
    ],
)
def test_invalid_cases_do_not_call_provider(
    case: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    section: str | None,
    key: str,
    value: object,
    reason: str,
) -> None:
    target = case if section is None else _map(case[section])
    target[key] = value
    provider = Mock(side_effect=AssertionError("provider MUST NOT start"))
    monkeypatch.setattr(evaluator, "FakeUncertainHandoffProvider", provider)
    result = evaluator.evaluate_handoff_case(case)
    assert result["status"] == "failed"
    assert result["reason_code"] == reason
    assert result["observed"] == {}
    provider.assert_not_called()


def test_missing_consent(case: dict[str, object]) -> None:
    _map(case["inputs"]).pop("plan_accepted")
    assert evaluator.evaluate_handoff_case(case)["reason_code"] == "consent_required"


def test_gold_does_not_drive_execution(
    case: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []
    create_link = evaluator.FakeUncertainHandoffProvider.create_link

    def counted_link(
        provider: evaluator.FakeUncertainHandoffProvider, payload: dict[str, object]
    ) -> str:
        calls.append(deepcopy(payload))
        return create_link(provider, payload)

    monkeypatch.setattr(
        evaluator.FakeUncertainHandoffProvider, "create_link", counted_link
    )
    first = evaluator.evaluate_handoff_case(case)
    case["expected"] = {
        "accepted": False,
        "total_cents": 1,
        "allowed_outcomes": ["succeeded"],
        "automatic_duplicate_forbidden": False,
    }
    second = evaluator.evaluate_handoff_case(case)
    assert first["observed"] == second["observed"]
    assert len(calls) == 4
    assert calls[:2] == calls[2:]
    assert second["status"] == "failed"
    checks = _map(second["checks"])
    assert checks["accepted"] is checks["total_cents"] is checks["outcome"] is False
    assert (
        checks["before_retry"] is checks["after_retry"] is checks["stale_retry"] is True
    )


def test_missing_gold_is_unassessed_after_execution(case: dict[str, object]) -> None:
    case.pop("expected")
    result = evaluator.evaluate_handoff_case(case)
    assert result["status"] == "unassessed"
    assert result["reason_code"] == "invalid_expected"
    assert _map(_map(result["observed"])["stale_retry"])["provider_calls"] == 2


def test_owner_scope_and_dispatch_arguments(
    case: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    _map(case["inputs"])["user_id"] = 17
    arguments: list[tuple[bool, int | None]] = []

    def dispatch(
        factory: sessionmaker[Session],
        provider: HandoffLinkProvider,
        user_id: int,
        handoff_id: str,
        *,
        retry: bool,
        expected_attempt: int | None,
        now: Callable[[], datetime],
    ) -> HandoffView:
        clock = now()
        with factory.begin() as session:
            assert list(session.scalars(select(User.id))) == [17]
            assert list(session.scalars(select(ShoppingHandoff.user_id))) == [17]
        with pytest.raises(HandoffNotFound):
            dispatch_handoff(factory, provider, 18, handoff_id, now=lambda: clock)
        arguments.append((retry, expected_attempt))
        return dispatch_handoff(
            factory,
            provider,
            user_id,
            handoff_id,
            retry=retry,
            expected_attempt=expected_attempt,
            now=lambda: clock,
        )

    monkeypatch.setattr(evaluator, "dispatch_handoff", dispatch)
    assert evaluator.evaluate_handoff_case(case)["status"] == "scored"
    assert arguments == [(False, None), (False, None), (True, 1), (True, 1)]


@pytest.mark.parametrize("operation", ["prepare_handoff", "dispatch_handoff"])
def test_production_errors_close_database_and_redact(
    case: dict[str, object], monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    closed: list[bool] = []

    @contextmanager
    def database() -> Iterator[FixtureDatabase]:
        try:
            with fixture_database() as fixture:
                yield fixture
        finally:
            closed.append(True)

    monkeypatch.setattr(evaluator, "fixture_database", database)
    monkeypatch.setattr(
        evaluator, operation, Mock(side_effect=RuntimeError("PRIVATE_MARKER"))
    )
    result = evaluator.evaluate_handoff_case(case)
    assert result["status"] == "failed"
    assert result["reason_code"] == "execution_failed"
    assert result["observed"] == {}
    assert closed == [True]
    assert "PRIVATE_MARKER" not in json.dumps(result)


def test_failed_plan_arithmetic_blocks_provider(
    case: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = evaluator.fixture_plan(_map(case["inputs"]))
    object.__setattr__(plan, "total_cents", 1)
    monkeypatch.setattr(evaluator, "fixture_plan", Mock(return_value=plan))
    provider = Mock()
    monkeypatch.setattr(evaluator, "FakeUncertainHandoffProvider", provider)
    assert evaluator.evaluate_handoff_case(case)["reason_code"] == "invalid_inputs"
    provider.assert_not_called()


def test_observed_recovery_failure_fails_even_with_changed_gold(
    case: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    execute = evaluator._execute

    def duplicate(
        inputs: dict[str, object], payload: dict[str, object]
    ) -> dict[str, object]:
        observed = execute(inputs, payload)
        _map(observed["before_retry"])["provider_calls"] = 2
        return observed

    _map(case["expected"])["automatic_duplicate_forbidden"] = False
    monkeypatch.setattr(evaluator, "_execute", duplicate)
    result = evaluator.evaluate_handoff_case(case)
    assert result["status"] == "failed"
    assert _map(result["checks"])["before_retry"] is False
