from __future__ import annotations

import importlib.util
import json
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import ModuleType
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import retention_admin
from app.runtime_database_policy import UNSAFE_ACCESS_SQL, UNSAFE_ROLE_SQL
from app.services import operator_retention
from app.services.job_leases import claim_job
from app.services.operator_retention import OperatorRetention, database_identity
from app.services.retention_manifest import (
    MAX_ROWS,
    TABLES,
    Manifest,
    RetentionError,
    Row,
    build_manifest,
    references,
)
from tests.conftest import require_test_database_url
from tests.test_runtime_database_access import (
    PASSWORD,
    PgConnection,
    _safe_target,
    provision_runtime_access,
)

NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=10)
BEFORE = NOW - timedelta(days=1)
JOB = "11111111-1111-4111-8111-111111111111"
EVIDENCE = "a" * 64
PLAN = UUID("22222222-2222-4222-8222-222222222222")


def _rows() -> dict[str, list[Row]]:
    rows: dict[str, list[Row]] = {name: [] for name in TABLES}
    rows["jobs"].append(
        {
            "id": JOB,
            "user_id": 1,
            "status": "succeeded",
            "created_at": OLD,
            "lease_expires_at": None,
            "has_lease_token": False,
            "payload": {},
            "result": {},
        }
    )
    rows["grocery_evidence"].append(
        {
            "id": EVIDENCE,
            "user_id": 1,
            "snapshot": {"sample": "Synthetic"},
            "created_at": OLD,
        }
    )
    rows["plan_revisions"].append(
        {
            "id": PLAN,
            "user_id": 1,
            "snapshot": {},
            "created_at": OLD,
        }
    )
    return rows


def _manifest(rows: dict[str, list[Row]], **overrides: object) -> Manifest:
    return build_manifest(
        rows,
        owner_id=cast(int, overrides.get("owner_id", 1)),
        before=cast(datetime, overrides.get("before", BEFORE)),
        now=NOW,
        database_id=cast(str, overrides.get("database_id", "b" * 64)),
        owner_status="disabled",
    )


def test_manifest_is_stable_opaque_and_binds_explicit_target() -> None:
    rows = _rows()
    first = _manifest(rows)
    assert first.digest == _manifest(rows).digest
    assert len(first.digest) == 64
    assert first.counts["jobs"] == first.counts["grocery_evidence"] == 1
    assert not first.blockers
    assert first.public()["target_identity"] == "b" * 64
    assert first.public()["owner_id"] == 1
    assert first.public()["before"] == BEFORE.isoformat()
    output = json.dumps(first.public())
    assert JOB not in output and EVIDENCE not in output and "Synthetic" not in output
    assert "backups" in output and "provider_copies" in output
    assert first.digest != _manifest(rows, owner_id=2).digest
    assert first.digest != _manifest(rows, before=BEFORE - timedelta(hours=1)).digest
    assert first.digest != _manifest(rows, database_id="c" * 64).digest
    rows["jobs"][0]["result"] = {"changed": True}
    assert first.digest != _manifest(rows).digest


@pytest.mark.parametrize("created_at", [OLD, NOW])
def test_manifest_non_null_lease_token_without_expiry_blocks(
    created_at: datetime,
) -> None:
    rows = _rows()
    first = _manifest(rows)
    rows["jobs"][0].update({"has_lease_token": True, "created_at": created_at})
    changed = _manifest(rows)
    assert "job_lease" in changed.blockers
    assert changed.counts["jobs"] == 0
    assert changed.digest != first.digest


@pytest.mark.parametrize(
    "table",
    [
        "jobs",
        "plan_proposals",
        "plan_revisions",
        "grocery_evidence",
        "security_intents",
    ],
)
def test_retained_cross_owner_nested_and_direct_references_block(table: str) -> None:
    rows = _rows()
    nested = {"trace": [{"constraints": {"legacy_ref": EVIDENCE}}]}
    retained: dict[str, Row] = {
        "jobs": {
            "id": str(uuid4()),
            "user_id": 2,
            "status": "succeeded",
            "created_at": OLD,
            "payload": {},
            "result": nested,
        },
        "plan_proposals": {
            "id": uuid4(),
            "user_id": 2,
            "status": "pending",
            "created_at": OLD,
            "updated_at": OLD,
            "base_plan_revision_id": PLAN,
            "applied_plan_revision_id": None,
            "operations": [nested],
            "apply_constraints": {"job_id": JOB},
        },
        "plan_revisions": {
            "id": uuid4(),
            "user_id": 2,
            "snapshot": nested,
            "created_at": OLD,
        },
        "grocery_evidence": {
            "id": "d" * 64,
            "user_id": 2,
            "snapshot": nested,
            "created_at": OLD,
        },
        "security_intents": {
            "id": uuid4(),
            "user_id": 2,
            "kind": "cart_confirmation",
            "state": "uncertain",
            "digest": "e" * 64,
            "details": nested,
            "created_at": OLD,
            "updated_at": OLD,
            "expires_at": OLD,
        },
    }
    first = _manifest(rows)
    rows[table].append(retained[table])
    second = _manifest(rows)
    assert "retained_dependency" in second.blockers
    assert first.digest != second.digest
    assert references({"url": f"urn:job:{JOB.upper()}"}, {JOB})
    assert not references({"value": "f" * 64}, {EVIDENCE})


