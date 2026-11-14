"""Add model call reservations."""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels: str | None = None
depends_on: str | None = None

GUARD_FUNCTION_SQL = """
CREATE FUNCTION model_call_reservations_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status = 'in_flight' THEN
            RETURN NEW;
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.status = 'in_flight'
           AND NEW.status IN ('settled', 'unknown')
           AND ROW(NEW.id, NEW.job_id, NEW.user_id, NEW.attempt, NEW.turn,
                   NEW.model_id, NEW.region, NEW.rate_version, NEW.utc_day,
                   NEW.reserved_microdollars, NEW.started_at, NEW.slot_deadline)
               IS NOT DISTINCT FROM
               ROW(OLD.id, OLD.job_id, OLD.user_id, OLD.attempt, OLD.turn,
                   OLD.model_id, OLD.region, OLD.rate_version, OLD.utc_day,
                   OLD.reserved_microdollars, OLD.started_at, OLD.slot_deadline)
        THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION 'Model reservation mutation is invalid' USING ERRCODE = '23514';
END;
$$
"""

GUARD_TRIGGER_SQL = """
CREATE TRIGGER model_call_reservations_guard
BEFORE INSERT OR UPDATE OR DELETE ON model_call_reservations
FOR EACH ROW EXECUTE FUNCTION model_call_reservations_guard()
"""


def upgrade() -> None:
    op.create_table(
        "model_call_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("rate_version", sa.Text(), nullable=False),
        sa.Column("utc_day", sa.Date(), nullable=False),
        sa.Column("reserved_microdollars", sa.BigInteger(), nullable=False),
        sa.Column("charged_microdollars", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        ),
    )
    op.create_index(
        "ix_model_calls_live_slots",
        "model_call_reservations",
        ["status", "slot_deadline"],
    )
    op.create_index(
        "ix_model_calls_daily_owner",
        "model_call_reservations",
        ["utc_day", "user_id"],
    )
    op.execute(GUARD_FUNCTION_SQL)
    op.execute(GUARD_TRIGGER_SQL)


def downgrade() -> None:
    raise NotImplementedError("Model cost reservations use a forward-only migration.")
