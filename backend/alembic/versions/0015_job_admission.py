"""Scope job request keys by operation and index admission lookups."""

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("request_namespace", sa.Text(), nullable=True))
    op.execute(
        "UPDATE jobs SET request_namespace = CASE "
        "WHEN kind = 'sync' THEN 'sync' "
        "WHEN payload ->> 'operation' = 'chat' THEN 'chat' ELSE 'plan' END"
    )
    op.alter_column(
        "jobs", "request_namespace", nullable=False, server_default=sa.text("'plan'")
    )
    op.drop_constraint("uq_jobs_user_kind_request_key", "jobs", type_="unique")
    op.create_unique_constraint(
        "uq_jobs_user_kind_namespace_request_key",
        "jobs",
        ["user_id", "kind", "request_namespace", "request_key"],
    )
    op.create_check_constraint(
        "ck_jobs_request_namespace",
        "jobs",
        "request_namespace IN ('plan', 'chat', 'sync')",
    )
    op.create_check_constraint(
        "ck_jobs_namespace_matches_payload",
        "jobs",
        "request_namespace = CASE WHEN kind = 'sync' THEN 'sync' "
        "WHEN payload ->> 'operation' = 'chat' THEN 'chat' ELSE 'plan' END",
    )
    op.create_index(
        "ix_jobs_user_status_lease", "jobs", ["user_id", "status", "lease_expires_at"]
    )
    op.create_index(
        "ix_jobs_user_kind_created", "jobs", ["user_id", "kind", "created_at"]
    )


def downgrade() -> None:
    raise NotImplementedError("Job admission migration is forward-only.")
