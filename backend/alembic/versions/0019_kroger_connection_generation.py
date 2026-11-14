"""Fence token replacement with a durable connection generation."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "kroger_owners",
        sa.Column(
            "connection_generation",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )
    op.execute(
        """
CREATE OR REPLACE FUNCTION public.fewia_retention_schema_supported() RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog AS $$
LOCK TABLE public.alembic_version IN SHARE MODE NOWAIT;
SELECT count(*) = 1 AND min(version_num) = '0019' FROM public.alembic_version
$$
"""
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
