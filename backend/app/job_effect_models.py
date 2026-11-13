"""Store immutable references to durable job effects."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class JobEffect(Base):
    __tablename__ = "job_effects"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["job_id", "user_id"],
            ["jobs.id", "jobs.user_id"],
            name="fk_job_effects_job_owner",
        ),
        sa.CheckConstraint(
            "length(effect_key) BETWEEN 1 AND 64", name="ck_job_effects_key"
        ),
        sa.CheckConstraint("length(input_digest) = 64", name="ck_job_effects_digest"),
    )

    job_id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    effect_key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    input_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    result_reference: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
