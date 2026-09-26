"""add the model run metadata columns

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_runs", sa.Column("model_version", sa.Text(), nullable=False))
    op.add_column("model_runs", sa.Column("random_seed", sa.Integer(), nullable=False))
    op.add_column(
        "model_runs", sa.Column("sample_size_train", sa.Integer(), nullable=False)
    )
    op.add_column(
        "model_runs", sa.Column("sample_size_test", sa.Integer(), nullable=False)
    )
    op.add_column("model_runs", sa.Column("feature_list", sa.JSON(), nullable=False))
    op.add_column("model_runs", sa.Column("split_method", sa.Text(), nullable=False))
    op.add_column(
        "model_runs", sa.Column("missing_data_policy", sa.Text(), nullable=False)
    )
    op.add_column("model_runs", sa.Column("baseline_mae", sa.Numeric(), nullable=False))
    op.create_unique_constraint(
        "uq_model_runs_model_version", "model_runs", ["model_version"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_model_runs_model_version", "model_runs")
    op.drop_column("model_runs", "baseline_mae")
    op.drop_column("model_runs", "missing_data_policy")
    op.drop_column("model_runs", "split_method")
    op.drop_column("model_runs", "feature_list")
    op.drop_column("model_runs", "sample_size_test")
    op.drop_column("model_runs", "sample_size_train")
    op.drop_column("model_runs", "random_seed")
    op.drop_column("model_runs", "model_version")
