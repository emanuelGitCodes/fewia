from typing import cast

from app.domain.budget import (
    STALE_SPENDING_ERROR,
    STALE_SPENDING_WARNING,
    SpendingSnapshot,
    StaleSpendingError,
    calculate_budget,
)
from app.evaluation_refresh_fixture import (
    FakeUnavailableSyncProvider,
    RefreshFixture,
    fixture,
)
from app.providers.plaid import PlaidUnavailable
from app.services.ledger_budget import load_spending
from app.services.plaid_sync import sync_item

EVIDENCE_CLASS = "deterministic_fake_provider"
EVIDENCE_PATHS = [EVIDENCE_CLASS, "local_sqlite"]


def _snapshot(ctx: RefreshFixture) -> tuple[dict[str, object], SpendingSnapshot]:
    cursor, synced = ctx.read_state()
    with ctx.factory() as session:
        spending = load_spending(session, ctx.user_id, ctx.period)
    return {
        "cursor": cursor,
        "last_synced_at": None if synced is None else synced.isoformat(),
        "posted_cents": spending.posted_cents,
        "pending_cents": spending.pending_cents,
        "refreshed_at": spending.refreshed_at.isoformat(),
    }, spending


def _run(ctx: RefreshFixture) -> dict[str, object]:
    before, _ = _snapshot(ctx)
    provider = FakeUnavailableSyncProvider()
    failed = False
    try:
        sync_item(
            ctx.factory,
            ctx.item_id,
            provider,
            user_id=ctx.user_id,
            now=lambda: ctx.clock,
        )
    except PlaidUnavailable:
        failed = True
    after, spending = _snapshot(ctx)
    observed: dict[str, object] = {
        "before": before,
        "after": after,
        "provider_calls": provider.calls,
        "sync_failed": failed,
        "accepted": False,
        "cursor_unchanged": before["cursor"] == after["cursor"],
        "last_synced_unchanged": before["last_synced_at"] == after["last_synced_at"],
        "ledger_unchanged": all(
            before[key] == after[key]
            for key in ("posted_cents", "pending_cents", "refreshed_at")
        ),
    }
    try:
        result = calculate_budget(
            ctx.limit, spending, now=ctx.clock, plan_cap_cents=ctx.plan_cap
        )
        observed.update(
            outcome="temporary_cap_accepted" if result.stale else "budget_ready",
            budget_path="stale_cap_accept" if result.stale else "accept_budget",
            budget_accepted=True,
            available_cents=result.available_cents,
            stale=result.stale,
            warnings=list(result.warnings),
            budget_safe=(
                result.stale
                and ctx.plan_cap is not None
                and result.available_cents == ctx.plan_cap
                and result.warnings == (STALE_SPENDING_WARNING,)
            ),
        )
    except StaleSpendingError:
        observed.update(
            outcome="refresh_required",
            budget_path="stale_reject",
            budget_accepted=False,
            available_cents=None,
            stale=True,
            warnings=[STALE_SPENDING_ERROR],
            budget_safe=ctx.plan_cap is None,
        )
    return observed


def evaluate_refresh_case(case: dict[str, object]) -> dict[str, object]:
    observed: dict[str, object] = {"outcome": "invalid_input"}
    checks: dict[str, bool] = {"valid_case": False}
    case_id = "invalid_case"
    if type(case) is dict:
        behavior = case.get("fixture_behavior")
        inputs = case.get("inputs")
        valid = (
            case.get("id") == "P01"
            and type(behavior) is dict
            and behavior.get("kind") == "plaid_refresh_failure"
            and type(inputs) is dict
        )
        if valid:
            case_id = "P01"
            try:
                with fixture(cast(dict[str, object], inputs)) as ctx:
                    observed = _run(ctx)
                checks["valid_case"] = True
            except (TypeError, ValueError):
                observed = {"outcome": "invalid_input"}
            except Exception:  # noqa: BLE001
                observed = {"outcome": "unexpected_error"}
        expected = case.get("expected")
        if type(expected) is dict:
            allowed = expected.get("allowed_outcomes")
            checks["outcome"] = type(allowed) is list and any(
                type(item) is str and observed.get("outcome") == item
                for item in allowed
            )
            checks["accepted"] = (
                type(expected.get("accepted")) is bool
                and observed.get("accepted") is expected["accepted"]
            )
        else:
            checks["expected"] = False
    for key in (
        "sync_failed",
        "cursor_unchanged",
        "last_synced_unchanged",
        "ledger_unchanged",
        "budget_safe",
    ):
        checks[key] = observed.get(key) is True
    checks["provider_calls"] = observed.get("provider_calls") == 1
    checks["stale"] = observed.get("stale") is True
    return {
        "case_id": case_id,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "observed": observed,
        "evidence_class": EVIDENCE_CLASS,
        "evidence_paths": list(EVIDENCE_PATHS),
        "model_quality_applicable": False,
    }