def test_candidate_eligibility_keeps_current_cost_quotas_and_cart_tombstones() -> None:
    rows = _rows()
    rows["model_call_reservations"] = [
        {
            "id": str(uuid4()),
            "job_id": JOB,
            "user_id": 1,
            "utc_day": NOW.date(),
            "started_at": NOW - timedelta(minutes=1),
            "slot_deadline": NOW + timedelta(seconds=1),
            "finished_at": None,
            "status": "in_flight",
        }
    ]
    rows["quota_counters"] = [
        {
            "scope": "user",
            "scope_key": 1,
            "action": "mutation",
            "count": 1,
            "minute_start": NOW,
            "expires_at": NOW + timedelta(minutes=1),
        },
        {
            "scope": "global",
            "scope_key": 0,
            "action": "retailer",
            "count": 1,
            "minute_start": OLD,
            "expires_at": OLD + timedelta(minutes=1),
        },
    ]
    rows["security_intents"] = [
        {
            "id": uuid4(),
            "user_id": 1,
            "kind": "cart_confirmation",
            "state": "uncertain",
            "digest": "e" * 64,
            "details": {},
            "created_at": OLD,
            "updated_at": OLD,
            "expires_at": OLD,
        }
    ]
    manifest = _manifest(rows)
    assert set(manifest.blockers) == {
        "active_provider_reservation",
        "retained_dependency",
        "ambiguous_cart_intent",
    }
    assert all(
        manifest.counts[name] == 0
        for name in (
            "model_call_reservations",
            "quota_counters",
            "security_intents",
        )
    )
    rows["model_call_reservations"][0].update(
        {
            "utc_day": OLD.date(),
            "started_at": OLD,
            "slot_deadline": OLD + timedelta(seconds=60),
        }
    )
    assert _manifest(rows).counts["model_call_reservations"] == 1


def test_manifest_fails_closed_on_workload_shapes_and_future_cutoff() -> None:
    rows = _rows()
    with pytest.raises(RetentionError):
        _manifest(rows, before=NOW + timedelta(seconds=1))
    rows["jobs"][0]["payload"] = ["unknown"]
    with pytest.raises(RetentionError):
        _manifest(rows)
    rows = _rows()
    rows["jobs"] *= MAX_ROWS + 1
    with pytest.raises(RetentionError):
        _manifest(rows)


