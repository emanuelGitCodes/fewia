"""Build server-owned grocery spending input for HTTP jobs."""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.domain.budget import NEW_YORK
from app.services.ledger_budget import (
    SpendingUnavailable as SpendingUnavailable,
)
from app.services.ledger_budget import (
    load_spending,
)
from app.services.plan_job import SpendingInput

FIXTURE_POSTED_CENTS = 18000
FIXTURE_PENDING_CENTS = 1200
SpendingSource = Literal["fixture", "plaid_sandbox"]


def spending_input(
    session: Session,
    user_id: int,
    source: str,
    now: datetime,
) -> SpendingInput:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now MUST be timezone-aware")
    period = now.astimezone(NEW_YORK).date().replace(day=1)
    if source == "fixture":
        return SpendingInput(
            period=period,
            posted_cents=FIXTURE_POSTED_CENTS,
            pending_cents=FIXTURE_PENDING_CENTS,
            refreshed_at=now.astimezone(UTC),
        )
    if source != "plaid_sandbox":
        raise SpendingUnavailable()
    snapshot = load_spending(session, user_id, period)
    return SpendingInput(
        period=snapshot.period,
        posted_cents=snapshot.posted_cents,
        pending_cents=snapshot.pending_cents,
        refreshed_at=snapshot.refreshed_at,
    )
