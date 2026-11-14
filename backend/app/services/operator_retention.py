"""Run explicit operator actions through a dedicated PostgreSQL role."""

from __future__ import annotations

import hmac
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from time import monotonic
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.retention_manifest import (
    DELETE_ORDER,
    MAX_ROW_BYTES,
    MAX_ROWS,
    MAX_SCAN_BYTES,
    TABLES,
    VERSION,
    Manifest,
    RetentionError,
    Row,
    build_manifest,
    content_hash,
    utc,
    validate_digest,
    validate_owner,
)

ROLE = "fewia_maintenance"
_TABLE_NAMES = ", ".join(f"'{name}'" for name in TABLES)
_LOCK_SQL = (
    "LOCK TABLE "
    + ", ".join(f"public.{name}" for name in sorted(TABLES))
    + " IN SHARE ROW EXCLUSIVE MODE NOWAIT"
)
_ROLE_SAFE_SQL = """
SELECT NOT EXISTS (
    SELECT 1 FROM pg_roles r WHERE r.rolname = 'fewia_maintenance' AND (
        r.rolcanlogin OR r.rolsuper OR r.rolinherit OR r.rolcreatedb
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
) AND NOT EXISTS (
    SELECT 1 FROM pg_roles a, pg_roles m
    WHERE a.rolname = 'fewia_app' AND m.rolname = 'fewia_maintenance'
      AND pg_has_role(a.oid, m.oid, 'MEMBER')
) AND NOT has_database_privilege(current_user, current_database(), 'CREATE')
  AND NOT has_database_privilege(current_user, current_database(), 'TEMPORARY')
  AND NOT EXISTS (
    SELECT 1 FROM pg_namespace n
    WHERE has_schema_privilege(current_user, n.oid, 'CREATE')
)
"""
_ACCESS_SAFE_SQL = f"""
WITH objects AS (
    SELECT c.*, n.nspname FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
), privileges(priv) AS (
    VALUES ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'), ('TRUNCATE'),
           ('REFERENCES'), ('TRIGGER')
)
SELECT NOT EXISTS (
    SELECT 1 FROM objects c CROSS JOIN privileges p
    WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f') AND (
        (has_table_privilege(current_user, c.oid, p.priv) AND NOT (
            c.nspname = 'public' AND c.relname IN ({_TABLE_NAMES})
            AND p.priv IN ('SELECT', 'DELETE')
        )) OR has_table_privilege(current_user, c.oid, p.priv || ' WITH GRANT OPTION')
    )
) AND NOT EXISTS (
    SELECT 1 FROM objects c JOIN pg_attribute a ON a.attrelid = c.oid
    CROSS JOIN privileges p
    WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND a.attnum > 0 AND NOT a.attisdropped
      AND p.priv IN ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES') AND (
        (has_column_privilege(current_user, c.oid, a.attnum, p.priv) AND NOT (
            c.nspname = 'public' AND (
                (c.relname IN ({_TABLE_NAMES}) AND p.priv = 'SELECT') OR
                (c.relname = 'users' AND (
                    (p.priv = 'SELECT'
                     AND a.attname IN ('id', 'workspace_id', 'status'))
                    OR (p.priv = 'UPDATE' AND a.attname = 'status')
                ))
            )
        )) OR has_column_privilege(
            current_user, c.oid, a.attnum, p.priv || ' WITH GRANT OPTION'
        )
    )
) AND NOT EXISTS (
    SELECT 1 FROM objects c WHERE c.relkind = 'S' AND (
        has_sequence_privilege(current_user, c.oid, 'SELECT')
        OR has_sequence_privilege(current_user, c.oid, 'USAGE')
        OR has_sequence_privilege(current_user, c.oid, 'UPDATE')
    )
) AND NOT EXISTS (
    SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
      AND p.prosecdef AND has_function_privilege(current_user, p.oid, 'EXECUTE')
      AND NOT (
          n.nspname = 'public' AND p.proname = 'fewia_retention_schema_supported'
          AND p.pronargs = 0 AND p.prorettype = 'boolean'::regtype
          AND p.prokind = 'f' AND p.provolatile = 'v' AND NOT p.proretset
          AND p.prolang = (SELECT oid FROM pg_language WHERE lanname = 'sql')
          AND p.proconfig = ARRAY['search_path=pg_catalog']
          AND regexp_replace(p.prosrc, '[[:space:]]', '', 'g') IN (
              'LOCKTABLEpublic.alembic_versionINSHAREMODENOWAIT;'
              'SELECTcount(*)=1ANDmin(version_num)=''0018''FROMpublic.alembic_version',
              'LOCKTABLEpublic.alembic_versionINSHAREMODENOWAIT;'
              'SELECTcount(*)=1ANDmin(version_num)=''0019''FROMpublic.alembic_version'
          )
          AND NOT EXISTS (
              SELECT 1 FROM aclexplode(COALESCE(
                  p.proacl, acldefault('f', p.proowner)
              )) a WHERE a.grantee NOT IN (
                  p.proowner, (SELECT oid FROM pg_roles WHERE rolname = current_user)
              ) OR (a.grantee <> p.proowner AND a.is_grantable)
          )
          AND NOT EXISTS (
              SELECT 1 FROM pg_roles r WHERE r.rolname = 'fewia_app'
              AND has_function_privilege(r.oid, p.oid, 'EXECUTE')
          )
      )
)
"""
_MINIMUM_COLUMNS: dict[str, set[str]] = {
    "jobs": {
        "id",
        "user_id",
        "status",
        "payload",
        "result",
        "created_at",
        "lease_expires_at",
        "lease_token",
    },
    "job_outbox": {"id", "job_id", "published_at", "created_at"},
    "job_effects": {"job_id", "user_id", "effect_key", "created_at"},
    "model_call_reservations": {
        "id",
        "job_id",
        "user_id",
        "utc_day",
        "status",
        "started_at",
        "slot_deadline",
        "finished_at",
    },
    "plan_proposals": {
        "id",
        "user_id",
        "status",
        "operations",
        "apply_constraints",
        "base_plan_revision_id",
        "applied_plan_revision_id",
        "created_at",
        "updated_at",
    },
    "plan_revisions": {"id", "user_id", "snapshot", "created_at"},
    "grocery_evidence": {"id", "user_id", "snapshot", "created_at"},
    "security_intents": {
        "id",
        "user_id",
        "kind",
        "digest",
        "details",
        "state",
        "expires_at",
        "created_at",
        "updated_at",
    },
    "quota_counters": {
        "scope",
        "scope_key",
        "action",
        "minute_start",
        "expires_at",
        "count",
    },
}


