"""SQLAlchemy models for immutable grocery evidence snapshots."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

SHA256_HEX_ID = "id ~ '^[0-9a-f]{64}$'"


class GroceryEvidence(Base):
    """One immutable grocery evidence snapshot.

    The application computes id from user_id and snapshot.
    """

    __tablename__ = "grocery_evidence"
    __table_args__ = (
        # SQLite create_all skips this PostgreSQL CHECK.
        sa.CheckConstraint(
            SHA256_HEX_ID,
            name="ck_grocery_evidence_id_sha256",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), nullable=False
    )
    snapshot: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
