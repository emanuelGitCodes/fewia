from datetime import date, datetime

from app.domain.budget import BudgetResult, SpendingSnapshot, calculate_budget

CLOCK_ERROR = "clock is invalid"
CENTS_ERROR = "cents is invalid"


def _cents(value: object) -> int:
    if type(value) is not int:
        raise TypeError(CENTS_ERROR)
    return value


def _parse_date(value: object) -> date:
    if type(value) is not str:
        raise TypeError(CLOCK_ERROR)
    parsed: date | None = None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None:
        raise TypeError(CLOCK_ERROR)
    return parsed


def _parse_clock(value: object) -> datetime:
    if type(value) is not str:
        raise TypeError(CLOCK_ERROR)
    text = value.replace("Z", "+00:00")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None:
        raise TypeError(CLOCK_ERROR)
    return parsed


def fixture_budget(inputs: dict[str, object]) -> BudgetResult:
    period = inputs.get("spending_period", inputs.get("budget_period"))
    clock = inputs.get("now")
    refreshed = inputs.get("spending_refreshed_at")
    cap = inputs.get("plan_cap_cents")
    return calculate_budget(
        _cents(inputs.get("monthly_limit_cents")),
        SpendingSnapshot(
            _parse_date(period),
            _cents(inputs.get("posted_cents")),
            _cents(inputs.get("pending_cents")),
            _parse_clock(refreshed),
        ),
        now=_parse_clock(clock),
        plan_cap_cents=None if cap is None else _cents(cap),
    )
