"""The deterministic period comparison tool."""

from datetime import date

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.tools.base import (
    ToolWarning,
    build_evidence_id,
    require_user,
    round_money,
    validate_range,
)
from app.tools.finance import FinancialContext, get_financial_context
from app.tools.health import HealthContext, get_health_context


class PeriodSummary(BaseModel):
    """The values of one period in a comparison."""

    start_date: date
    end_date: date
    health_evidence_id: str
    health_record_count: int
    finance_evidence_id: str
    finance_record_count: int
    average_steps: int
    total_spending: float


class PeriodComparison(BaseModel):
    """The two period summaries and the deltas between them."""

    user_id: int
    source: str
    evidence_id: str
    warnings: list[ToolWarning]
    period_a: PeriodSummary
    period_b: PeriodSummary
    steps_delta: int
    steps_percent_change: float | None
    spending_delta: float
    spending_percent_change: float | None


def _percent_change(value_a: float, value_b: float) -> float | None:
    """Return the change from value_a to value_b in percent.

    The result is None when value_a is 0, because the change has no base.
    """
    if value_a == 0:
        return None
    return round_money((value_b - value_a) / value_a * 100)


def _summarize(health: HealthContext, finance: FinancialContext) -> PeriodSummary:
    """Build the summary of one period from its two child results."""
    return PeriodSummary(
        start_date=health.start_date,
        end_date=health.end_date,
        health_evidence_id=health.evidence_id,
        health_record_count=health.record_count,
        finance_evidence_id=finance.evidence_id,
        finance_record_count=finance.record_count,
        average_steps=health.average_steps,
        total_spending=finance.total_spending,
    )


def compare_periods(
    session: Session,
    user_id: int,
    period_a: tuple[date, date],
    period_b: tuple[date, date],
) -> PeriodComparison:
    """Compare the steps and the spending of one user over two date ranges."""
    validate_range(*period_a)
    validate_range(*period_b)
    require_user(session, user_id)
    health_a = get_health_context(session, user_id, *period_a)
    finance_a = get_financial_context(session, user_id, *period_a)
    health_b = get_health_context(session, user_id, *period_b)
    finance_b = get_financial_context(session, user_id, *period_b)
    children = (
        (health_a, "a", "health"),
        (finance_a, "a", "finance"),
        (health_b, "b", "health"),
        (finance_b, "b", "finance"),
    )
    warnings: list[ToolWarning] = []
    for child, period, domain in children:
        warnings.extend(
            warning.model_copy(
                update={"detail": warning.detail | {"period": period, "domain": domain}}
            )
            for warning in child.warnings
        )
    spans = sorted((period_a, period_b))
    span_first = build_evidence_id("compare", user_id, *spans[0]).rsplit(":", 1)[1]
    span_second = build_evidence_id("compare", user_id, *spans[1]).rsplit(":", 1)[1]
    steps_a = health_a.average_steps
    steps_b = health_b.average_steps
    spending_a = finance_a.total_spending
    spending_b = finance_b.total_spending
    return PeriodComparison(
        user_id=user_id,
        source=",".join(
            sorted({child.source for child, _, _ in children if child.source})
        ),
        evidence_id=f"compare:user-{user_id}:{span_first}_vs_{span_second}",
        warnings=warnings,
        period_a=_summarize(health_a, finance_a),
        period_b=_summarize(health_b, finance_b),
        steps_delta=steps_b - steps_a,
        steps_percent_change=_percent_change(steps_a, steps_b),
        spending_delta=round_money(spending_b - spending_a),
        spending_percent_change=_percent_change(spending_a, spending_b),
    )
