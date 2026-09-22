from app.domain.budget import StaleSpendingError, calculate_budget
from app.evaluation_budget import EVIDENCE_CLASS, UNASSESSED, _as_map, _typed_equal
from app.evaluation_refresh_fixture import (
    ITEM_ID,
    FakeUnavailableSyncProvider,
    RefreshFixture,
    fixture,
)
from app.providers.plaid import PlaidUnavailable
from app.services.ledger_budget import load_spending
from app.services.plaid_sync import sync_item

STORAGE = "sqlite_in_memory"


def _observe(inputs: dict[str, object]) -> dict[str, object]:
    labeled: dict[str, object] = {"storage": STORAGE, "evidence_class": EVIDENCE_CLASS}
    try:
        with fixture(inputs) as ctx:
            return {**_run(ctx), **labeled}
    except Exception:
        return {"outcome": "unexpected_error", **labeled}


def _run(ctx: RefreshFixture) -> dict[str, object]:
    before = ctx.read_state()
    provider = FakeUnavailableSyncProvider()
    failed = False
    try:
        sync_item(
            ctx.session_factory,
            ITEM_ID,
            provider,
            user_id=ctx.user_id,
            now=lambda: ctx.clock,
        )
    except PlaidUnavailable:
        failed = True
    after = ctx.read_state()
    cursor_ok = after[0] == before[0]
    sync_ok = after[1] == before[1]
    with ctx.session_factory() as session:
        spending = load_spending(session, ctx.user_id, ctx.period)
    ledger_ok = (
        spending.posted_cents == ctx.posted and spending.pending_cents == ctx.pending
    )
    try:
        result = calculate_budget(
            ctx.limit, spending, now=ctx.clock, plan_cap_cents=ctx.plan_cap
        )
        stale: bool | None = result.stale
    except StaleSpendingError:
        stale = None
    if stale is None:
        outcome, path = "refresh_required", "stale_reject"
    elif stale:
        outcome, path = "temporary_cap_accepted", "stale_cap_accept"
    else:
        outcome, path = "budget_ready", "accept_budget"
    return {
        "accepted": False,
        "outcome": outcome,
        "budget_path": path,
        "provider_calls": provider.calls,
        "sync_failed": failed,
        "cursor_unchanged": cursor_ok,
        "last_synced_unchanged": sync_ok,
        "ledger_unchanged": ledger_ok,
        "database_freshness_preserved": cursor_ok and sync_ok,
    }


def evaluate_refresh_case(case: dict[str, object]) -> dict[str, object]:
    gold = _as_map(case.get("expected"))
    observed = _observe(_as_map(case.get("inputs")))
    allowed = gold.get("allowed_outcomes")
    outcome_ok = isinstance(allowed, list) and any(
        _typed_equal(observed.get("outcome"), item) for item in allowed
    )
    report: dict[str, object] = {
        "case_id": "P01" if case.get("id") == "P01" else "invalid_case",
        "checks": {
            "accepted": _typed_equal(observed.get("accepted"), gold.get("accepted")),
            "outcome": bool(outcome_ok),
            "sync_failed": observed.get("sync_failed") is True,
            "cursor_unchanged": observed.get("cursor_unchanged") is True,
            "last_synced_unchanged": observed.get("last_synced_unchanged") is True,
            "ledger_unchanged": observed.get("ledger_unchanged") is True,
            "provider_calls": observed.get("provider_calls") == 1,
            "database_freshness_preserved": (
                observed.get("database_freshness_preserved") is True
            ),
        },
        "observed": observed,
        "unassessed": [*UNASSESSED, "answer_claims"],
        "evidence_class": EVIDENCE_CLASS,
        "storage": STORAGE,
    }
    if gold.get("evidence_class") == "plaid_sandbox":
        report["evidence_target"] = "plaid_sandbox"
    return report
