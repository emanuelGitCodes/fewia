import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import psycopg
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import bootstrap_demo, models
from app.db import Base

ENDPOINT = "http://floci:4566"
SECRET = "AKIASECRETVALUE"
TRUSTED = Path("/trusted/infra/floci_bootstrap.py")
SessionFactory = bootstrap_demo.SessionFactory


@pytest.fixture(autouse=True)
def isolated_local_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "FEWIA_LOCAL_ADMIN_PASSWORD_FILE",
        "FEWIA_LOCAL_DATABASE_PASSWORD_FILE",
        "FEWIA_LOCAL_BOOTSTRAP_DATABASE",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


class Recorder:
    def __init__(self, codes: Sequence[int] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.codes = list(codes) if codes is not None else [0]
        self.index = 0

    def __call__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> SimpleNamespace:
        self.calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout})
        code = self.codes[min(self.index, len(self.codes) - 1)]
        self.index += 1
        return SimpleNamespace(returncode=code, stdout=SECRET, stderr=SECRET)


def sqlite_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def noop_wait(seconds: float) -> None:
    del seconds


def last_status(output: str) -> dict[str, str]:
    payload = json.loads(output.strip().splitlines()[-1])
    assert isinstance(payload, dict)
    return {"status": str(payload["status"]), "stage": str(payload["stage"])}


def invoke(
    recorder: Recorder,
    factory: SessionFactory,
    *,
    endpoint: str = ENDPOINT,
    wait: bootstrap_demo.WaitFn = noop_wait,
    infra_path: Path = TRUSTED,
) -> int:
    return bootstrap_demo.main(
        ["--endpoint", endpoint],
        runner=cast(bootstrap_demo.CommandRunner, recorder),
        factory=factory,
        wait=wait,
        infra_path=infra_path,
    )


def test_rejects_non_local_endpoint_before_effects(
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder()
    factory = sqlite_factory()
    waits: list[float] = []

    def boom() -> Session:
        raise AssertionError("seed ran before endpoint validation")

    code = bootstrap_demo.main(
        ["--endpoint", "https://sqs.us-east-1.amazonaws.com"],
        runner=cast(bootstrap_demo.CommandRunner, recorder),
        factory=boom,
        wait=lambda seconds: waits.append(seconds),
    )
    captured = capsys.readouterr()
    assert code == 1
    assert last_status(captured.out) == {"status": "failed", "stage": "endpoint"}
    assert recorder.calls == []
    assert waits == []
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(models.User)) == 0