@pytest.mark.parametrize(
    "args",
    [
        ["preview", "--owner-id", "0", "--before", "not-a-time"],
        ["purge", "--owner-id", "1", "--before", BEFORE.isoformat()],
        ["disable", "--owner-id", "1", "--workspace-id", "private-input"],
        ["preview", "--owner-id", "private-input", "--before", BEFORE.isoformat()],
    ],
)
def test_cli_failures_are_fixed(
    args: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("FEWIA_RETENTION_DATABASE_URL", raising=False)
    assert retention_admin.main(args) == 2
    assert capsys.readouterr().out == '{"error":"operator_retention_refused"}\n'


def test_cli_preview_needs_only_explicit_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = MagicMock(spec=Engine)

    def make_engine(*args: object, **kwargs: object) -> Engine:
        return cast(Engine, engine)

    class PreviewOnly:
        def __init__(self, supplied_engine: Engine) -> None:
            assert supplied_engine is engine

        def preview(self, *, owner_id: int, before: datetime) -> dict[str, object]:
            return _manifest(_rows(), owner_id=owner_id, before=before).public()

    monkeypatch.setenv(
        "FEWIA_RETENTION_DATABASE_URL",
        "postgresql+psycopg://operator@localhost/fewia_eval_retention",
    )
    monkeypatch.delenv("FEWIA_RETENTION_DATABASE_ID", raising=False)
    monkeypatch.setattr(retention_admin.sa, "create_engine", make_engine)
    monkeypatch.setattr(retention_admin, "OperatorRetention", PreviewOnly)
    assert (
        retention_admin.main(
            [
                "preview",
                "--owner-id",
                "1",
                "--before",
                BEFORE.isoformat(),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["target_identity"] == "b" * 64
    assert output["owner_id"] == 1 and output["before"] == BEFORE.isoformat()
    assert "localhost" not in json.dumps(output)
    engine.dispose.assert_called_once_with()


def _module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"retention_test_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade(engine: Engine, *, through: str = "0018", role: str) -> None:
    directory = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    modules = [
        _module(path) for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]_*.py"))
    ]
    pending = {
        str(module.revision): module
        for module in modules
        if str(module.revision) <= through
    }
    applied: set[str | None] = {None}
    with engine.begin() as connection:
        assert re.fullmatch(r"fewia_eval_retention_dba_[0-9a-f]{32}", role)
        connection.execute(sa.text(f'SET LOCAL SESSION AUTHORIZATION "{role}"'))
        connection.execute(
            sa.text(
                "CREATE TABLE public.alembic_version("
                "version_num varchar(32) PRIMARY KEY)"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            while pending:
                ready = [
                    module
                    for module in pending.values()
                    if module.down_revision in applied
                ]
                assert ready, "Migration ancestors are missing. Integrate 0015-0017."
                for module in ready:
                    module.upgrade()
                    applied.add(module.revision)
                    del pending[module.revision]
        connection.execute(
            sa.text(
                "INSERT INTO public.alembic_version(version_num) VALUES (:version)"
            ),
            {"version": through},
        )
    assert through in applied


@dataclass
class Database:
    engine: Engine
    operator_engine: Engine
    service: OperatorRetention
    dba_role: str
    operator_role: str
    owner: int
    workspace: UUID
    before: datetime


@dataclass(frozen=True)
class RetentionTemplate:
    name: str
    dba_role: str


Target = dict[str, str | int]


def _control_engine(options: Target) -> Engine:
    return sa.create_engine(
        "postgresql+psycopg://",
        connect_args=options,
        isolation_level="AUTOCOMMIT",
    )


def _assert_isolated_cluster(connection: sa.Connection) -> None:
    assert connection.scalar(
        sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ), "Disposable retention tests need a test-cluster superuser."
    assert (
        int(cast(str, connection.scalar(sa.text("SHOW server_version_num")))) >= 160000
    ), "Retention role tests need PostgreSQL 16 or later."
    assert all(
        re.fullmatch(r"fewia_eval(?:_[A-Za-z0-9_]+)?", value)
        for value in connection.scalars(
            sa.text(
                "SELECT datname FROM pg_database "
                "WHERE datname NOT IN ('postgres', 'template0', 'template1')"
            )
        )
    ), "Retention tests need an isolated test cluster."
    assert connection.scalar(
        sa.text(
            "SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fewia_app')"
        )
    ), "Retention tests need an absent runtime test role."


def _maintenance_role_missing(connection: sa.Connection) -> bool:
    return (
        connection.scalar(
            sa.text(
                "SELECT NOT EXISTS (SELECT 1 FROM pg_roles "
                "WHERE rolname = 'fewia_maintenance')"
            )
        )
        is True
    )


def _create_role(connection: sa.Connection, role: str, *, createrole: bool) -> None:
    privilege = "CREATEROLE" if createrole else "NOCREATEROLE"
    connection.execute(
        sa.text(
            f'CREATE ROLE "{role}" NOLOGIN NOINHERIT NOSUPERUSER '
            f"NOCREATEDB {privilege} NOREPLICATION NOBYPASSRLS"
        )
    )


def _grant_maintenance_admin(connection: sa.Connection, dba_role: str) -> None:
    connection.execute(
        sa.text(
            f'GRANT fewia_maintenance TO "{dba_role}" '
            "WITH ADMIN TRUE, INHERIT FALSE, SET FALSE"
        )
    )


def _revoke_temporary(engine: Engine, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text(f'REVOKE TEMPORARY ON DATABASE "{name}" FROM PUBLIC')
        )


def _seed_database(engine: Engine) -> tuple[datetime, UUID]:
    with Session(engine) as session, session.begin():
        now = cast(datetime, session.scalar(sa.select(sa.func.clock_timestamp())))
        workspace = uuid4()
        session.execute(
            sa.text(
                "INSERT INTO public.users(id, display_name, workspace_id) "
                "VALUES (1, 'Synthetic retention owner', :workspace), "
                "(2, 'Synthetic retained owner', gen_random_uuid())"
            ),
            {"workspace": workspace},
        )
        session.execute(
            sa.text(
                "INSERT INTO public.jobs "
                "(id, user_id, kind, request_namespace, request_key, "
                "status, payload, created_at) "
                "VALUES (:id, 1, 'agent', 'plan', 'synthetic', "
                "'succeeded', '{}', :old)"
            ),
            {"id": JOB, "old": now - timedelta(days=10)},
        )
        session.execute(
            sa.text(
                "INSERT INTO public.grocery_evidence("
                "id, user_id, snapshot, created_at) "
                "VALUES (:id, 1, CAST(:snapshot AS json), :old)"
            ),
            {
                "id": EVIDENCE,
                "old": now - timedelta(days=10),
                "snapshot": json.dumps({"sample": True}),
            },
        )
    return now, workspace


def _grant_operator(engine: Engine, dba_role: str, operator_role: str) -> None:
    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL SESSION AUTHORIZATION "{dba_role}"'))
        connection.execute(
            sa.text(
                f'GRANT fewia_maintenance TO "{operator_role}" '
                "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
            )
        )


def _operator_engine(target: Target, operator_role: str) -> Engine:
    operator_engine = sa.create_engine("postgresql+psycopg://", connect_args=target)

    @sa.event.listens_for(operator_engine, "connect")
    def authenticate_operator(
        dbapi_connection: object, connection_record: object
    ) -> None:
        driver = cast(PgConnection, dbapi_connection)
        driver.execute(f'SET SESSION AUTHORIZATION "{operator_role}"')
        driver.commit()

    return operator_engine


@pytest.fixture(scope="module")
def retention_template() -> Iterator[RetentionTemplate]:
    """Migrate one template database through 0018 for the whole module."""
    options = _safe_target(require_test_database_url())
    control = _control_engine(options)
    name = f"fewia_eval_retention_template_{uuid4().hex}"
    dba_role = f"fewia_eval_retention_dba_{uuid4().hex}"
    engine: Engine | None = None
    created_maintenance = False
    created_dba = False
    created_database = False
    try:
        with control.connect() as connection:
            _assert_isolated_cluster(connection)
            created_maintenance = _maintenance_role_missing(connection)
            _create_role(connection, dba_role, createrole=True)
            created_dba = True
            if not created_maintenance:
                _grant_maintenance_admin(connection, dba_role)
            connection.execute(sa.text(f'CREATE DATABASE "{name}" OWNER "{dba_role}"'))
            created_database = True
        engine = sa.create_engine(
            "postgresql+psycopg://", connect_args={**options, "dbname": name}
        )
        _revoke_temporary(engine, name)
        _upgrade(engine, through="0018", role=dba_role)
        engine.dispose()
        yield RetentionTemplate(name=name, dba_role=dba_role)
    finally:
        if engine is not None:
            engine.dispose()
        with control.connect() as connection:
            if created_database:
                connection.execute(sa.text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            if created_dba:
                connection.execute(sa.text(f'DROP ROLE "{dba_role}"'))
            if created_maintenance:
                connection.execute(sa.text("DROP ROLE IF EXISTS fewia_maintenance"))
        control.dispose()


@pytest.fixture()
def database(request: pytest.FixtureRequest) -> Iterator[Database]:
    """Clone the migrated template, except for the populated 0017 upgrade case."""
    if getattr(request, "param", None) == "populated_0017":
        yield from _scratch_database(populated_upgrade=True)
    else:
        template = cast(
            RetentionTemplate, request.getfixturevalue("retention_template")
        )
        yield from _cloned_database(template)


@pytest.fixture()
def scratch_database() -> Iterator[Database]:
    """Build a private database from migration 0001 for schema-changing tests."""
    yield from _scratch_database(populated_upgrade=False)


def _cloned_database(template: RetentionTemplate) -> Iterator[Database]:
    options = _safe_target(require_test_database_url())
    control = _control_engine(options)
    name = f"fewia_eval_retention_{uuid4().hex}"
    operator_role = f"fewia_eval_retention_operator_{uuid4().hex}"
    engine: Engine | None = None
    operator_engine: Engine | None = None
    owns_runtime_role = False
    created_operator = False
    created_database = False
    try:
        with control.connect() as connection:
            _assert_isolated_cluster(connection)
            owns_runtime_role = True
            _create_role(connection, operator_role, createrole=False)
            created_operator = True
            connection.execute(
                sa.text(
                    f'CREATE DATABASE "{name}" OWNER "{template.dba_role}" '
                    f'TEMPLATE "{template.name}"'
                )
            )
            created_database = True
        target = {**options, "dbname": name}
        engine = sa.create_engine("postgresql+psycopg://", connect_args=target)
        _revoke_temporary(engine, name)
        now, workspace = _seed_database(engine)
        _grant_operator(engine, template.dba_role, operator_role)
        operator_engine = _operator_engine(target, operator_role)
        yield Database(
            engine=engine,
            operator_engine=operator_engine,
            service=OperatorRetention(operator_engine),
            dba_role=template.dba_role,
            operator_role=operator_role,
            owner=1,
            workspace=workspace,
            before=now - timedelta(days=1),
        )
    finally:
        if operator_engine is not None:
            operator_engine.dispose()
        if engine is not None:
            engine.dispose()
        with control.connect() as connection:
            if created_database:
                connection.execute(sa.text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            if owns_runtime_role:
                connection.execute(sa.text("DROP ROLE IF EXISTS fewia_app"))
            if created_operator:
                connection.execute(sa.text(f'DROP ROLE "{operator_role}"'))
        control.dispose()


def _scratch_database(*, populated_upgrade: bool) -> Iterator[Database]:
    options = _safe_target(require_test_database_url())
    control = _control_engine(options)
    name = f"fewia_eval_retention_{uuid4().hex}"
    dba_role = f"fewia_eval_retention_dba_{uuid4().hex}"
    operator_role = f"fewia_eval_retention_operator_{uuid4().hex}"
    engine: Engine | None = None
    operator_engine: Engine | None = None
    created_role = False
    owns_runtime_role = False
    created_dba = False
    created_operator = False
    created_database = False
    try:
        with control.connect() as connection:
            _assert_isolated_cluster(connection)
            owns_runtime_role = True
            created_role = _maintenance_role_missing(connection)
            _create_role(connection, dba_role, createrole=True)
            created_dba = True
            _create_role(connection, operator_role, createrole=False)
            created_operator = True
            if not created_role:
                _grant_maintenance_admin(connection, dba_role)
            connection.execute(sa.text(f'CREATE DATABASE "{name}" OWNER "{dba_role}"'))
            created_database = True
        target = {**options, "dbname": name}
        engine = sa.create_engine("postgresql+psycopg://", connect_args=target)
        _revoke_temporary(engine, name)
        _upgrade(engine, through="0017" if populated_upgrade else "0018", role=dba_role)
        now, workspace = _seed_database(engine)
        if populated_upgrade:
            migration = _module(
                Path(__file__).resolve().parents[1]
                / "alembic"
                / "versions"
                / "0018_operator_retention.py"
            )
            with engine.begin() as connection:
                connection.execute(
                    sa.text(f'SET LOCAL SESSION AUTHORIZATION "{dba_role}"')
                )
                with Operations.context(MigrationContext.configure(connection)):
                    migration.upgrade()
                connection.execute(
                    sa.text("UPDATE public.alembic_version SET version_num = '0018'")
                )
        _grant_operator(engine, dba_role, operator_role)
        operator_engine = _operator_engine(target, operator_role)
        yield Database(
            engine=engine,
            operator_engine=operator_engine,
            service=OperatorRetention(operator_engine),
            dba_role=dba_role,
            operator_role=operator_role,
            owner=1,
            workspace=workspace,
            before=now - timedelta(days=1),
        )
    finally:
        if operator_engine is not None:
            operator_engine.dispose()
        if engine is not None:
            engine.dispose()
        with control.connect() as connection:
            if created_database:
                connection.execute(sa.text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            if owns_runtime_role:
                connection.execute(sa.text("DROP ROLE IF EXISTS fewia_app"))
            if created_operator:
                connection.execute(sa.text(f'DROP ROLE "{operator_role}"'))
            if created_dba:
                connection.execute(sa.text(f'DROP ROLE "{dba_role}"'))
            if created_role:
                connection.execute(sa.text("DROP ROLE IF EXISTS fewia_maintenance"))
        control.dispose()


def _count(database: Database, table: str) -> int:
    assert table in {*TABLES, "users"}
    with database.engine.connect() as connection:
        return cast(
            int, connection.scalar(sa.text(f"SELECT count(*) FROM public.{table}"))
        )


@pytest.mark.parametrize("database", ["clean", "populated_0017"], indirect=True)
def test_postgres_preview_then_exact_purge_preserves_identity(
    database: Database,
) -> None:
    service, before = database.service, database.before
    first = service.preview(owner_id=1, before=before)
    assert first == service.preview(owner_id=1, before=before)
    with Session(database.engine) as session:
        assert first["target_identity"] == database_identity(session)
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1
    assert not first["blockers"]
    response = service.purge(
        owner_id=1, before=before, digest=cast(str, first["digest"])
    )
    assert response["purged"] is True
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 0
    assert _count(database, "users") == 2


def test_postgres16_creator_membership_is_admin_only(database: Database) -> None:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migration = _module(path / "0018_operator_retention.py")
    held_role = f"fewia_eval_retention_held_{uuid4().hex}"
    with database.engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                sa.text(f'ALTER ROLE fewia_maintenance RENAME TO "{held_role}"')
            )
            connection.execute(
                sa.text(f'SET LOCAL SESSION AUTHORIZATION "{database.dba_role}"')
            )
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT NOT rolsuper AND rolcreaterole FROM pg_roles "
                        "WHERE rolname = current_user"
                    )
                )
                is True
            )
            connection.execute(sa.text(cast(str, migration.ROLE_SQL)))
            membership = connection.execute(
                sa.text(
                    "SELECT m.admin_option, m.inherit_option, m.set_option "
                    "FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid "
                    "JOIN pg_roles u ON u.oid = m.member "
                    "WHERE r.rolname = 'fewia_maintenance' AND u.rolname = current_user"
                )
            ).one()
            assert tuple(membership) == (True, False, False)
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT pg_has_role(current_user, 'fewia_maintenance', 'SET')"
                    )
                )
                is False
            )
            connection.execute(
                sa.text(
                    f'GRANT fewia_maintenance TO "{database.operator_role}" '
                    "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
                )
            )
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(sa.text("SET LOCAL ROLE fewia_maintenance"))
        finally:
            transaction.rollback()


def test_postgres_separate_operator_can_lock_with_only_delete_grant(
    database: Database,
) -> None:
    with pytest.raises(DBAPIError):
        with database.operator_engine.begin() as connection:
            connection.execute(sa.text("SELECT id FROM public.jobs"))
    with database.operator_engine.begin() as connection:
        assert (
            connection.scalar(sa.text("SELECT session_user")) == database.operator_role
        )
        connection.execute(sa.text("SET LOCAL ROLE fewia_maintenance"))
        assert (
            connection.scalar(
                sa.text(
                    "SELECT has_table_privilege(current_user, 'public.jobs', 'DELETE') "
                    "AND NOT has_table_privilege("
                    "current_user, 'public.jobs', 'UPDATE') "
                    "AND NOT has_table_privilege("
                    "current_user, 'public.jobs', 'TRUNCATE')"
                )
            )
            is True
        )
        connection.execute(sa.text(operator_retention._LOCK_SQL))
    with pytest.raises(DBAPIError):
        with database.engine.begin() as connection:
            connection.execute(
                sa.text(f'SET LOCAL SESSION AUTHORIZATION "{database.dba_role}"')
            )
            connection.execute(sa.text("SET LOCAL ROLE fewia_maintenance"))


def test_postgres_copied_database_rejects_original_digest(database: Database) -> None:
    preview = database.service.preview(owner_id=1, before=database.before)
    options = _safe_target(require_test_database_url())
    copied_name = f"fewia_eval_retention_copy_{uuid4().hex}"
    with database.engine.connect() as connection:
        original_name = connection.scalar(sa.text("SELECT current_database()"))
        assert isinstance(original_name, str)
        assert re.fullmatch(r"fewia_eval_retention_[0-9a-f]{32}", original_name)
    database.operator_engine.dispose()
    database.engine.dispose()
    control = sa.create_engine(
        "postgresql+psycopg://",
        connect_args=options,
        isolation_level="AUTOCOMMIT",
    )
    copied_engine: Engine | None = None
    created = False
    try:
        with control.connect() as connection:
            connection.execute(
                sa.text(f'CREATE DATABASE "{copied_name}" TEMPLATE "{original_name}"')
            )
            created = True
            connection.execute(
                sa.text(f'REVOKE TEMPORARY ON DATABASE "{copied_name}" FROM PUBLIC')
            )
        copied_engine = sa.create_engine(
            "postgresql+psycopg://",
            connect_args={**options, "dbname": copied_name},
        )
        service = OperatorRetention(copied_engine)
        copied_preview = service.preview(owner_id=1, before=database.before)
        assert copied_preview["counts"] == preview["counts"]
        assert copied_preview["target_identity"] != preview["target_identity"]
        with pytest.raises(RetentionError):
            service.purge(
                owner_id=1, before=database.before, digest=cast(str, preview["digest"])
            )
        with copied_engine.connect() as connection:
            assert connection.scalar(sa.text("SELECT count(*) FROM public.jobs")) == 1
    finally:
        if copied_engine is not None:
            copied_engine.dispose()
        if created:
            with control.connect() as connection:
                connection.execute(
                    sa.text(f'DROP DATABASE "{copied_name}" WITH (FORCE)')
                )
        control.dispose()


@pytest.mark.parametrize("budget", ["MAX_SCAN_BYTES", "MAX_ROWS"])
def test_postgres_budget_refuses_before_fetching_rows(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    budget: str,
) -> None:
    statements: list[str] = []

    def record(
        connection: sa.Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    sa.event.listen(database.operator_engine, "before_cursor_execute", record)
    monkeypatch.setattr(operator_retention, budget, 0)
    with pytest.raises(RetentionError):
        database.service.preview(owner_id=1, before=database.before)
    assert any("row_bytes" in statement for statement in statements)
    assert not any(statement.startswith('SELECT "id"') for statement in statements)
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1


def test_postgres_owner_row_lock_blocks_status_and_purge(database: Database) -> None:
    preview = database.service.preview(owner_id=1, before=database.before)
    with database.engine.begin() as connection:
        connection.execute(
            sa.text("SELECT id FROM public.users WHERE id = 1 FOR UPDATE")
        )
        with pytest.raises(RetentionError):
            database.service.set_owner_status(
                owner_id=1,
                workspace_id=database.workspace,
                enabled=False,
            )
        with pytest.raises(RetentionError):
            database.service.purge(
                owner_id=1,
                before=database.before,
                digest=cast(str, preview["digest"]),
            )
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1


def test_postgres_null_expiry_with_lease_token_blocks(database: Database) -> None:
    preview = database.service.preview(owner_id=1, before=database.before)
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE public.jobs SET lease_token = 'synthetic-lease', "
                "lease_expires_at = NULL WHERE id = :id"
            ),
            {"id": JOB},
        )
    changed = database.service.preview(owner_id=1, before=database.before)
    assert "job_lease" in cast(list[str], changed["blockers"])
    assert changed["digest"] != preview["digest"]
    with pytest.raises(RetentionError):
        database.service.purge(
            owner_id=1,
            before=database.before,
            digest=cast(str, changed["digest"]),
        )
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1


