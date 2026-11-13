"""Store immutable references to durable job effects."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class JobEffect(Base):
    __tablename__ = "job_effects"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["job_id", "user_id"],
            ["jobs.id", "jobs.user_id"],
            name="fk_job_effects_job_owner",
        ),
        sa.CheckConstraint(
            sa.column("effect_key").regexp_match(
                r"^(evidence|proposal|sync):[0-9]{1,6}$"
            ),
            name="ck_job_effects_key",
        ),
        sa.CheckConstraint(
            sa.column("input_digest").regexp_match(r"^[0-9a-f]{64}$"),
            name="ck_job_effects_digest",
        ),
        sa.CheckConstraint(
            """
            octet_length(result_reference::text) <= 1024
            AND json_typeof(result_reference) = 'object'
            AND CASE result_reference->>'kind'
                WHEN 'evidence' THEN
                    result_reference::jsonb - 'kind' - 'id' = '{}'::jsonb
                    AND json_typeof(result_reference->'id') = 'string'
                    AND result_reference->>'id' ~ '^[0-9a-f]{64}$'
                WHEN 'proposal' THEN
                    result_reference::jsonb - 'kind' - 'id' = '{}'::jsonb
                    AND json_typeof(result_reference->'id') = 'string'
                    AND result_reference->>'id' ~
                        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                WHEN 'sync' THEN
                    result_reference::jsonb - 'kind' - 'changed_count' = '{}'::jsonb
                    AND json_typeof(result_reference->'changed_count') = 'number'
                    AND result_reference->>'changed_count' ~ '^[0-9]{1,10}$'
                    AND (result_reference->>'changed_count')::numeric <= 2147483647
                ELSE false
            END IS TRUE
            """,
            name="ck_job_effects_reference",
        ).ddl_if(dialect="postgresql"),
    )

    job_id: Mapped[str] = mapped_column(sa.String(36), primary_key=True)
    effect_key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    input_digest: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    result_reference: Mapped[dict[str, object]] = mapped_column(sa.JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
