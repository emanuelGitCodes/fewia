import json
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast
from unittest.mock import MagicMock

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from app import (
    bootstrap_database,
    bootstrap_hosting,
    cloud_database_settings,
    runtime_database_access,
)
from tests import test_runtime_database_access as access_tests

PASSWORD = "A1" * 16
SECRET = "synthetic-private-marker"
ADMIN_PASSWORD = "test%@:/?#[]+ password"
PgConnection = psycopg.Connection[tuple[object, ...]]


@pytest.fixture()
def hosted_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in cloud_database_settings._FORBIDDEN_KEYS:
        monkeypatch.delenv(key, raising=False)
    values = {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": "fewia.example.us-east-1.rds.amazonaws.com",
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_admin",
        "FEWIA_DATABASE_PASSWORD": ADMIN_PASSWORD,
        "FEWIA_APPLICATION_DATABASE_PASSWORD": PASSWORD,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


@dataclass
class Effects:
    bootstrap: MagicMock
    connect: MagicMock
    connection: MagicMock
    provision: MagicMock


@pytest.fixture()
def effects(monkeypatch: pytest.MonkeyPatch) -> Effects:
    connection = MagicMock()
    connection.info.dbname = "fewia"
    connection.__enter__.return_value = connection
    bootstrap = MagicMock(return_value=0)
    connect = MagicMock(return_value=connection)
    provision = MagicMock()
    monkeypatch.setattr(bootstrap_database, "main", bootstrap)
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setattr(runtime_database_access, "provision_runtime_access", provision)
    return Effects(bootstrap, connect, connection, provision)


def assert_status(capsys: pytest.CaptureFixture[str], status: str, stage: str) -> None:
    captured = capsys.readouterr()
    assert (
        captured.out
        == json.dumps({"status": status, "stage": stage}, sort_keys=True) + "\n"
    )
    assert captured.err == ""
    assert SECRET not in captured.out
    assert ADMIN_PASSWORD not in captured.out
    assert PASSWORD not in captured.out


def assert_no_effects(effects: Effects) -> None:
    effects.bootstrap.assert_not_called()
    effects.connect.assert_not_called()
    effects.provision.assert_not_called()
    effects.connection.execute.assert_not_called()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--ru"],
        ["--unknown", SECRET],
        ["--run", SECRET],
        [f"--run={SECRET}"],
        ["--run", "--endpoint", SECRET],
        ["--help", "--unknown", SECRET],
    ],
)
def test_arguments_fail_before_configuration_or_effects(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    effects: Effects,
) -> None:
    configuration = MagicMock(side_effect=AssertionError(SECRET))
    monkeypatch.setattr(bootstrap_hosting, "_configuration", configuration)
    assert bootstrap_hosting.main(argv) == 1
    assert_status(capsys, "failed", "arguments")
    configuration.assert_not_called()
    assert_no_effects(effects)


