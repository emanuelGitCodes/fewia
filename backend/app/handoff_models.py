"""SQLAlchemy models for Instacart development shopping-list handoffs."""

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ShoppingHandoff(Base):
    __tablename__ = "shopping_handoffs"
    __table_args__ = (
        sa.CheckConstraint(
            "state IN ('prepared', 'dispatching', 'succeeded', 'failed', 'uncertain')",
            name="ck_shopping_handoffs_state",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_shopping_handoffs_attempts"),
        sa.CheckConstraint(
            "state <> 'dispatching' OR (attempt_token IS NOT NULL AND"
            " started_at IS NOT NULL)",
            name="ck_shopping_handoffs_dispatching",
        ),
        sa.CheckConstraint(
            "state <> 'succeeded' OR url IS NOT NULL",
            name="ck_shopping_handoffs_succeeded",
        ),
        sa.UniqueConstraint(
            "user_id",
            "request_hash",
            name="uq_shopping_handoffs_user_request_hash",
        ),
    )

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), nullable=False
    )
    request_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    request_payload: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False)
    state: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default=sa.text("'prepared'")
    )
    attempt_token: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    retry_authorized_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
