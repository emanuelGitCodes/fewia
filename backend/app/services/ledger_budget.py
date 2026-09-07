"""Load grocery spending totals from owned Plaid ledger rows."""

from calendar import monthrange
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.orm import Session

from app.domain.budget import SpendingSnapshot
from app.plaid_models import PlaidItem, PlaidTransaction

_UNAVAILABLE = "Spending is unavailable"


class SpendingUnavailable(Exception):
    def __init__(self) -> None:
        super().__init__(_UNAVAILABLE)


def _require_user_id(user_id: object) -> int:
    if type(user_id) is not int:
        raise TypeError("user_id MUST be an integer")
    if user_id < 1:
        raise ValueError("user_id MUST be a positive integer")
    return user_id


def _require_period(period: object) -> date:
    if type(period) is not date:
        raise TypeError("period MUST be a date")
    if period.day != 1:
        raise ValueError("period MUST be the first day of its month")
    return period


def _stored_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _integral_cents(value: object) -> int:
    if value is None:
        return 0
    if type(value) is int:
        return value
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError("aggregate cents MUST be an exact integer")
        return int(value)
    raise TypeError("aggregate cents MUST be an integer")


def _month_end(period: date) -> date:
    return date(period.year, period.month, monthrange(period.year, period.month)[1])


def load_spending(session: Session, user_id: int, period: date) -> SpendingSnapshot:
    user_id = _require_user_id(user_id)
    period = _require_period(period)
    ready = case(
        (
            (func.trim(PlaidItem.cursor) != "") & PlaidItem.last_synced_at.is_not(None),
            1,
        ),
        else_=0,
    )
    posted_sum = func.sum(
        case((PlaidTransaction.pending.is_(False), PlaidTransaction.amount_cents))
    )
    pending_sum = func.sum(
        case((PlaidTransaction.pending.is_(True), PlaidTransaction.amount_cents))
    )
    totals = session.execute(
        select(
            func.count(distinct(PlaidItem.id)),
            func.min(ready),
            func.min(PlaidItem.last_synced_at),
            posted_sum,
            pending_sum,
        )
        .select_from(PlaidItem)
        .outerjoin(
            PlaidTransaction,
            and_(
                PlaidTransaction.item_id == PlaidItem.id,
                PlaidTransaction.currency == "USD",
                PlaidTransaction.is_grocery.is_(True),
                PlaidTransaction.transaction_date >= period,
                PlaidTransaction.transaction_date <= _month_end(period),
            ),
        )
        .where(PlaidItem.user_id == user_id)
    ).one()
    owned, readiness, last_synced_at, posted, pending = totals
    if type(owned) is not int or owned < 1:
        raise SpendingUnavailable()
    if type(readiness) is not int or readiness != 1:
        raise SpendingUnavailable()
    if not isinstance(last_synced_at, datetime):
        raise SpendingUnavailable()
    return SpendingSnapshot(
        period=period,
        posted_cents=_integral_cents(posted),
        pending_cents=_integral_cents(pending),
        refreshed_at=_stored_utc(last_synced_at),
    )