@pytest.mark.parametrize("argv", [["--help"], ["-h"], ["--run", "--help"]])
def test_help_uses_static_program_and_skips_configuration(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    effects: Effects,
) -> None:
    configuration = MagicMock(side_effect=AssertionError(SECRET))
    monkeypatch.setattr(bootstrap_hosting, "_configuration", configuration)
    monkeypatch.setattr(sys, "argv", [SECRET, *argv])
    assert bootstrap_hosting.main() == 0
    captured = capsys.readouterr()
    assert "python -m app.bootstrap_hosting" in captured.out
    assert "--run" in captured.out
    assert SECRET not in captured.out
    assert captured.err == ""
    configuration.assert_not_called()
    assert_no_effects(effects)


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (None, 0),
        ([], 1),
        (["--help"], 0),
        (["--run", "--help"], 0),
        (["--ru"], 1),
        (["--run", "--unknown"], 1),
    ],
)
def test_fresh_process_has_no_database_imports_or_credential_reads(
    argv: list[str] | None, expected: int
) -> None:
    script = f"""
import builtins
import os
import subprocess
import sys
seen: list[str] = []
original_import = builtins.__import__
def guarded_import(name: str, *args: object, **kwargs: object) -> object:
    if name in ('app.db', 'app.bootstrap_demo'):
        seen.append('import')
        raise AssertionError('private import marker')
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
def forbidden(*args: object, **kwargs: object) -> None:
    seen.append('effect')
    raise AssertionError('private effect marker')
class NoCredentials(dict[str, str]):
    def __getitem__(self, key: str) -> str:
        if key.startswith(('FEWIA_', 'PG')) or key == 'DATABASE_URL':
            seen.append('credential')
            raise AssertionError('private credential marker')
        return super().__getitem__(key)
    def get(self, key: str, default: str | None = None) -> str | None:
        if key.startswith(('FEWIA_', 'PG')) or key == 'DATABASE_URL':
            seen.append('credential')
            raise AssertionError('private credential marker')
        return super().get(key, default)
os.environ = NoCredentials()
subprocess.run = forbidden
subprocess.Popen = forbidden
from app import bootstrap_hosting
code = 0 if {argv!r} is None else bootstrap_hosting.main({argv!r})
assert seen == []
assert 'app.db' not in sys.modules
assert 'app.bootstrap_demo' not in sys.modules
assert code == {expected}
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={"DATABASE_URL": "postgresql+PRIVATE_DRIVER://localhost/fewia_eval_test"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert "private" not in result.stdout


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("FEWIA_DATABASE_MODE", "local"),
        ("FEWIA_DATABASE_MODE", None),
        ("FEWIA_DATABASE_HOST", None),
        ("FEWIA_DATABASE_HOST", "localhost"),
        ("FEWIA_DATABASE_NAME", "fewia_eval_test"),
        ("FEWIA_DATABASE_USER", "fewia_app"),
        ("FEWIA_DATABASE_USER", "Fewia_admin"),
        ("FEWIA_DATABASE_PASSWORD", None),
        ("FEWIA_DATABASE_PASSWORD", SECRET + "\n"),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", None),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", ""),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", "A" * 31),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", "A" * 33),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", "A" * 31 + "_"),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", "é" * 32),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", "Ａ" * 32),
        ("FEWIA_APPLICATION_DATABASE_PASSWORD", "A" * 31 + "\n"),
        ("DATABASE_URL", SECRET),
        ("PGHOST", SECRET),
    ],
)
def test_invalid_configuration_has_no_database_effects(
    key: str,
    value: str | None,
    hosted_environment: None,
    effects: Effects,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if value is None:
        monkeypatch.delenv(key)
    else:
        monkeypatch.setenv(key, value)
    assert bootstrap_hosting.main(["--run"]) == 1
    assert_status(capsys, "failed", "configuration")
    assert_no_effects(effects)


def test_local_mode_without_cloud_fields_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    effects: Effects,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("FEWIA_DATABASE_MODE", "local")
    for key in cloud_database_settings._CLOUD_FIELDS:
        monkeypatch.delenv(key, raising=False)
    assert bootstrap_hosting.main(["--run"]) == 1
    assert_status(capsys, "failed", "configuration")
    assert_no_effects(effects)


@pytest.mark.parametrize(
    "url",
    [
        None,
        make_url("postgresql://fewia_app@localhost/fewia"),
        make_url("postgresql://fewia_admin@localhost/other"),
    ],
)
def test_configuration_rechecks_cloud_identity(
    url: object,
    monkeypatch: pytest.MonkeyPatch,
    effects: Effects,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cloud_database_settings, "cloud_database_url", lambda: url)
    assert bootstrap_hosting.main(["--run"]) == 1
    assert_status(capsys, "failed", "configuration")
    assert_no_effects(effects)


def test_success_preserves_tls_password_and_timeout_parameters(
    hosted_environment: None, effects: Effects, capsys: pytest.CaptureFixture[str]
) -> None:
    def bootstrap(argv: list[str]) -> int:
        assert argv == ["--run"]
        effects.connect.assert_not_called()
        effects.provision.assert_not_called()
        print(SECRET)
        print(SECRET, file=sys.stderr)
        return 0

    effects.bootstrap.side_effect = bootstrap
    assert bootstrap_hosting.main(["--run"]) == 0
    assert_status(capsys, "ok", "complete")
    effects.bootstrap.assert_called_once_with(["--run"])
    conninfo = effects.connect.call_args.args[0]
    url = make_url(conninfo)
    assert url.drivername == "postgresql"
    assert url.username == "fewia_admin"
    assert url.password == ADMIN_PASSWORD
    assert url.host == "fewia.example.us-east-1.rds.amazonaws.com"
    assert url.database == "fewia"
    assert url.port == 5432
    assert url.query == {
        "sslmode": "verify-full",
        "sslrootcert": "/app/infra/rds/us-east-1-bundle.pem",
    }
    assert "%25" in conninfo
    assert effects.connect.call_args.kwargs == {
        "autocommit": True,
        "connect_timeout": 10,
        "options": "-c statement_timeout=30000 -c lock_timeout=5000",
    }
    assert access_tests.statements(effects.connection) == [
        'REVOKE CREATE, TEMPORARY ON DATABASE "fewia" FROM PUBLIC',
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    ]
    effects.provision.assert_called_once_with(effects.connection, PASSWORD)
    effects.connection.transaction.assert_called_once_with()
    effects.connection.transaction.return_value.__exit__.assert_called_once_with(
        None, None, None
    )


@pytest.mark.parametrize("result", [1, -9, 130])
def test_migration_or_seed_failure_skips_connection_and_permissions(
    result: int,
    hosted_environment: None,
    effects: Effects,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def bootstrap(argv: list[str]) -> int:
        print(SECRET)
        return result

    effects.bootstrap.side_effect = bootstrap
    assert bootstrap_hosting.main(["--run"]) == (130 if result == 130 else 1)
    assert_status(capsys, "interrupted" if result == 130 else "failed", "database")
    effects.connect.assert_not_called()
    effects.provision.assert_not_called()


@pytest.mark.parametrize(
    "operation", ["configuration", "bootstrap", "connect", "provision"]
)
@pytest.mark.parametrize("interrupt", [False, True])
def test_failures_are_static_and_interrupts_preserve_exit_code(
    operation: str,
    interrupt: bool,
    hosted_environment: None,
    effects: Effects,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = KeyboardInterrupt(SECRET) if interrupt else RuntimeError(SECRET)
    failure.__cause__ = ValueError(ADMIN_PASSWORD)
    if operation == "configuration":
        monkeypatch.setattr(
            bootstrap_hosting, "_configuration", MagicMock(side_effect=failure)
        )
    else:
        getattr(effects, operation).side_effect = failure
    assert bootstrap_hosting.main(["--run"]) == (130 if interrupt else 1)
    stage = {
        "configuration": "configuration",
        "bootstrap": "database",
        "connect": "database",
        "provision": "permissions",
    }[operation]
    assert_status(capsys, "interrupted" if interrupt else "failed", stage)
    if operation in {"configuration", "bootstrap"}:
        effects.connect.assert_not_called()
    if operation != "provision":
        effects.provision.assert_not_called()
    else:
        assert effects.connection.transaction.return_value.__exit__.call_args.args[
            0
        ] is type(failure)


def test_permission_helper_quotes_database_identifier_and_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connection.info.dbname = 'fewia_eval_"; DROP DATABASE other; --'
    provision = MagicMock(side_effect=RuntimeError(SECRET))
    monkeypatch.setattr(runtime_database_access, "provision_runtime_access", provision)
    with pytest.raises(RuntimeError):
        bootstrap_hosting._permissions(cast(PgConnection, connection), PASSWORD)
    assert access_tests.statements(connection) == [
        "REVOKE CREATE, TEMPORARY ON DATABASE "
        '"fewia_eval_""; DROP DATABASE other; --" FROM PUBLIC',
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    ]
    provision.assert_called_once_with(connection, PASSWORD)
    assert (
        connection.transaction.return_value.__exit__.call_args.args[0] is RuntimeError
    )


@pytest.mark.parametrize("statement", [1, 2])
@pytest.mark.parametrize("interrupt", [False, True])
def test_hardening_failure_skips_role_work_and_rolls_back(
    statement: int,
    interrupt: bool,
    hosted_environment: None,
    effects: Effects,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = KeyboardInterrupt(SECRET) if interrupt else RuntimeError(SECRET)
    effects.connection.execute.side_effect = [None] * (statement - 1) + [failure]
    assert bootstrap_hosting.main(["--run"]) == (130 if interrupt else 1)
    assert_status(capsys, "interrupted" if interrupt else "failed", "permissions")
    effects.provision.assert_not_called()
    assert effects.connection.execute.call_count == statement
    assert effects.connection.transaction.return_value.__exit__.call_args.args[
        0
    ] is type(failure)


@pytest.fixture()
def admin() -> Iterator[PgConnection]:
    yield from access_tests.admin.__wrapped__()


def _grant_public_setup_access(connection: PgConnection) -> None:
    connection.execute(
        sql.SQL("GRANT CONNECT, CREATE, TEMPORARY ON DATABASE {} TO PUBLIC").format(
            sql.Identifier(connection.info.dbname)
        )
    )
    connection.execute("GRANT CREATE, USAGE ON SCHEMA public TO PUBLIC")


def test_postgres_hosted_step_hardens_public_and_preserves_rows_and_other_acls(
    admin: PgConnection,
) -> None:
    _grant_public_setup_access(admin)
    admin.execute(
        "INSERT INTO users (id, display_name) VALUES (987654321, 'Hosted test')"
    )
    admin.execute("CREATE ROLE fewia_eval_member NOLOGIN")
    admin.execute("GRANT SELECT ON users TO fewia_eval_member WITH GRANT OPTION")
    admin.execute("GRANT UPDATE (display_name) ON users TO fewia_eval_member")
    admin.execute("GRANT USAGE ON SCHEMA public TO fewia_eval_member")
    admin.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO fewia_eval_member")
    admin.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO fewia_eval_member").format(
            sql.Identifier(admin.info.dbname)
        )
    )
    admin.execute("GRANT SELECT ON public.users TO PUBLIC")
    before, rows = access_tests._catalog(admin), access_tests._rows(admin)
    other = access_tests._other_role_acl(admin)
    with pytest.raises(runtime_database_access.RuntimeDatabaseAccessError):
        runtime_database_access.provision_runtime_access(admin, PASSWORD)
    assert access_tests._catalog(admin) == before
    recording = access_tests.RecordingConnection(admin)
    for _ in range(2):
        bootstrap_hosting._permissions(cast(PgConnection, recording), PASSWORD)
        access_tests._assert_privileges(admin)
        access_tests._assert_password(admin, PASSWORD)
        assert access_tests._rows(admin) == rows
        assert access_tests._other_role_acl(admin) == other
        assert admin.execute(
            "SELECT has_database_privilege('fewia_eval_member', current_database(), "
            "'CONNECT'), has_schema_privilege('fewia_eval_member', 'public', 'USAGE')"
        ).fetchone() == (True, True)
    public = admin.execute(
        "SELECT p.privilege_type FROM pg_database d CROSS JOIN LATERAL "
        "aclexplode(d.datacl) p WHERE d.datname = current_database() "
        "AND p.grantee = 0 ORDER BY 1"
    ).fetchall()
    assert public == [("CONNECT",)]
    assert admin.execute(
        "SELECT p.privilege_type FROM pg_namespace n CROSS JOIN LATERAL "
        "aclexplode(n.nspacl) p WHERE n.nspname = 'public' AND p.grantee = 0"
    ).fetchall() == [("USAGE",)]
    assert admin.execute(
        "SELECT p.privilege_type FROM pg_class c CROSS JOIN LATERAL "
        "aclexplode(c.relacl) p WHERE c.oid = 'public.users'::regclass "
        "AND p.grantee = 0"
    ).fetchall() == [("SELECT",)]
    assert (
        sum(s.startswith('CREATE ROLE "fewia_app"') for s in recording.statements) == 1
    )


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["policy", "late_sql", "interrupt"])
def test_postgres_permission_failure_rolls_back_public_and_role_changes(
    admin: PgConnection,
    existing: bool,
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if existing:
        runtime_database_access.provision_runtime_access(admin, PASSWORD)
    _grant_public_setup_access(admin)
    if failure == "policy":
        admin.execute("GRANT UPDATE ON public.grocery_evidence TO PUBLIC")
    before, rows = access_tests._catalog(admin), access_tests._rows(admin)
    recording = access_tests.RecordingConnection(admin, fail=failure == "late_sql")
    if failure == "interrupt":

        def interrupted(connection: PgConnection, password: str) -> None:
            connection.execute("CREATE ROLE fewia_eval_member NOLOGIN")
            raise KeyboardInterrupt(SECRET)

        monkeypatch.setattr(
            runtime_database_access, "provision_runtime_access", interrupted
        )
    expected = (
        KeyboardInterrupt
        if failure == "interrupt"
        else runtime_database_access.RuntimeDatabaseAccessError
    )
    with pytest.raises(expected):
        bootstrap_hosting._permissions(cast(PgConnection, recording), "B2" * 16)
    assert recording.statements[:2] == [
        f'REVOKE CREATE, TEMPORARY ON DATABASE "{admin.info.dbname}" FROM PUBLIC',
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    ]
    assert access_tests._catalog(admin) == before
    assert access_tests._rows(admin) == rows
    assert (
        admin.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = 'fewia_eval_member'"
        ).fetchone()
        is None
    )
