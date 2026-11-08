from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plan_proposals", sa.Column("apply_constraints", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("plan_proposals", "apply_constraints")
