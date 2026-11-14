"""Create durable action quota counters."""

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "quota_counters",
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.BigInteger(), nullable=False),
        sa.Column("minute_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "action", "scope", "scope_key", "minute_start", name="pk_quota_counters"
        ),
        sa.CheckConstraint(
            "(action = 'mutation' AND scope = 'user' AND scope_key > 0) OR "
            "(action = 'retailer' AND ((scope = 'global' AND scope_key = 0) OR "
            "(scope = 'user' AND scope_key > 0)))",
            name="ck_quota_counters_action_scope_key",
        ),
        sa.CheckConstraint("count > 0", name="ck_quota_counters_count_positive"),
        sa.CheckConstraint(
            "expires_at > minute_start", name="ck_quota_counters_expiry"
        ),
    )
    op.create_index("ix_quota_counters_expires_at", "quota_counters", ["expires_at"])


def downgrade() -> None:
    raise NotImplementedError("Quota counter migration is forward-only.")
