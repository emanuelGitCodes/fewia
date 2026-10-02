from datetime import date
from typing import TypeGuard, cast, get_args

from app.domain.budget import STALE_SPENDING_WARNING, BudgetResult, SpendingSource

TOOL_NAME = "get_budget_summary"
_SOURCE_LABELS: dict[SpendingSource, str] = {
    "manual": "Your entered budget",
    "fixture": "Demo spending",
    "plaid_sandbox": "Plaid Sandbox",
}


class BudgetToolError(ValueError):
    """A budget-tool failure with a static message and no raw input."""


def budget_tool_spec() -> dict[str, object]:
    """Return the Bedrock toolSpec for get_budget_summary."""
    return {
        "toolSpec": {
            "name": TOOL_NAME,
            "description": (
                "Return the server budget summary. "
                "The tool accepts no input. "
                "The tool does not purchase items."
            ),
            "inputSchema": {
                "json": cast(
                    dict[str, object],
                    {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
            },
        }
    }


def _exact_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    magnitude = -cents if cents < 0 else cents
    return f"USD {sign}${magnitude // 100}.{magnitude % 100:02d}"


def _warnings_output(stale: bool) -> list[str]:
    if stale:
        return [STALE_SPENDING_WARNING]
    return []


def _validate_budget(budget: object) -> BudgetResult:
    if not isinstance(budget, BudgetResult):
        raise BudgetToolError("budget is invalid")
    if (
        not _exact_int(budget.available_cents)
        or budget.available_cents < 0
        or not _exact_int(budget.pending_cents)
        or type(budget.stale) is not bool
        or type(budget.warnings) is not tuple
        or not all(type(item) is str for item in budget.warnings)
    ):
        raise BudgetToolError("budget is invalid")
    return budget


def _validate_period(period: object) -> date:
    if type(period) is not date or period.day != 1:
        raise BudgetToolError("period is invalid")
    return period


def _validate_source(spending_source: object) -> SpendingSource:
    if type(spending_source) is not str or spending_source not in get_args(
        SpendingSource
    ):
        raise BudgetToolError("spending_source is invalid")
    return cast(SpendingSource, spending_source)


def _validate_facts(
    budget: object, period: object, spending_source: object
) -> tuple[BudgetResult, date, SpendingSource]:
    return (
        _validate_budget(budget),
        _validate_period(period),
        _validate_source(spending_source),
    )


def execute_budget_summary(
    arguments: object,
    budget: BudgetResult,
    period: date,
    *,
    spending_source: SpendingSource,
) -> dict[str, object]:
    """Return validated server budget facts."""
    if type(arguments) is not dict or arguments:
        raise BudgetToolError("arguments are invalid")
    valid_budget, valid_period, valid_source = _validate_facts(
        budget, period, spending_source
    )
    return {
        "period": valid_period.isoformat(),
        "spending_source": valid_source,
        "budget": {
            "available_cents": valid_budget.available_cents,
            "pending_cents": valid_budget.pending_cents,
            "stale": valid_budget.stale,
            "warnings": _warnings_output(valid_budget.stale),
        },
        "money_display": {
            "available": _usd(valid_budget.available_cents),
            "pending": _usd(valid_budget.pending_cents),
        },
    }


def budget_summary_answer(
    budget: BudgetResult,
    period: date,
    *,
    spending_source: SpendingSource,
) -> str:
    """Return a fixed reply from validated server budget facts."""
    valid_budget, _, valid_source = _validate_facts(budget, period, spending_source)
    text = (
        f"Available for this plan: {_usd(valid_budget.available_cents)}. "
        f"Pending: {_usd(valid_budget.pending_cents)}. "
        f"Source: {_SOURCE_LABELS[valid_source]}."
    )
    if valid_budget.stale:
        return f"{text} {STALE_SPENDING_WARNING}"
    return text
