"""Add immutable job effect references."""

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD CONSTRAINT uq_jobs_id_user UNIQUE (id, user_id)")
    op.execute(
        """
        CREATE TABLE job_effects (
            job_id VARCHAR(36) NOT NULL,
            effect_key VARCHAR(64) NOT NULL,
            user_id BIGINT NOT NULL,
            input_digest VARCHAR(64) NOT NULL,
            result_reference JSON NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (job_id, effect_key),
            CONSTRAINT fk_job_effects_job_owner FOREIGN KEY (job_id, user_id)
                REFERENCES jobs (id, user_id),
            CONSTRAINT ck_job_effects_key CHECK (
                effect_key ~ '^(evidence|proposal|sync):[0-9]{1,6}$'
            ),
            CONSTRAINT ck_job_effects_digest CHECK (input_digest ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_job_effects_reference CHECK (
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
            )
        )
    """
    )
    op.execute("REVOKE ALL ON job_effects FROM PUBLIC")
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'fewia_app') THEN
                REVOKE ALL ON job_effects FROM fewia_app;
                GRANT SELECT, INSERT ON job_effects TO fewia_app;
            END IF;
        END $$
    """
    )


def downgrade() -> None:
    op.execute("DROP TABLE job_effects")
    op.execute("ALTER TABLE jobs DROP CONSTRAINT uq_jobs_id_user")
