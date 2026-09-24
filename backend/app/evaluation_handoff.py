from app.evaluation_budget import EVIDENCE_CLASS, UNASSESSED, _as_map, _typed_equal
from app.evaluation_handoff_fixture import (
    FakeUncertainHandoffProvider,
    HandoffFixture,
    fixture,
)
from app.services.handoff_dispatch import dispatch_handoff
from app.services.handoff_intents import HandoffView, prepare_handoff

STORAGE = "sqlite_in_memory"
TARGET = "live_instacart_development"


def _observe(inputs: dict[str, object]) -> dict[str, object]:
    labeled: dict[str, object] = {"storage": STORAGE, "evidence_class": EVIDENCE_CLASS}
    try:
        with fixture(inputs) as ctx:
            return {**_run(ctx), **labeled}
    except Exception:
        return {"outcome": "unexpected_error", **labeled}


def _outcome(view: HandoffView) -> str:
    if view.state == "uncertain" and view.retry_allowed:
        return "uncertain_handoff"
    if view.retry_allowed:
        return "retry_choice"
    return "unexpected_error"


def _run(ctx: HandoffFixture) -> dict[str, object]:
    provider = FakeUncertainHandoffProvider()
    first = prepare_handoff(ctx.factory, ctx.user_id, ctx.payload, now=ctx.clock)
    second = prepare_handoff(ctx.factory, ctx.user_id, ctx.payload, now=ctx.clock)
    dispatched = dispatch_handoff(
        ctx.factory, provider, ctx.user_id, first.id, now=lambda: ctx.clock
    )
    again = dispatch_handoff(
        ctx.factory, provider, ctx.user_id, second.id, now=lambda: ctx.clock
    )
    same_intent = first.id == second.id == dispatched.id == again.id
    stable = same_intent and dispatched.state == again.state
    stable = stable and dispatched.attempts == again.attempts
    calls = provider.calls
    return {
        "accepted": ctx.plan.accepted,
        "total_cents": ctx.plan.total_cents,
        "outcome": _outcome(again),
        "same_intent": same_intent,
        "state_uncertain": again.state == "uncertain",
        "error_code_uncertain": again.error_code == "instacart_uncertain",
        "url_absent": dispatched.url is None and again.url is None,
        "retry_allowed": (
            dispatched.retry_allowed is True and again.retry_allowed is True
        ),
        "attempts": again.attempts,
        "provider_calls": calls,
        "automatic_duplicate": not (calls == 1 and stable),
    }


def _score(observed: dict[str, object], gold: dict[str, object]) -> dict[str, bool]:
    allowed = gold.get("allowed_outcomes")
    outcome_ok = isinstance(allowed, list) and any(
        _typed_equal(observed.get("outcome"), item) for item in allowed
    )
    checks: dict[str, bool] = {
        "accepted": _typed_equal(observed.get("accepted"), gold.get("accepted")),
        "outcome": bool(outcome_ok),
        "same_intent": observed.get("same_intent") is True,
        "state_uncertain": observed.get("state_uncertain") is True,
        "error_code_uncertain": observed.get("error_code_uncertain") is True,
        "url_absent": observed.get("url_absent") is True,
        "retry_allowed": observed.get("retry_allowed") is True,
        "attempts": observed.get("attempts") == 1,
        "provider_calls": observed.get("provider_calls") == 1,
        "automatic_duplicate": observed.get("automatic_duplicate") is False,
    }
    if "total_cents" in gold:
        checks["total_cents"] = _typed_equal(
            observed.get("total_cents"), gold["total_cents"]
        )
    return checks


def evaluate_handoff_case(case: dict[str, object]) -> dict[str, object]:
    gold = _as_map(case.get("expected"))
    observed = _observe(_as_map(case.get("inputs")))
    report: dict[str, object] = {
        "case_id": "P02" if case.get("id") == "P02" else "invalid_case",
        "checks": _score(observed, gold),
        "observed": observed,
        "unassessed": [*UNASSESSED, "concurrency"],
        "evidence_class": EVIDENCE_CLASS,
        "storage": STORAGE,
    }
    if gold.get("evidence_class") == TARGET:
        report["evidence_target"] = TARGET
    return report