def test_runs_migrate_before_seed_and_floci() -> None:
    events: list[str] = []
    inner = sqlite_factory()

    def tracking_factory() -> Session:
        events.append("seed")
        return inner()

    def runner(
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> SimpleNamespace:
        del cwd, timeout
        if list(argv[1:3]) == ["-m", "alembic"]:
            events.append("migrate")
        else:
            events.append("floci")
        return SimpleNamespace(returncode=0)

    code = bootstrap_demo.main(
        ["--endpoint", ENDPOINT],
        runner=cast(bootstrap_demo.CommandRunner, runner),
        factory=tracking_factory,
        wait=noop_wait,
        infra_path=TRUSTED,
    )
    assert code == 0
    assert events == ["migrate", "seed", "floci"]


def test_seeds_user_one_when_absent() -> None:
    factory = sqlite_factory()
    code = invoke(Recorder(), factory, endpoint="http://127.0.0.1:4566")
    assert code == 0
    with factory() as session:
        user = session.get(models.User, 1)
        assert user is not None
        assert user.display_name == "FEWIA demo"
        assert session.scalar(select(func.count()).select_from(models.User)) == 1


def test_seed_is_idempotent_and_does_not_overwrite() -> None:
    factory = sqlite_factory()
    with factory() as session:
        session.add(models.User(id=1, display_name="Existing owner"))
        session.commit()
    runner = Recorder()
    first = invoke(runner, factory, endpoint="http://localhost:4566")
    second = invoke(runner, factory, endpoint="http://localhost:4566")
    assert first == 0
    assert second == 0
    with factory() as session:
        user = session.get(models.User, 1)
        assert user is not None
        assert user.display_name == "Existing owner"
        assert session.scalar(select(func.count()).select_from(models.User)) == 1


def test_child_commands_use_argument_lists_timeouts_and_trusted_paths() -> None:
    recorder = Recorder()
    code = invoke(recorder, sqlite_factory(), infra_path=TRUSTED)
    assert code == 0
    assert recorder.calls[0]["argv"] == [
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        "head",
    ]
    assert recorder.calls[0]["cwd"] == bootstrap_demo.BACKEND_BASE
    assert recorder.calls[0]["timeout"] == 30
    assert recorder.calls[1]["argv"] == [
        sys.executable,
        str(TRUSTED),
        "--endpoint",
        ENDPOINT,
    ]
    assert recorder.calls[1]["timeout"] == 30


def test_infra_script_prefers_backend_copy_then_repo_root(tmp_path: Path) -> None:
    docker_base = tmp_path / "docker"
    docker_script = docker_base / "infra" / "floci_bootstrap.py"
    docker_script.parent.mkdir(parents=True)
    docker_script.write_text("# docker\n", encoding="utf-8")
    host_base = tmp_path / "backend"
    host_base.mkdir()
    host_script = tmp_path / "infra" / "floci_bootstrap.py"
    host_script.parent.mkdir()
    host_script.write_text("# host\n", encoding="utf-8")
    assert bootstrap_demo.resolve_infra_script(docker_base) == docker_script
    assert bootstrap_demo.resolve_infra_script(host_base) == host_script


def test_floci_retries_three_times_with_bounded_wait() -> None:
    recorder = Recorder(codes=[0, 1, 1, 1])
    waits: list[float] = []
    code = invoke(
        recorder,
        sqlite_factory(),
        wait=lambda seconds: waits.append(seconds),
    )
    assert code == 1
    assert waits == [1.0, 1.0]
    migrate_calls = [call for call in recorder.calls if "alembic" in str(call["argv"])]
    floci_calls = [
        call for call in recorder.calls if "floci_bootstrap.py" in str(call["argv"])
    ]
    assert len(migrate_calls) == 1
    assert len(floci_calls) == 3


def test_floci_succeeds_on_third_attempt() -> None:
    recorder = Recorder(codes=[0, 1, 1, 0])
    waits: list[float] = []
    code = invoke(
        recorder,
        sqlite_factory(),
        wait=lambda seconds: waits.append(seconds),
    )
    assert code == 0
    assert waits == [1.0, 1.0]


def test_migrate_failure_skips_seed_and_floci() -> None:
    recorder = Recorder(codes=[1])
    factory = sqlite_factory()
    code = invoke(recorder, factory)
    assert code == 1
    assert len(recorder.calls) == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(models.User)) == 0


