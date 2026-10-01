"""Evidence ID helpers for grocery planning tools."""

from calendar import monthrange
from datetime import date


def build_evidence_id(
    domain: str, user_id: int, start_date: date, end_date: date
) -> str:
    """Build the evidence ID "{domain}:user-{user_id}:{range}".

    The range is "YYYY-MM" when start_date is the first day of a month and
    end_date is the last day of the same month. In every other case the range
    is "YYYY-MM-DD..YYYY-MM-DD". This rule is locked.
    """
    return f"{domain}:user-{user_id}:{_build_evidence_span(start_date, end_date)}"


def _build_evidence_span(start_date: date, end_date: date) -> str:
    """Build the month or day span of an evidence ID."""
    same_month = start_date.year == end_date.year and start_date.month == end_date.month
    last_day = monthrange(start_date.year, start_date.month)[1]
    if same_month and start_date.day == 1 and end_date.day == last_day:
        return f"{start_date:%Y-%m}"
    return f"{start_date:%Y-%m-%d}..{end_date:%Y-%m-%d}"
