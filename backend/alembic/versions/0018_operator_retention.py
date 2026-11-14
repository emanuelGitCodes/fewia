"""Add the dedicated operator maintenance boundary."""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_SQL = """
DO $$
DECLARE created boolean := false;
BEGIN
    IF current_setting('server_version_num')::integer < 160000 THEN
        RAISE EXCEPTION 'PostgreSQL 16 or later is required';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fewia_maintenance') THEN
        CREATE ROLE fewia_maintenance NOLOGIN NOINHERIT NOSUPERUSER
            NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
        created := true;
    END IF;
    IF created AND EXISTS (
        SELECT 1 FROM pg_auth_members m
        JOIN pg_roles r ON r.oid = m.roleid
        JOIN pg_roles u ON u.oid = m.member
        WHERE r.rolname = 'fewia_maintenance' AND u.rolname = current_user
          AND (m.inherit_option OR m.set_option OR NOT m.admin_option)
    ) THEN
        RAISE EXCEPTION 'Unsafe maintenance creator membership';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_roles r WHERE r.rolname = 'fewia_maintenance' AND (
            r.rolcanlogin OR r.rolinherit OR r.rolsuper OR r.rolcreatedb
            OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls
            OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid)
            OR EXISTS (SELECT 1 FROM pg_shdepend d
                WHERE d.refclassid = 'pg_authid'::regclass
                  AND d.refobjid = r.oid AND d.deptype = 'o')
            OR EXISTS (SELECT 1 FROM pg_database d WHERE d.datdba = r.oid)
            OR EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspowner = r.oid)
            OR EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner = r.oid)
            OR EXISTS (SELECT 1 FROM pg_default_acl a
                CROSS JOIN LATERAL aclexplode(a.defaclacl) x
                WHERE x.grantee = r.oid)
        )
    ) OR EXISTS (
        SELECT 1 FROM pg_roles a, pg_roles m
        WHERE a.rolname = 'fewia_app' AND m.rolname = 'fewia_maintenance'
          AND pg_has_role(a.oid, m.oid, 'MEMBER')
    ) THEN
        RAISE EXCEPTION 'Unsafe maintenance role';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(c.relacl) a
        JOIN pg_roles r ON r.oid = a.grantee
        WHERE r.rolname = 'fewia_maintenance' AND (
            a.is_grantable OR NOT (
                n.nspname = 'public' AND c.relname IN (
                    'jobs', 'job_outbox', 'job_effects', 'model_call_reservations',
                    'plan_proposals', 'plan_revisions', 'grocery_evidence',
                    'security_intents', 'quota_counters'
                ) AND a.privilege_type IN ('SELECT', 'DELETE')
            )
        )
    ) OR EXISTS (
        SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(a.attacl) x
        JOIN pg_roles r ON r.oid = x.grantee
        WHERE r.rolname = 'fewia_maintenance' AND (
            x.is_grantable OR NOT (
                n.nspname = 'public' AND c.relname = 'users' AND (
                    (x.privilege_type = 'SELECT'
                     AND a.attname IN ('id', 'workspace_id', 'status'))
                    OR (x.privilege_type = 'UPDATE' AND a.attname = 'status')
                )
            )
        )
    ) OR EXISTS (
        SELECT 1 FROM pg_namespace n
        CROSS JOIN LATERAL aclexplode(n.nspacl) a
        JOIN pg_roles r ON r.oid = a.grantee
        WHERE r.rolname = 'fewia_maintenance' AND (
            a.is_grantable OR n.nspname <> 'public' OR a.privilege_type <> 'USAGE'
        )
    ) OR EXISTS (
        SELECT 1 FROM pg_database d
        CROSS JOIN LATERAL aclexplode(d.datacl) a
        JOIN pg_roles r ON r.oid = a.grantee
        WHERE r.rolname = 'fewia_maintenance'
          AND (a.is_grantable OR a.privilege_type <> 'CONNECT')
    ) OR EXISTS (
        SELECT 1 FROM pg_proc p
        CROSS JOIN LATERAL aclexplode(p.proacl) a
        JOIN pg_roles r ON r.oid = a.grantee
        WHERE r.rolname = 'fewia_maintenance'
          AND (a.is_grantable OR (
              p.prosecdef AND p.proname <> 'fewia_retention_schema_supported'
          ))
    ) THEN
        RAISE EXCEPTION 'Unsafe maintenance access';
    END IF;
END;
$$
"""

