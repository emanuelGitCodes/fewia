from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_FUNCTION_SQL = """
CREATE FUNCTION fewia_plan_revisions_immutable() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'plan_revisions is immutable';
END;
$$
"""

IMMUTABLE_TRIGGER_SQL = """
CREATE TRIGGER fewia_plan_revisions_immutable
BEFORE UPDATE OR DELETE ON plan_revisions
FOR EACH ROW
EXECUTE FUNCTION fewia_plan_revisions_immutable()
"""


def upgrade() -> None:
    op.create_table(
        "plan_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text(IMMUTABLE_FUNCTION_SQL))
    op.execute(sa.text(IMMUTABLE_TRIGGER_SQL))


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