def test_static_failure_stdout_omits_secrets_and_chains(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = invoke(Recorder(codes=[1]), sqlite_factory())
    captured = capsys.readouterr()
    assert code == 1
    assert last_status(captured.out) == {"status": "failed", "stage": "migrate"}
    assert SECRET not in captured.out
    assert SECRET not in captured.err
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_timeout_becomes_static_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def runner(
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: int = 30,
    ) -> SimpleNamespace:
        del cwd
        raise subprocess.TimeoutExpired(cmd=list(argv), timeout=timeout)

    code = bootstrap_demo.main(
        ["--endpoint", ENDPOINT],
        runner=cast(bootstrap_demo.CommandRunner, runner),
        factory=sqlite_factory(),
        wait=noop_wait,
        infra_path=TRUSTED,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert last_status(captured.out) == {"status": "failed", "stage": "migrate"}
    assert "TimeoutExpired" not in captured.out


@pytest.mark.parametrize("failure_stage", [None, "connect", "provision"])
def test_admin_bootstrap_orders_seed_and_runtime_provision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure_stage: str | None,
) -> None:
    from app import runtime_database_access

    admin, runtime = tmp_path / "admin", tmp_path / "runtime"
    admin.write_text("A" * 32)
    runtime.write_text("R" * 32)
    for path in (admin, runtime):
        path.chmod(0o600)
    monkeypatch.setenv("FEWIA_LOCAL_ADMIN_PASSWORD_FILE", str(admin))
    monkeypatch.setenv("FEWIA_LOCAL_DATABASE_PASSWORD_FILE", str(runtime))
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    events: list[str] = []
    admin_urls: list[URL] = []
    connection = MagicMock(spec=psycopg.Connection)
    connection.__enter__.return_value = connection
    dispose = MagicMock(wraps=engine.dispose)

    def engine_factory(url: URL, *, hide_parameters: bool) -> Engine:
        assert url.username == "fewia"
        assert url.password == "A" * 32
        assert hide_parameters is True
        admin_urls.append(url)
        return engine

    def connect(
        conninfo: str, *, autocommit: bool
    ) -> psycopg.Connection[tuple[object, ...]]:
        events.append("connect")
        assert conninfo == admin_urls[0].set(drivername="postgresql").render_as_string(
            hide_password=False
        )
        assert autocommit is True
        with Session(engine) as session:
            assert session.scalar(select(models.User.id)) == 1
        if failure_stage == "connect":
            raise psycopg.OperationalError(SECRET)
        return cast(psycopg.Connection[tuple[object, ...]], connection)

    def provision(
        runtime_connection: psycopg.Connection[tuple[object, ...]], password: str
    ) -> None:
        events.append("provision")
        assert runtime_connection is connection
        assert password == "R" * 32
        if failure_stage == "provision":
            raise ValueError(SECRET)

    def runner(
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: int = 30,
        env: dict[str, str] | None = None,
    ) -> SimpleNamespace:
        del cwd, timeout
        if "alembic" in argv:
            events.append("migrate")
            assert env is not None
            assert env["FEWIA_LOCAL_BOOTSTRAP_DATABASE"] == "1"
            assert "A" * 32 not in repr(env)
            assert "R" * 32 not in repr(env)
        else:
            events.append("floci")
            assert env is None
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(bootstrap_demo, "create_engine", engine_factory)
    monkeypatch.setattr(bootstrap_demo.psycopg, "connect", connect)
    monkeypatch.setattr(engine, "dispose", dispose)
    monkeypatch.setattr(runtime_database_access, "provision_runtime_access", provision)
    assert bootstrap_demo.main(
        ["--endpoint", ENDPOINT], runner=runner, wait=noop_wait, infra_path=TRUSTED
    ) == int(failure_stage is not None)
    expected = ["migrate", "connect"]
    if failure_stage != "connect":
        expected.append("provision")
        connection.__exit__.assert_called_once()
    else:
        connection.__enter__.assert_not_called()
    if failure_stage is None:
        expected.append("floci")
    assert events == expected
    dispose.assert_called_once_with()
    assert "FEWIA_LOCAL_BOOTSTRAP_DATABASE" not in os.environ
    captured = capsys.readouterr()
    assert last_status(captured.out) == {
        "status": "ok" if failure_stage is None else "failed",
        "stage": "complete" if failure_stage is None else "runtime-access",
    }
    assert SECRET not in captured.out + captured.err
    assert "A" * 32 not in captured.out + captured.err
    assert "R" * 32 not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err


def test_missing_admin_file_fails_before_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FEWIA_LOCAL_ADMIN_PASSWORD_FILE", str(tmp_path / "absent"))
    recorder = Recorder()
    assert invoke(recorder, sqlite_factory()) == 1
    assert recorder.calls == []
