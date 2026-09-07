from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IMMUTABLE_FUNCTION_SQL = """
CREATE FUNCTION fewia_grocery_evidence_immutable() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'grocery_evidence is immutable';
END;
$$
"""

IMMUTABLE_TRIGGER_SQL = """
CREATE TRIGGER fewia_grocery_evidence_immutable
BEFORE UPDATE OR DELETE ON grocery_evidence
FOR EACH ROW
EXECUTE FUNCTION fewia_grocery_evidence_immutable()
"""


def upgrade() -> None:
    op.create_table(
        "grocery_evidence",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "id ~ '^[0-9a-f]{64}$'",
            name="ck_grocery_evidence_id_sha256",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(sa.text(IMMUTABLE_FUNCTION_SQL))
    op.execute(sa.text(IMMUTABLE_TRIGGER_SQL))


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
