import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import bootstrap_demo, models
from app.db import Base

ENDPOINT = "http://floci:4566"
SECRET = "AKIASECRETVALUE"
TRUSTED = Path("/trusted/infra/floci_bootstrap.py")
SessionFactory = bootstrap_demo.SessionFactory


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
