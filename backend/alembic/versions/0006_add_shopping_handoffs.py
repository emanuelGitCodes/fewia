from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shopping_handoffs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column(
            "state", sa.Text(), server_default=sa.text("'prepared'"), nullable=False
        ),
        sa.Column("attempt_token", sa.Text(), nullable=True),
        sa.Column(
            "attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("retry_authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "request_hash",
            name="uq_shopping_handoffs_user_request_hash",
        ),
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
