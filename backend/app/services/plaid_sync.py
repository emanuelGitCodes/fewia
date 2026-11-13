"""Apply Plaid Sandbox sync pages to one owned Item."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.plaid_models import PlaidItem, PlaidTransaction
from app.providers.plaid import PlaidSyncMutation
from app.providers.plaid_contract import SyncPage, TransactionData
from app.services.job_delivery import JobContext, RetryableJobError
from app.services.job_effects import apply_effect, fence_job, input_digest, read_effect

_ITEM_ERROR = "Plaid Item is missing or not owned"
_PAGE_ERROR = "Plaid sync exceeded the page bound"
_RACE_ERROR = "Plaid sync snapshot changed."


class _SnapshotChanged(Exception):
    pass


@dataclass(frozen=True)
class _ItemSnapshot:
    credential_ref: str = field(repr=False)
    cursor: str | None = field(repr=False)
    last_synced_at: datetime | None


class SyncProvider(Protocol):
    def sync_page(self, credential_ref: str, cursor: str | None) -> SyncPage: ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _noop() -> None:
    return None


def _require_int(value: object, name: str, minimum: int, maximum: int | None) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} MUST be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            raise ValueError(f"{name} MUST be a positive integer")
        raise ValueError(f"{name} MUST be an integer between {minimum} and {maximum}")
    return value


def _aware_utc(value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.tzinfo.utcoffset(value) is None
    ):
        raise ValueError("now MUST be a timezone-aware datetime")
    return value.astimezone(UTC)


def _row(item_id: str, data: TransactionData) -> PlaidTransaction:
    return PlaidTransaction(
        item_id=item_id,
        transaction_id=data.transaction_id,
        account_id=data.account_id,
        amount_cents=data.amount_cents,
        currency=data.currency,
        transaction_date=data.transaction_date,
        pending=data.pending,
        pending_transaction_id=data.pending_transaction_id,
        is_grocery=data.is_grocery,
        classification_version=data.classification_version,
    )


def _apply_pages(session: Session, item_id: str, pages: list[SyncPage]) -> int:
    count = 0
    for page in pages:
        for data in (*page.added, *page.modified):
            session.merge(_row(item_id, data))
            count += 1
        session.flush()
        for transaction_id in page.removed_ids:
            session.execute(
                delete(PlaidTransaction).where(
                    PlaidTransaction.item_id == item_id,
                    PlaidTransaction.transaction_id == transaction_id,
                )
            )
            count += 1
        session.flush()
    return count


def _collect_pages(
    provider: SyncProvider,
    credential_ref: str,
    cursor: str | None,
    heartbeat: Callable[[], None],
    max_pages: int,
    max_restarts: int,
) -> list[SyncPage]:
    restarts = 0
    while True:
        pages: list[SyncPage] = []
        current = cursor
        for _ in range(max_pages):
            heartbeat()
            try:
                page = provider.sync_page(credential_ref, current)
            except PlaidSyncMutation:
                if restarts >= max_restarts:
                    raise
                restarts += 1
                break
            pages.append(page)
            if not page.has_more:
                return pages
            current = page.next_cursor
        else:
            raise ValueError(_PAGE_ERROR)


def sync_item(
    factory: sessionmaker[Session],
    item_id: str,
    provider: SyncProvider,
    *,
    user_id: int = 1,
    now: Callable[[], datetime] = _utc_now,
    heartbeat: Callable[[], None] = _noop,
    max_pages: int = 10,
    max_restarts: int = 2,
    context: JobContext | None = None,
) -> int:
    user_id = _require_int(user_id, "user_id", 1, None)
    max_pages = _require_int(max_pages, "max_pages", 1, 20)
    max_restarts = _require_int(max_restarts, "max_restarts", 0, 3)
    if context is not None and context.user_id != user_id:
        raise ValueError(_ITEM_ERROR)
    if context is not None:
        heartbeat = context.heartbeat
    effect_inputs = {
        "item_id": item_id,
        "max_pages": max_pages,
        "max_restarts": max_restarts,
    }
    for _ in range(3):
        with factory.begin() as session:
            if context is not None:
                fence_job(session, context)
                previous = read_effect(
                    session, context, "sync:0", input_digest(effect_inputs)
                )
                if previous is not None:
                    return cast(int, previous["changed_count"])
            item = session.scalar(
                select(PlaidItem).where(
                    PlaidItem.id == item_id, PlaidItem.user_id == user_id
                )
            )
            if item is None:
                raise ValueError(_ITEM_ERROR)
            snapshot = _ItemSnapshot(
                item.credential_ref, item.cursor, item.last_synced_at
            )
        heartbeat()
        pages = _collect_pages(
            provider,
            snapshot.credential_ref,
            snapshot.cursor,
            heartbeat,
            max_pages,
            max_restarts,
        )
        current = _aware_utc(now())
        heartbeat()

        def write(session: Session) -> dict[str, object]:
            owned = session.scalar(
                select(PlaidItem)
                .where(PlaidItem.id == item_id, PlaidItem.user_id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if owned is None:
                raise ValueError(_ITEM_ERROR)
            if (
                _ItemSnapshot(owned.credential_ref, owned.cursor, owned.last_synced_at)
                != snapshot
            ):
                raise _SnapshotChanged
            count = _apply_pages(session, owned.id, pages)
            owned.cursor = pages[-1].next_cursor
            prior = owned.last_synced_at
            if prior is not None:
                if prior.utcoffset() is None:
                    prior = prior.replace(tzinfo=UTC)
                owned.last_synced_at = max(current, prior + timedelta(microseconds=1))
            else:
                owned.last_synced_at = current
            return {"kind": "sync", "changed_count": count}

        try:
            if context is not None:
                result = apply_effect(factory, context, "sync:0", effect_inputs, write)
            else:
                with factory.begin() as session:
                    result = write(session)
            return cast(int, result["changed_count"])
        except _SnapshotChanged:
            if context is not None:
                break
    raise RetryableJobError(_RACE_ERROR)