@pytest.mark.parametrize(
    "failure", ["owner", "cutoff", "invalid", "mutation", "dependency", "database"]
)
def test_postgres_digest_refusals_delete_nothing(
    database: Database, failure: str
) -> None:
    service, before = database.service, database.before
    digest = cast(str, service.preview(owner_id=1, before=before)["digest"])
    owner = 1
    if failure == "owner":
        owner = 2
    elif failure == "cutoff":
        before -= timedelta(hours=1)
    elif failure == "invalid":
        digest = "invalid"
    elif failure == "database":
        with database.engine.begin() as connection:
            connection.execute(
                sa.text(
                    "COMMENT ON FUNCTION public.fewia_retention_schema_supported() "
                    f"IS '{uuid4()}'"
                )
            )
    else:
        with database.engine.begin() as connection:
            if failure == "mutation":
                connection.execute(
                    sa.text(
                        "UPDATE public.jobs SET result = CAST(:result AS json) "
                        "WHERE id = :id"
                    ),
                    {"id": JOB, "result": json.dumps({"changed": True})},
                )
            else:
                connection.execute(
                    sa.text(
                        "INSERT INTO public.jobs "
                        "(id, user_id, kind, request_namespace, request_key, "
                        "status, payload) "
                        "VALUES (:id, 2, 'agent', 'plan', 'retained', 'succeeded', "
                        "CAST(:payload AS json))"
                    ),
                    {
                        "id": str(uuid4()),
                        "payload": json.dumps({"trace": [{"ref": EVIDENCE}]}),
                    },
                )
    with pytest.raises(RetentionError, match="^Operator retention refused.$"):
        service.purge(owner_id=owner, before=before, digest=digest)
    assert _count(database, "jobs") >= 1
    assert _count(database, "grocery_evidence") == 1


