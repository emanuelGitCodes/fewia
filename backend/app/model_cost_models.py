from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ModelCallReservation(Base):
    __tablename__ = "model_call_reservations"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["job_id", "user_id"],
            ["jobs.id", "jobs.user_id"],
            name="fk_model_calls_job_owner",
        ),
        sa.UniqueConstraint("job_id", "attempt", "turn", name="uq_model_calls_turn"),
        sa.CheckConstraint("attempt > 0 AND turn > 0", name="ck_model_calls_turn"),
        sa.CheckConstraint("reserved_microdollars > 0", name="ck_model_calls_reserved"),
        sa.CheckConstraint(
            "(status = 'in_flight' AND charged_microdollars IS NULL "
            "AND finished_at IS NULL) OR "
            "(status = 'unknown' AND charged_microdollars IS NULL "
            "AND finished_at IS NOT NULL) OR "
            "(status = 'settled' AND charged_microdollars IS NOT NULL "
            "AND charged_microdollars >= 0 "
            "AND charged_microdollars <= reserved_microdollars "
            "AND finished_at IS NOT NULL)",
            name="ck_model_calls_state",
        ),
        sa.CheckConstraint(
            "slot_deadline > started_at "
            "AND (finished_at IS NULL OR finished_at >= started_at)",
            name="ck_model_calls_time",
        ),
        sa.CheckConstraint(
            "slot_deadline = started_at + interval '60 seconds' "
            "AND utc_day = (started_at AT TIME ZONE 'UTC')::date",
            name="ck_model_calls_clock",
        ).ddl_if(dialect="postgresql"),
        sa.Index("ix_model_calls_live_slots", "status", "slot_deadline"),
        sa.Index("ix_model_calls_daily_owner", "utc_day", "user_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(sa.String(36), nullable=False)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    attempt: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    turn: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    model_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    region: Mapped[str] = mapped_column(sa.Text, nullable=False)
    rate_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    utc_day: Mapped[date] = mapped_column(sa.Date, nullable=False)
    reserved_microdollars: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    charged_microdollars: Mapped[int | None] = mapped_column(sa.BigInteger)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    slot_deadline: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
