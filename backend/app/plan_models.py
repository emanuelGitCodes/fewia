"""SQLAlchemy model for immutable plan revisions."""

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PlanRevision(Base):
    """One immutable saved plan. The application generates the id."""

    __tablename__ = "plan_revisions"

    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), nullable=False
    )
    snapshot: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class PlanProposal(Base):
    """A validated change to a saved plan revision, applied or discarded once."""

    __tablename__ = "plan_proposals"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'discarded')",
            name="ck_plan_proposals_status",
        ),
        sa.CheckConstraint(
            "(applied_plan_revision_id IS NOT NULL) = (status = 'applied')",
            name="ck_plan_proposals_applied_revision",
        ),
    )

    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger, sa.ForeignKey("users.id"), nullable=False
    )
    base_plan_revision_id: Mapped[UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("plan_revisions.id"), nullable=False
    )
    operations: Mapped[list[dict[str, object]]] = mapped_column(sa.JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default=sa.text("'pending'")
    )
    applied_plan_revision_id: Mapped[UUID | None] = mapped_column(
        sa.Uuid, sa.ForeignKey("plan_revisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