TABLES = (
    "jobs",
    "job_outbox",
    "job_effects",
    "model_call_reservations",
    "plan_proposals",
    "plan_revisions",
    "grocery_evidence",
    "security_intents",
    "quota_counters",
)

EFFECTIVE_ACCESS_SQL = """
DO $$
DECLARE obj record; col record; privilege text; allowed boolean;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_namespace n
        WHERE has_schema_privilege('fewia_maintenance', n.oid, 'CREATE')
    ) OR has_database_privilege('fewia_maintenance', current_database(), 'CREATE')
    OR EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
          AND p.prosecdef AND has_function_privilege(
              'fewia_maintenance', p.oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'Unsafe maintenance access';
    END IF;
    FOR obj IN SELECT c.*, n.nspname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
    LOOP
        IF obj.relkind = 'S' THEN
            IF has_sequence_privilege('fewia_maintenance', obj.oid, 'USAGE')
               OR has_sequence_privilege('fewia_maintenance', obj.oid, 'SELECT')
               OR has_sequence_privilege('fewia_maintenance', obj.oid, 'UPDATE') THEN
                RAISE EXCEPTION 'Unsafe maintenance access';
            END IF;
            CONTINUE;
        END IF;
        FOREACH privilege IN ARRAY ARRAY[
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
        ] LOOP
            allowed := obj.nspname = 'public' AND obj.relname IN (
                'jobs', 'job_outbox', 'job_effects', 'model_call_reservations',
                'plan_proposals', 'plan_revisions', 'grocery_evidence',
                'security_intents', 'quota_counters'
            ) AND privilege IN ('SELECT', 'DELETE');
            IF (has_table_privilege('fewia_maintenance', obj.oid, privilege)
                AND NOT allowed) OR has_table_privilege(
                    'fewia_maintenance', obj.oid, privilege || ' WITH GRANT OPTION'
                ) THEN
                RAISE EXCEPTION 'Unsafe maintenance access';
            END IF;
            IF privilege NOT IN ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES') THEN
                CONTINUE;
            END IF;
            FOR col IN SELECT attnum, attname FROM pg_attribute
                WHERE attrelid = obj.oid AND attnum > 0 AND NOT attisdropped
            LOOP
                IF (has_column_privilege(
                    'fewia_maintenance', obj.oid, col.attnum, privilege
                ) AND NOT (allowed OR (
                    obj.nspname = 'public' AND obj.relname = 'users' AND (
                        (privilege = 'SELECT'
                         AND col.attname IN ('id', 'workspace_id', 'status')) OR
                        (privilege = 'UPDATE' AND col.attname = 'status')
                    )
                ))) OR has_column_privilege(
                    'fewia_maintenance', obj.oid, col.attnum,
                    privilege || ' WITH GRANT OPTION'
                ) THEN
                    RAISE EXCEPTION 'Unsafe maintenance access';
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;
    IF EXISTS (SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'public.job_effects'::regclass AND NOT tgisinternal) THEN
        RAISE EXCEPTION 'Unknown job effect trigger contract';
    END IF;
END;
$$
"""

