"""Shared models, errors, and helpers for the deterministic context tools."""

from calendar import monthrange
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

MAX_RANGE_DAYS = 366

WarningCode = Literal["no_records", "missing_days", "null_fields"]


class ToolWarning(BaseModel):
    """One data-quality warning that a tool attaches to its result."""

    code: WarningCode
    message: str
    detail: dict[str, str]


class ContextResponse(BaseModel):
    """Fields that every deterministic context tool returns."""

    user_id: int
    start_date: date
    end_date: date
    record_count: int
    source: str
    evidence_id: str
    warnings: list[ToolWarning]


class ToolError(Exception):
    """An error that a tool reports to the caller with an HTTP status."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def build_evidence_id(
    domain: str, user_id: int, start_date: date, end_date: date
) -> str:
    """Build the evidence ID "{domain}:user-{user_id}:{range}".

    The range is "YYYY-MM" when start_date is the first day of a month and
    end_date is the last day of the same month. In every other case the range
    is "YYYY-MM-DD..YYYY-MM-DD". This rule is locked.
    """
    same_month = start_date.year == end_date.year and start_date.month == end_date.month
    last_day = monthrange(start_date.year, start_date.month)[1]
    if same_month and start_date.day == 1 and end_date.day == last_day:
        span = f"{start_date:%Y-%m}"
    else:
        span = f"{start_date:%Y-%m-%d}..{end_date:%Y-%m-%d}"
    return f"{domain}:user-{user_id}:{span}"


def validate_range(start_date: date, end_date: date) -> None:
    """Reject a reversed range or a range longer than MAX_RANGE_DAYS days."""
    if start_date > end_date:
        message = "start_date MUST NOT come after end_date."
    elif (end_date - start_date).days + 1 > MAX_RANGE_DAYS:
        message = f"The range MUST NOT cover more than {MAX_RANGE_DAYS} days."
    else:
        return
    raise ToolError(code="invalid_range", message=message, status_code=422)


def require_user(session: Session, user_id: int) -> None:
    """Reject a user ID that no users row holds."""
    found = session.execute(select(User.id).where(User.id == user_id)).first()
    if found is None:
        message = f"No user has the id {user_id}."
        raise ToolError(code="user_not_found", message=message, status_code=404)


def missing_day_warnings(
    record_count: int, start_date: date, end_date: date
) -> list[ToolWarning]:
    """Report an empty result or a result that misses days of the range."""
    day_count = (end_date - start_date).days + 1
    detail = {"record_count": str(record_count), "day_count": str(day_count)}
    if record_count == 0:
        code: WarningCode = "no_records"
        message = "The range holds no records."
    elif record_count < day_count:
        code = "missing_days"
        message = "The range misses one or more days."
    else:
        return []
    return [ToolWarning(code=code, message=message, detail=detail)]


def round_money(value: Decimal | float) -> float:
    """Round a money value to 2 decimals."""
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
