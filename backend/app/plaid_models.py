"""SQLAlchemy models for Plaid Sandbox ledger data."""

from datetime import date, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PlaidItem(Base):
    __tablename__ = "plaid_items"
    __table_args__ = (
        sa.UniqueConstraint("provider_item_id", name="uq_plaid_items_provider_item_id"),
    )

    id: Mapped[str] = mapped_column(
        sa.String(length=36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), nullable=False
    )
    provider_item_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    credential_ref: Mapped[str] = mapped_column(sa.Text, nullable=False)
    cursor: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


class PlaidTransaction(Base):
    __tablename__ = "plaid_transactions"
    __table_args__ = (
        sa.CheckConstraint(
            "currency = 'USD'", name="ck_plaid_transactions_currency_usd"
        ),
        sa.Index(
            "ix_plaid_transactions_item_date_pending",
            "item_id",
            "transaction_date",
            "pending",
        ),
    )

    item_id: Mapped[str] = mapped_column(
        sa.String(length=36),
        sa.ForeignKey("plaid_items.id"),
        primary_key=True,
    )
    transaction_id: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    account_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    amount_cents: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(sa.Text, nullable=False)
    transaction_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    pending: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    pending_transaction_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_grocery: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    classification_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