COST_GUARD_SQL = """
CREATE OR REPLACE FUNCTION public.model_call_reservations_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_user = 'fewia_maintenance'
       AND TG_TABLE_SCHEMA = 'public'
       AND TG_TABLE_NAME = 'model_call_reservations' THEN
        RETURN OLD;
    ELSIF TG_OP = 'INSERT' THEN
        IF NEW.status = 'in_flight' THEN
            RETURN NEW;
        END IF;
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.status = 'in_flight'
           AND NEW.status IN ('settled', 'unknown')
           AND ROW(NEW.id, NEW.job_id, NEW.user_id, NEW.attempt, NEW.turn,
                   NEW.model_id, NEW.region, NEW.rate_version, NEW.utc_day,
                   NEW.reserved_microdollars, NEW.started_at, NEW.slot_deadline)
               IS NOT DISTINCT FROM
               ROW(OLD.id, OLD.job_id, OLD.user_id, OLD.attempt, OLD.turn,
                   OLD.model_id, OLD.region, OLD.rate_version, OLD.utc_day,
                   OLD.reserved_microdollars, OLD.started_at, OLD.slot_deadline)
        THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION 'Model reservation mutation is invalid' USING ERRCODE = '23514';
END;
$$
"""


def upgrade() -> None:
    op.execute(sa.text(ROLE_SQL))
    op.execute(sa.text(EFFECTIVE_ACCESS_SQL))
    op.execute("GRANT USAGE ON SCHEMA public TO fewia_maintenance")
    for table in TABLES:
        op.execute(f"GRANT SELECT, DELETE ON TABLE public.{table} TO fewia_maintenance")
    op.execute(
        "GRANT SELECT (id, workspace_id, status), UPDATE (status) "
        "ON TABLE public.users TO fewia_maintenance"
    )
    for table in ("grocery_evidence", "plan_revisions"):
        op.execute(
            f"""
CREATE OR REPLACE FUNCTION public.fewia_{table}_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_user = 'fewia_maintenance'
       AND TG_TABLE_SCHEMA = 'public' AND TG_TABLE_NAME = '{table}' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '{table} is immutable';
END;
$$
"""
        )
    op.execute(COST_GUARD_SQL)
    op.execute(
        """
CREATE FUNCTION public.fewia_job_effects_retention_guard() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_user = 'fewia_maintenance'
       AND TG_TABLE_SCHEMA = 'public' AND TG_TABLE_NAME = 'job_effects' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'job_effects is immutable';
END;
$$
"""
    )
    op.execute(
        "CREATE TRIGGER fewia_job_effects_retention_guard "
        "BEFORE UPDATE OR DELETE ON public.job_effects FOR EACH ROW "
        "EXECUTE FUNCTION public.fewia_job_effects_retention_guard()"
    )
    op.execute(
        "COMMENT ON FUNCTION public.fewia_job_effects_retention_guard() "
        "IS '0018:operator-retention:1'"
    )
    op.execute(
        """
CREATE FUNCTION public.fewia_retention_schema_supported() RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog AS $$
LOCK TABLE public.alembic_version IN SHARE MODE NOWAIT;
SELECT count(*) = 1 AND min(version_num) = '0018' FROM public.alembic_version
$$
"""
    )
    op.execute(
        f"COMMENT ON FUNCTION public.fewia_retention_schema_supported() IS '{uuid4()}'"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.fewia_retention_schema_supported() FROM PUBLIC"
    )
    op.execute(
        """
DO $$
DECLARE recipient record;
BEGIN
    FOR recipient IN SELECT DISTINCT r.rolname FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        CROSS JOIN LATERAL aclexplode(p.proacl) a
        JOIN pg_roles r ON r.oid = a.grantee
        WHERE n.nspname = 'public'
          AND p.proname = 'fewia_retention_schema_supported' AND p.pronargs = 0
          AND a.grantee <> p.proowner
    LOOP
        EXECUTE format(
            'REVOKE ALL ON FUNCTION public.fewia_retention_schema_supported() FROM %I',
            recipient.rolname
        );
    END LOOP;
END;
$$
"""
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.fewia_retention_schema_supported() "
        "TO fewia_maintenance"
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