def test_postgres_fk_failure_rolls_back_earlier_job_deletion(
    database: Database,
) -> None:
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE public.fewia_retained_fk "
                "(id int PRIMARY KEY, evidence_id text "
                "REFERENCES public.grocery_evidence(id))"
            )
        )
        connection.execute(
            sa.text("INSERT INTO public.fewia_retained_fk VALUES (1, :id)"),
            {"id": EVIDENCE},
        )
    preview = database.service.preview(owner_id=1, before=database.before)
    with pytest.raises(RetentionError):
        database.service.purge(
            owner_id=1,
            before=database.before,
            digest=cast(str, preview["digest"]),
        )
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1


def test_postgres_owner_transition_requires_exact_workspace_and_state(
    database: Database,
) -> None:
    with pytest.raises(RetentionError):
        database.service.set_owner_status(
            owner_id=1, workspace_id=uuid4(), enabled=False
        )
    assert database.service.set_owner_status(
        owner_id=1,
        workspace_id=database.workspace,
        enabled=False,
    ) == {"status": "disabled"}
    with pytest.raises(RetentionError):
        database.service.set_owner_status(
            owner_id=1, workspace_id=database.workspace, enabled=False
        )
    assert database.service.set_owner_status(
        owner_id=1,
        workspace_id=database.workspace,
        enabled=True,
    ) == {"status": "active"}