def database_identity(session: Session) -> str:
    row = (
        session.execute(
            sa.text(
                "SELECT current_database() AS database_name, "
                "d.oid::bigint AS database_oid, "
                "n.oid::bigint AS schema_oid, "
                "inet_server_addr()::text AS server_address, "
                "inet_server_port() AS server_port, "
                "obj_description(to_regprocedure("
                "'public.fewia_retention_schema_supported()'), 'pg_proc') "
                "AS installation_id "
                "FROM pg_database d CROSS JOIN pg_namespace n "
                "WHERE d.datname = current_database() AND n.nspname = 'public'"
            )
        )
        .mappings()
        .one()
    )
    marker = row["installation_id"]
    if not isinstance(marker, str) or str(UUID(marker)) != marker:
        raise RetentionError()
    return content_hash(dict(row))


def _lock_owner(session: Session, owner_id: int) -> None:
    from app.services.security_admission import lock_owner

    lock_owner(session, owner_id)


def _within_budget(session: Session) -> None:
    if monotonic() > cast(float, session.info["retention_deadline"]):
        raise RetentionError()


class OperatorRetention:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name != "postgresql":
            raise RetentionError()
        self._engine = engine

    @contextmanager
    def _session(self, owner_id: int) -> Iterator[Session]:
        validate_owner(owner_id)
        try:
            with (
                self._engine.connect().execution_options(
                    isolation_level="READ COMMITTED"
                ) as connection,
                Session(bind=connection, autoflush=False) as session,
                session.begin(),
            ):
                session.execute(sa.text("SET LOCAL statement_timeout = '5s'"))
                session.execute(sa.text("SET LOCAL lock_timeout = '1s'"))
                session.execute(
                    sa.text("SET LOCAL idle_in_transaction_session_timeout = '5s'")
                )
                session.execute(sa.text("SET LOCAL ROLE fewia_maintenance"))
                session.execute(sa.text("SET LOCAL search_path = pg_catalog, public"))
                session.execute(sa.text("SET LOCAL row_security = off"))
                if session.scalar(sa.text("SELECT current_role")) != ROLE:
                    raise RetentionError()
                if session.scalar(sa.text(_ROLE_SAFE_SQL)) is not True:
                    raise RetentionError()
                if session.scalar(sa.text(_ACCESS_SAFE_SQL)) is not True:
                    raise RetentionError()
                if (
                    session.scalar(
                        sa.text(
                            "SELECT obj_description("
                            "to_regprocedure("
                            "'public.fewia_job_effects_retention_guard()'), "
                            "'pg_proc')"
                        )
                    )
                    != VERSION
                ):
                    raise RetentionError()
                _lock_owner(session, owner_id)
                if (
                    session.scalar(
                        sa.text(
                            "SELECT id FROM public.users WHERE id = :owner "
                            "FOR UPDATE NOWAIT"
                        ),
                        {"owner": owner_id},
                    )
                    != owner_id
                ):
                    raise RetentionError()
                session.info["retention_deadline"] = monotonic() + 5
                if (
                    session.scalar(
                        sa.text("SELECT public.fewia_retention_schema_supported()")
                    )
                    is not True
                ):
                    raise RetentionError()
                session.info["retention_database_id"] = database_identity(session)
                yield session
                _within_budget(session)
        except (SQLAlchemyError, ImportError, ValueError, TypeError, KeyError):
            raise RetentionError() from None

    def _snapshot(
        self, session: Session, owner_id: int, before: datetime
    ) -> tuple[Manifest, dict[str, sa.Table]]:
        session.execute(sa.text(_LOCK_SQL))
        owner = (
            session.execute(
                sa.text(
                    "SELECT status, workspace_id FROM public.users WHERE id = :owner"
                ),
                {"owner": owner_id},
            )
            .mappings()
            .one_or_none()
        )
        if owner is None or not isinstance(owner["workspace_id"], UUID):
            raise RetentionError()
        owner_status = owner["status"]
        if not isinstance(owner_status, str):
            raise RetentionError()
        now = utc(session.scalar(sa.select(sa.func.clock_timestamp())))
        before = utc(before)
        if before > now:
            raise RetentionError()
        if (
            session.scalar(
                sa.text(
                    "SELECT EXISTS (SELECT 1 FROM pg_constraint k "
                    "JOIN pg_class c ON c.oid = k.confrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    f"WHERE n.nspname = 'public' AND c.relname IN ({_TABLE_NAMES}) "
                    "AND k.contype = 'f' AND k.confdeltype NOT IN ('a', 'r'))"
                )
            )
            is not False
        ):
            raise RetentionError()
        tables: dict[str, sa.Table] = {}
        rows: dict[str, list[Row]] = {}
        remaining = MAX_ROWS
        remaining_bytes = MAX_SCAN_BYTES
        for name in TABLES:
            _within_budget(session)
            table = sa.Table(
                name,
                sa.MetaData(),
                schema="public",
                autoload_with=session.connection(),
                resolve_fks=False,
            )
            if (
                not _MINIMUM_COLUMNS[name] <= set(table.c.keys())
                or len(table.primary_key.columns) == 0
            ):
                raise RetentionError()
            if name == "job_effects" and (
                not {"input_digest", "input_hash"}.intersection(table.c.keys())
                or not {"result_ref", "result_reference", "result"}.intersection(
                    table.c.keys()
                )
            ):
                raise RetentionError()
            if any(
                not str(column.name).replace("_", "").isascii()
                or not str(column.name).replace("_", "").isalnum()
                for column in table.c
            ):
                raise RetentionError()
            columns = [column for column in table.c if column.name != "lease_token"]
            selection = ", ".join(f'"{column.name}"' for column in columns)
            if name == "jobs":
                selection += ", lease_token IS NOT NULL AS has_lease_token"
            sizes = (
                session.execute(
                    sa.text(
                        "SELECT count(*) AS row_count, "
                        "COALESCE(max(row_bytes), 0) AS maximum, "
                        "COALESCE(sum(row_bytes), 0) AS total FROM ("
                        "SELECT octet_length(row_to_json(b)::text) AS row_bytes "
                        f"FROM (SELECT {selection} FROM public.{name} "
                        "LIMIT :limit) b) sizes"
                    ),
                    {"limit": remaining + 1},
                )
                .mappings()
                .one()
            )
            maximum, total, row_count = (
                sizes["maximum"],
                sizes["total"],
                sizes["row_count"],
            )
            if (
                not isinstance(maximum, int)
                or not isinstance(total, int)
                or not isinstance(row_count, int)
                or row_count > remaining
                or maximum > MAX_ROW_BYTES
                or total > remaining_bytes
            ):
                raise RetentionError()
            remaining_bytes -= total
            result = session.execute(
                sa.text(f"SELECT {selection} FROM public.{name} LIMIT :limit"),
                {"limit": remaining + 1},
            ).mappings()
            group: list[Row] = []
            while batch := result.fetchmany(128):
                group.extend(dict(cast(Mapping[str, object], row)) for row in batch)
                if len(group) > remaining:
                    raise RetentionError()
            remaining -= len(group)
            tables[name], rows[name] = table, group
        schema_query = (
            "SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid) AS definition, "
            "pg_get_functiondef(t.tgfoid) AS function_definition, t.tgenabled "
            "FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            f"WHERE n.nspname = 'public' AND c.relname IN ({_TABLE_NAMES}) "
            "AND NOT t.tgisinternal ORDER BY c.relname, t.tgname LIMIT 16"
        )
        schema_sizes = (
            session.execute(
                sa.text(
                    "SELECT COALESCE(max(octet_length(row_to_json(b)::text)), 0) "
                    "AS maximum, "
                    "COALESCE(sum(octet_length(row_to_json(b)::text)), 0) AS total "
                    f"FROM ({schema_query}) b"
                )
            )
            .mappings()
            .one()
        )
        if (
            not isinstance(schema_sizes["maximum"], int)
            or not isinstance(schema_sizes["total"], int)
            or schema_sizes["maximum"] > MAX_ROW_BYTES
            or schema_sizes["total"] > remaining_bytes
        ):
            raise RetentionError()
        schema_state = session.execute(sa.text(schema_query)).mappings().all()
        expected_triggers = {
            ("grocery_evidence", "fewia_grocery_evidence_immutable"),
            ("plan_revisions", "fewia_plan_revisions_immutable"),
            ("model_call_reservations", "model_call_reservations_guard"),
            ("job_effects", "fewia_job_effects_retention_guard"),
        }
        if {
            (row["relname"], row["tgname"]) for row in schema_state
        } != expected_triggers or any(row["tgenabled"] != "O" for row in schema_state):
            raise RetentionError()
        manifest = build_manifest(
            rows,
            owner_id=owner_id,
            before=before,
            now=now,
            database_id=cast(str, session.info["retention_database_id"]),
            context_digest=content_hash(
                {
                    "workspace": owner["workspace_id"],
                    "triggers": [dict(row) for row in schema_state],
                }
            ),
            owner_status=owner_status,
        )
        _within_budget(session)
        return manifest, tables

    def preview(self, *, owner_id: int, before: datetime) -> dict[str, object]:
        before = utc(before)
        with self._session(owner_id) as session:
            manifest, _ = self._snapshot(session, owner_id, before)
            return manifest.public()

    def purge(
        self, *, owner_id: int, before: datetime, digest: str
    ) -> dict[str, object]:
        validate_digest(digest)
        before = utc(before)
        with self._session(owner_id) as session:
            manifest, tables = self._snapshot(session, owner_id, before)
            if manifest.blockers or not hmac.compare_digest(manifest.digest, digest):
                raise RetentionError()
            for name in DELETE_ORDER:
                table = tables[name]
                group = manifest.candidates[name]
                for offset in range(0, len(group), 128):
                    _within_budget(session)
                    batch = group[offset : offset + 128]
                    condition = sa.or_(
                        *(
                            sa.and_(
                                *(
                                    column == row[column.name]
                                    for column in table.primary_key
                                )
                            )
                            for row in batch
                        )
                    )
                    deleted = session.scalars(
                        sa.delete(table).where(condition).returning(sa.literal(1))
                    ).all()
                    if len(deleted) != len(batch):
                        raise RetentionError()
            response = manifest.public()
            response["purged"] = True
        return response

    def set_owner_status(
        self, *, owner_id: int, workspace_id: UUID, enabled: bool
    ) -> dict[str, object]:
        if not isinstance(workspace_id, UUID) or type(enabled) is not bool:
            raise RetentionError()
        expected, target = ("disabled", "active") if enabled else ("active", "disabled")
        with self._session(owner_id) as session:
            changed = session.scalar(
                sa.text(
                    "UPDATE public.users SET status = :target WHERE id = :owner "
                    "AND workspace_id = :workspace AND status = :expected RETURNING id"
                ),
                {
                    "owner": owner_id,
                    "workspace": workspace_id,
                    "expected": expected,
                    "target": target,
                },
            )
            if changed != owner_id:
                raise RetentionError()
        return {"status": target}
