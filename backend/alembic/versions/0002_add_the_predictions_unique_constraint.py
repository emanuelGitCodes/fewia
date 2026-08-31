"""add the predictions unique constraint

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_predictions_run_user_date",
        "predictions",
        ["model_run_id", "user_id", "observation_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_predictions_run_user_date", "predictions")