def test_postgres_claim_under_owner_lock_invalidates_waiting_purge(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = cast(
        str, database.service.preview(owner_id=1, before=database.before)["digest"]
    )
    waiting = Event()
    real_lock = operator_retention._lock_owner

    def wait_lock(session: Session, owner_id: int) -> None:
        waiting.set()
        real_lock(session, owner_id)

    monkeypatch.setattr(operator_retention, "_lock_owner", wait_lock)
    with ThreadPoolExecutor(max_workers=1) as executor:
        with Session(database.engine) as session, session.begin():
            real_lock(session, 1)
            future = executor.submit(
                database.service.purge,
                owner_id=1,
                before=database.before,
                digest=digest,
            )
            assert waiting.wait(2)
            job_id = str(uuid4())
            session.execute(
                sa.text(
                    "INSERT INTO public.jobs "
                    "(id, user_id, kind, request_namespace, request_key, "
                    "status, payload) "
                    "VALUES (:id, 1, 'agent', 'plan', 'new-claim', 'queued', '{}')"
                ),
                {"id": job_id},
            )
            now = cast(datetime, session.scalar(sa.select(sa.func.clock_timestamp())))
            assert claim_job(session, job_id, now=now) is not None
        with pytest.raises(RetentionError):
            future.result(timeout=3)
    assert _count(database, "jobs") == 2
    assert _count(database, "grocery_evidence") == 1


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE public.grocery_evidence SET snapshot = snapshot",
        "UPDATE public.plan_revisions SET snapshot = snapshot",
        "SELECT * FROM public.kroger_customer_tokens",
        "SELECT auth_subject FROM public.users",
        "UPDATE public.users SET display_name = 'Denied'",
        "DELETE FROM public.users",
        "TRUNCATE public.jobs",
    ],
)
def test_postgres_maintenance_acl_and_immutable_updates(
    database: Database,
    statement: str,
) -> None:
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO public.plan_revisions (id, user_id, snapshot) "
                "VALUES (:id, 1, '{}')"
            ),
            {"id": PLAN},
        )
    with pytest.raises(DBAPIError):
        with database.engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL ROLE fewia_maintenance"))
            connection.execute(sa.text(statement))


def test_postgres_immutable_owner_cannot_delete_and_unsafe_acl_refuses(
    database: Database,
) -> None:
    with pytest.raises(DBAPIError):
        with database.engine.begin() as connection:
            connection.execute(sa.text("DELETE FROM public.grocery_evidence"))
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "GRANT SELECT ON public.kroger_customer_tokens TO fewia_maintenance"
            )
        )
    with pytest.raises(RetentionError):
        database.service.preview(owner_id=1, before=database.before)
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1


@pytest.mark.parametrize(
    "unsafe",
    [
        "ALTER ROLE fewia_maintenance LOGIN",
        "GRANT INSERT ON public.jobs TO fewia_maintenance",
        "GRANT CREATE ON SCHEMA public TO fewia_maintenance",
    ],
)
def test_postgres_migration_rejects_unsafe_preexisting_role(
    scratch_database: Database,
    unsafe: str,
) -> None:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migration = _module(path / "0018_operator_retention.py")
    with pytest.raises(DBAPIError):
        with scratch_database.engine.begin() as connection:
            connection.execute(sa.text(unsafe))
            connection.execute(sa.text(cast(str, migration.ROLE_SQL)))
    assert (
        scratch_database.service.preview(owner_id=1, before=scratch_database.before)[
            "blockers"
        ]
        == []
    )


