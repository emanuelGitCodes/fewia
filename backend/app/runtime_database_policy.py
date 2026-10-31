"""Define the runtime role boundary without database effects.

Bootstrap MUST revoke default PUBLIC TEMPORARY access on the target database.
The policy queries report unsafe access; they do not change ACLs.
"""

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

RUNTIME_ROLE: Final[str] = "fewia_app"
RUNTIME_GRANTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "users": "SELECT",
        "jobs": "SELECT, INSERT, UPDATE",
        "job_outbox": "SELECT, INSERT, UPDATE",
        "shopping_handoffs": "SELECT, INSERT, UPDATE",
        "grocery_evidence": "SELECT, INSERT",
        "plan_revisions": "SELECT, INSERT",
        "plan_proposals": "SELECT, INSERT, UPDATE",
        "kroger_customer_tokens": "SELECT, INSERT, UPDATE, DELETE",
        "plaid_items": "SELECT",
        "plaid_transactions": "SELECT",
    }
)

UNSAFE_ROLE_SQL: Final[str] = """
SELECT EXISTS (
    SELECT 1 FROM pg_roles r WHERE r.rolname = 'fewia_app' AND (
        r.rolsuper OR r.rolinherit OR r.rolcreatedb OR r.rolcreaterole
        OR r.rolreplication OR r.rolbypassrls
        OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member = r.oid)
        OR EXISTS (SELECT 1 FROM pg_database d WHERE d.datdba = r.oid)
        OR EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspowner = r.oid)
        OR EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner = r.oid)
        OR EXISTS (
            SELECT 1 FROM pg_shdepend s
            WHERE s.refobjid = r.oid AND s.refclassid = 'pg_authid'::regclass
            AND s.deptype = 'o'
        )
    )
)
"""

UNSAFE_ACCESS_SQL: Final[str] = """
WITH non_system_schemas AS (
    SELECT oid, nspname FROM pg_namespace
    WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
)
SELECT
    has_database_privilege('fewia_app', current_database(), 'CREATE')
    OR has_database_privilege('fewia_app', current_database(), 'TEMPORARY')
    OR EXISTS (
        SELECT 1 FROM pg_namespace n
        WHERE has_schema_privilege('fewia_app', n.oid, 'CREATE')
    )
    OR EXISTS (
        SELECT 1 FROM pg_class c
        JOIN non_system_schemas n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL aclexplode(acldefault('r', c.relowner))
            AS p(grantor, grantee, priv, grantable)
        WHERE CASE WHEN c.relkind IN ('r', 'p', 'v', 'm', 'f') THEN (
            (
                has_table_privilege('fewia_app', c.oid, p.priv)
                OR CASE WHEN p.priv IN ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES')
                    THEN has_any_column_privilege('fewia_app', c.oid, p.priv)
                    ELSE false END
            ) AND NOT (
                n.nspname = 'public' AND (
                    (p.priv = 'SELECT' AND c.relname IN (
                        'users', 'jobs', 'job_outbox', 'shopping_handoffs',
                        'grocery_evidence', 'plan_revisions', 'plan_proposals',
                        'kroger_customer_tokens', 'plaid_items',
                        'plaid_transactions'
                    ))
                    OR (p.priv = 'INSERT' AND c.relname IN (
                        'jobs', 'job_outbox', 'shopping_handoffs',
                        'grocery_evidence', 'plan_revisions', 'plan_proposals',
                        'kroger_customer_tokens'
                    ))
                    OR (p.priv = 'UPDATE' AND c.relname IN (
                        'jobs', 'job_outbox', 'shopping_handoffs',
                        'plan_proposals', 'kroger_customer_tokens'
                    ))
                    OR (p.priv = 'DELETE' AND c.relname IN (
                        'kroger_customer_tokens'
                    ))
                )
            )
            OR has_table_privilege('fewia_app', c.oid,
                                   p.priv || ' WITH GRANT OPTION')
            OR CASE WHEN p.priv IN ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES')
                THEN has_any_column_privilege('fewia_app', c.oid,
                                             p.priv || ' WITH GRANT OPTION')
                ELSE false END
        ) ELSE false END
    )
    OR EXISTS (
        SELECT 1 FROM pg_class c
        JOIN non_system_schemas n ON n.oid = c.relnamespace
        WHERE CASE WHEN c.relkind = 'S'
            THEN has_sequence_privilege('fewia_app', c.oid, 'USAGE, SELECT, UPDATE')
            ELSE false END
    )
    OR EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN non_system_schemas n ON n.oid = p.pronamespace
        WHERE p.prosecdef AND has_function_privilege('fewia_app', p.oid, 'EXECUTE')
    )
"""


def validate_runtime_password(password: str) -> str:
    if type(password) is not str or re.fullmatch(r"[A-Za-z0-9]{32}", password) is None:
        raise ValueError("runtime database password is invalid")
    return password
