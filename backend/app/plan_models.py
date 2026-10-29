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