def test_postgres_runtime_boundary_stays_intact(database: Database) -> None:
    with database.engine.begin() as connection:
        driver = cast(PgConnection, connection.connection.driver_connection)
        provision_runtime_access(driver, PASSWORD)
        assert connection.scalar(sa.text(UNSAFE_ROLE_SQL)) is False
        assert connection.scalar(sa.text(UNSAFE_ACCESS_SQL)) is False
    for statement in (
        "SET LOCAL ROLE fewia_maintenance",
        "SELECT public.fewia_retention_schema_supported()",
        "DELETE FROM public.jobs",
        "UPDATE public.users SET status = 'disabled' WHERE id = 1",
        "UPDATE public.grocery_evidence SET snapshot = snapshot",
    ):
        with pytest.raises(DBAPIError):
            with database.engine.begin() as connection:
                connection.execute(sa.text("SET LOCAL SESSION AUTHORIZATION fewia_app"))
                connection.execute(sa.text(statement))


def test_postgres_runtime_membership_path_refuses_retention(database: Database) -> None:
    with database.engine.begin() as connection:
        driver = cast(PgConnection, connection.connection.driver_connection)
        provision_runtime_access(driver, PASSWORD)
        connection.execute(
            sa.text(
                "GRANT fewia_maintenance TO fewia_app "
                "WITH ADMIN FALSE, INHERIT FALSE, SET TRUE"
            )
        )
        assert connection.scalar(sa.text(UNSAFE_ROLE_SQL)) is True
    with pytest.raises(RetentionError):
        database.service.preview(owner_id=1, before=database.before)
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1


def test_postgres_legacy_handoffs_and_pairing_generations_remain(
    database: Database,
) -> None:
    generation = uuid4()
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO public.kroger_owners(user_id, pairing_generation) "
                "VALUES (1, :generation)"
            ),
            {"generation": generation},
        )
        connection.execute(
            sa.text(
                "INSERT INTO public.shopping_handoffs "
                "(id, user_id, request_hash, request_payload) "
                "VALUES (:id, 1, 'synthetic-handoff', '{}')"
            ),
            {"id": str(uuid4())},
        )
        connection.execute(
            sa.text(
                "INSERT INTO public.daily_finance "
                "(user_id, observation_date, total_spending, grocery_spending, "
                "restaurant_spending, transportation_spending, fitness_spending, "
                "discretionary_spending, cash_flow, source) "
                "VALUES (1, current_date, 1, 1, 0, 0, 0, 0, 0, 'synthetic')"
            )
        )
    preview = database.service.preview(owner_id=1, before=database.before)
    database.service.purge(
        owner_id=1,
        before=database.before,
        digest=cast(str, preview["digest"]),
    )
    with database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT pairing_generation FROM public.kroger_owners "
                    "WHERE user_id = 1"
                )
            )
            == generation
        )
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM public.shopping_handoffs"))
            == 1
        )
        assert (
            connection.scalar(sa.text("SELECT count(*) FROM public.daily_finance")) == 1
        )


@pytest.mark.parametrize("current", [False, True])
def test_postgres_model_guard_and_current_cost_dependency(
    database: Database,
    current: bool,
) -> None:
    with database.engine.begin() as connection:
        now = cast(datetime, connection.scalar(sa.select(sa.func.clock_timestamp())))
        started = now if current else now - timedelta(days=10)
        connection.execute(
            sa.text(
                "INSERT INTO public.model_call_reservations "
                "(id, job_id, user_id, attempt, turn, model_id, region, rate_version, "
                "utc_day, reserved_microdollars, status, started_at, slot_deadline) "
                "VALUES (:id, :job, 1, 1, 1, 'synthetic', 'global', 'synthetic', "
                ":day, 1, 'in_flight', :started, :deadline)"
            ),
            {
                "id": str(uuid4()),
                "job": JOB,
                "day": started.date(),
                "started": started,
                "deadline": started + timedelta(seconds=60),
            },
        )
    preview = database.service.preview(owner_id=1, before=database.before)
    if current:
        assert "retained_dependency" in cast(list[str], preview["blockers"])
        with pytest.raises(RetentionError):
            database.service.purge(
                owner_id=1,
                before=database.before,
                digest=cast(str, preview["digest"]),
            )
        assert _count(database, "model_call_reservations") == 1
    else:
        assert cast(dict[str, int], preview["counts"])["model_call_reservations"] == 1
        database.service.purge(
            owner_id=1,
            before=database.before,
            digest=cast(str, preview["digest"]),
        )
        assert _count(database, "model_call_reservations") == 0


def test_postgres_cross_owner_table_write_refuses_without_deadlock(
    database: Database,
) -> None:
    foreign_job = str(uuid4())
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO public.jobs "
                "(id, user_id, kind, request_namespace, request_key, status, payload) "
                "VALUES (:id, 2, 'agent', 'plan', 'foreign-retained', "
                "'succeeded', '{}')"
            ),
            {"id": foreign_job},
        )
    preview = database.service.preview(owner_id=1, before=database.before)
    with database.engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE public.jobs SET result = '{}' WHERE id = :id"),
            {
                "id": foreign_job,
            },
        )
        with pytest.raises(RetentionError):
            database.service.purge(
                owner_id=1,
                before=database.before,
                digest=cast(str, preview["digest"]),
            )
    assert _count(database, "jobs") == 2
    assert _count(database, "grocery_evidence") == 1


def test_postgres_immutable_triggers_reject_owner_updates(database: Database) -> None:
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO public.plan_revisions(id, user_id, snapshot) "
                "VALUES (:id, 1, '{}')"
            ),
            {"id": PLAN},
        )
    for table in ("grocery_evidence", "plan_revisions"):
        with pytest.raises(DBAPIError) as caught:
            with database.engine.begin() as connection:
                connection.execute(
                    sa.text(f"UPDATE public.{table} SET snapshot = snapshot")
                )
        assert getattr(caught.value.orig, "sqlstate", None) != "42501"


def test_postgres_later_schema_version_refuses_retention(
    scratch_database: Database,
) -> None:
    with scratch_database.engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE public.alembic_version SET version_num = '0019'")
        )
    with pytest.raises(RetentionError):
        scratch_database.service.preview(owner_id=1, before=scratch_database.before)
    assert (
        _count(scratch_database, "jobs")
        == _count(scratch_database, "grocery_evidence")
        == 1
    )


