"""create the six core tables

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("feature_set", sa.Text(), nullable=False),
        sa.Column("data_version", sa.Text(), nullable=False),
        sa.Column(
            "trained_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("mae", sa.Numeric(), nullable=False),
        sa.Column("rmse", sa.Numeric(), nullable=False),
        sa.Column("r_squared", sa.Numeric(), nullable=False),
        sa.Column("artifact_uri", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "daily_environment",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("park_count", sa.Integer(), nullable=False),
        sa.Column("gym_count", sa.Integer(), nullable=False),
        sa.Column("grocery_store_count", sa.Integer(), nullable=False),
        sa.Column("restaurant_count", sa.Integer(), nullable=False),
        sa.Column("location_type", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "observation_date"),
    )
    op.create_table(
        "daily_finance",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("total_spending", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "grocery_spending", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "restaurant_spending", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "transportation_spending", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "fitness_spending", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column(
            "discretionary_spending", sa.Numeric(precision=12, scale=2), nullable=False
        ),
        sa.Column("cash_flow", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "observation_date"),
    )
    op.create_table(
        "daily_health",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column(
            "resting_heart_rate", sa.Numeric(precision=5, scale=2), nullable=True
        ),
        sa.Column("sleep_minutes", sa.Integer(), nullable=True),
        sa.Column("intensity_minutes", sa.Integer(), nullable=True),
        sa.Column("stress_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.CheckConstraint("steps >= 0", name="ck_daily_health_steps"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "observation_date"),
    )
    op.create_table(
        "predictions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("model_run_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("predicted_steps", sa.Numeric(), nullable=False),
        sa.Column("actual_steps", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_run_id"],
            ["model_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("predictions")
    op.drop_table("daily_health")
    op.drop_table("daily_finance")
    op.drop_table("daily_environment")
    op.drop_table("users")
    op.drop_table("model_runs")
