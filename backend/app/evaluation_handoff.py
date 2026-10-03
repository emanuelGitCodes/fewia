from copy import deepcopy
from typing import cast

from app.evaluation_budget_inputs import _parse_clock
from app.evaluation_database import fixture_database
from app.evaluation_plan_inputs import fixture_plan
from app.models import User
from app.providers.instacart import InstacartUncertain
from app.services.handoff_dispatch import dispatch_handoff
from app.services.handoff_intents import HandoffView, prepare_handoff, read_handoff
from app.services.shopping_payload import build_shopping_payload


class FakeUncertainHandoffProvider:
    calls: int = 0

    def create_link(self, payload: dict[str, object]) -> str:
        self.calls += 1
        error = InstacartUncertain()
        error.args = ("SYNTHETIC_HANDOFF_MARKER",)
        raise error


def _validate(case: dict[str, object]) -> str | None:
    if case.get("id") != "P02":
        return "invalid_case"
    if not isinstance(fixture := case.get("fixture_behavior"), dict) or (
        fixture.get("kind") != "instacart_timeout" or fixture.get("provider") != "fake"
    ):
        return "invalid_fixture"
    inputs = case.get("inputs")
    if not isinstance(inputs, dict):
        return "invalid_inputs"
    owner = inputs.get("user_id")
    if type(owner) is not int or owner <= 0:
        return "invalid_owner"
    return None if inputs.get("plan_accepted") is True else "consent_required"


def _snapshot(view: HandoffView, calls: int) -> dict[str, object]:
    return {
        "state": view.state,
        "attempts": view.attempts,
        "provider_calls": calls,
        "url_absent": view.url is None,
        "retry_allowed": view.retry_allowed,
        "error_code": view.error_code,
    }


def _execute(
    inputs: dict[str, object], payload: dict[str, object]
) -> dict[str, object]:
    owner = cast(int, inputs["user_id"])
    clock = _parse_clock(inputs["now"])
    provider = FakeUncertainHandoffProvider()
    with fixture_database() as database:
        with database.factory.begin() as session:
            session.add(User(id=owner, display_name="Evaluation owner"))
        first = prepare_handoff(database.factory, owner, payload, now=clock)
        second = prepare_handoff(database.factory, owner, payload, now=clock)
        views = [first, second]
        stages: dict[str, object] = {"prepared": _snapshot(first, provider.calls)}
        for stage, retry in (
            ("first_dispatch", False),
            ("before_retry", False),
            ("after_retry", True),
            ("stale_retry", True),
        ):
            view = dispatch_handoff(
                database.factory,
                provider,
                owner,
                second.id,
                retry=retry,
                expected_attempt=1 if retry else None,
                now=lambda: clock,
            )
            views.append(view)
            stages[stage] = _snapshot(view, provider.calls)
        uncertain = view.state == "uncertain" and view.retry_allowed
        return {
            **stages,
            "same_intent": all(view.id == first.id for view in views),
            "owner_scoped": (
                read_handoff(database.factory, owner + 1, first.id, now=clock) is None
            ),
            "outcome": "uncertain_handoff" if uncertain else "unexpected_outcome",
        }


def _checks(
    observed: dict[str, object], expected: dict[str, object]
) -> dict[str, bool]:
    checks = {
        key: type(observed.get(key)) is type(expected.get(key))
        and observed.get(key) == expected.get(key)
        for key in ("accepted", "total_cents")
    }
    allowed = expected.get("allowed_outcomes")
    checks["outcome"] = isinstance(allowed, list) and observed["outcome"] in allowed
    checks["same_intent"] = observed.get("same_intent") is True
    checks["owner_scoped"] = observed.get("owner_scoped") is True
    for stage, attempts in (
        ("first_dispatch", 1),
        ("before_retry", 1),
        ("after_retry", 2),
        ("stale_retry", 2),
    ):
        checks[stage] = observed[stage] == {
            "state": "uncertain",
            "attempts": attempts,
            "provider_calls": attempts,
            "url_absent": True,
            "retry_allowed": True,
            "error_code": "instacart_uncertain",
        }
    return checks


def evaluate_handoff_case(case: dict[str, object]) -> dict[str, object]:
    report: dict[str, object] = {
        "case_id": "P02" if case.get("id") == "P02" else "invalid_case",
        "status": "failed",
        "checks": {},
        "observed": {},
        "evidence_class": "deterministic_fake_provider",
        "storage": "sqlite_in_memory",
        "model_quality_applicable": False,
    }
    if (reason := _validate(case)) is not None:
        return {**report, "reason_code": reason}
    inputs = deepcopy(cast(dict[str, object], case["inputs"]))
    try:
        try:
            plan = fixture_plan(inputs)
            payload = build_shopping_payload(plan)
        except (TypeError, ValueError):
            return {**report, "reason_code": "invalid_inputs"}
        observed = _execute(inputs, payload)
    except Exception:  # noqa: BLE001
        return {**report, "reason_code": "execution_failed"}
    observed.update(accepted=plan.accepted, total_cents=plan.total_cents)
    report["observed"] = observed
    expected = case.get("expected")
    if not isinstance(expected, dict):
        return {**report, "status": "unassessed", "reason_code": "invalid_expected"}
    checks = _checks(observed, expected)
    report.update(checks=checks, status="scored" if all(checks.values()) else "failed")
    return report