def _upgrade_connection_generation(database: Database) -> None:
    migration = _module(
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0019_kroger_connection_generation.py"
    )
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(f'SET LOCAL SESSION AUTHORIZATION "{database.dba_role}"')
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        connection.execute(
            sa.text("UPDATE public.alembic_version SET version_num = '0019'")
        )


def test_postgres_connection_upgrade_preserves_data_and_retention(
    scratch_database: Database,
) -> None:
    database = scratch_database
    pairing, version, intent_id = uuid4(), uuid4(), uuid4()
    cipher = Fernet(Fernet.generate_key())
    access = cipher.encrypt(b"synthetic-access")
    refresh = cipher.encrypt(b"synthetic-refresh")
    guard_sql = sa.text(
        "SELECT oid, proowner, proacl::text, prosecdef, proconfig, provolatile, "
        "prolang, obj_description(oid, 'pg_proc') FROM pg_proc "
        "WHERE oid = 'public.fewia_retention_schema_supported()'::regprocedure"
    )
    with database.engine.begin() as connection:
        driver = cast(PgConnection, connection.connection.driver_connection)
        provision_runtime_access(driver, PASSWORD)
        connection.execute(
            sa.text(
                "INSERT INTO public.kroger_owners(user_id, pairing_generation) "
                "VALUES (1, :pairing)"
            ),
            {"pairing": pairing},
        )
        connection.execute(
            sa.text(
                "INSERT INTO public.kroger_customer_tokens "
                "(user_id, connection_version, access_token, refresh_token, "
                "access_expires_at) VALUES (1, :version, :access, :refresh, "
                "clock_timestamp() + interval '30 minutes')"
            ),
            {"version": version, "access": access, "refresh": refresh},
        )
        connection.execute(
            sa.text(
                "INSERT INTO public.security_intents "
                "(id, user_id, kind, digest, details, state, expires_at) "
                "VALUES (:id, 1, 'oauth_state', :digest, CAST(:details AS json), "
                "'consumed', clock_timestamp() + interval '5 minutes')"
            ),
            {
                "id": intent_id,
                "digest": "b" * 64,
                "details": json.dumps({"pairing_generation": str(pairing)}),
            },
        )
        owner_before = connection.scalar(
            sa.text("SELECT to_jsonb(o) FROM public.kroger_owners o WHERE user_id = 1")
        )
        tokens_before = connection.scalar(
            sa.text("SELECT to_jsonb(t) FROM public.kroger_customer_tokens t")
        )
        intent_before = connection.scalar(
            sa.text("SELECT to_jsonb(i) FROM public.security_intents i")
        )
        guard_before = connection.execute(guard_sql).one()
        acl_before = connection.scalar(
            sa.text(
                "SELECT relacl::text FROM pg_class "
                "WHERE oid = 'kroger_owners'::regclass"
            )
        )
    preview_before = database.service.preview(owner_id=1, before=database.before)
    _upgrade_connection_generation(database)
    preview_after = database.service.preview(owner_id=1, before=database.before)
    assert preview_before["target_identity"] == preview_after["target_identity"]
    assert preview_before["digest"] == preview_after["digest"]
    with database.engine.begin() as connection:
        assert connection.execute(guard_sql).one() == guard_before
        assert (
            connection.scalar(
                sa.text(
                    "SELECT relacl::text FROM pg_class "
                    "WHERE oid = 'kroger_owners'::regclass"
                )
            )
            == acl_before
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT to_jsonb(o) - 'connection_generation' "
                    "FROM public.kroger_owners o WHERE user_id = 1"
                )
            )
            == owner_before
        )
        assert (
            connection.scalar(
                sa.text("SELECT to_jsonb(t) FROM public.kroger_customer_tokens t")
            )
            == tokens_before
        )
        assert (
            connection.scalar(
                sa.text("SELECT to_jsonb(i) FROM public.security_intents i")
            )
            == intent_before
        )
        generation = connection.scalar(
            sa.text(
                "SELECT connection_generation FROM public.kroger_owners "
                "WHERE user_id = 1"
            )
        )
        assert isinstance(generation, UUID)
        connection.execute(sa.text("SET LOCAL ROLE fewia_app"))
        inserted = connection.scalar(
            sa.text(
                "INSERT INTO public.kroger_owners(user_id) VALUES (2) "
                "RETURNING connection_generation"
            )
        )
        assert isinstance(inserted, UUID) and inserted != generation
        assert connection.scalar(sa.text(UNSAFE_ACCESS_SQL)) is False
        connection.execute(sa.text("RESET ROLE"))


def test_postgres_upgraded_retention_rejects_unknown_revision(
    scratch_database: Database,
) -> None:
    database = scratch_database
    _upgrade_connection_generation(database)
    preview = database.service.preview(owner_id=1, before=database.before)
    assert preview["blockers"] == []
    with database.engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE public.alembic_version SET version_num = '0020'")
        )
    with pytest.raises(RetentionError):
        database.service.preview(owner_id=1, before=database.before)
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1


def test_postgres_retention_rejects_expanded_schema_guard(
    scratch_database: Database,
) -> None:
    database = scratch_database
    _upgrade_connection_generation(database)
    with database.engine.begin() as connection:
        connection.execute(
            sa.text(f'SET LOCAL SESSION AUTHORIZATION "{database.dba_role}"')
        )
        connection.execute(
            sa.text(
                """
CREATE OR REPLACE FUNCTION public.fewia_retention_schema_supported() RETURNS boolean
LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = pg_catalog AS $$
LOCK TABLE public.alembic_version IN SHARE MODE NOWAIT;
SELECT count(*) = 1 AND min(version_num) IN ('0018', '0019') FROM public.alembic_version
$$
"""
            )
        )
        assert (
            connection.scalar(
                sa.text("SELECT public.fewia_retention_schema_supported()")
            )
            is True
        )
    with pytest.raises(RetentionError):
        database.service.preview(owner_id=1, before=database.before)
    assert _count(database, "jobs") == _count(database, "grocery_evidence") == 1
