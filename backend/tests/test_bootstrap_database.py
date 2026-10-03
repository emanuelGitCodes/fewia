import importlib
import json
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import bootstrap_database, bootstrap_demo, models
from app.db import Base

SECRET = "bootstrap-secret-marker"
DRIVER_MARKER = "SYNTHETIC_PRIVATE_DRIVER"
MALFORMED_DATABASE_URL = (
    f"postgresql+{DRIVER_MARKER}://fewia:dummy@localhost/fewia_eval_probe"
)


class Recorder:
    def __init__(self, code: int = 0, failure: BaseException | None = None) -> None:
        self.code = code
        self.failure = failure
        self.calls: list[tuple[list[str], Path | None, int]] = []

    def __call__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        timeout: int = bootstrap_demo.COMMAND_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((list(argv), cwd, timeout))
        if self.failure is not None:
            raise self.failure
        return subprocess.CompletedProcess(
            list(argv), self.code, stdout=SECRET.encode(), stderr=SECRET.encode()
        )


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()


def invoke(
    recorder: Recorder,
    factory: bootstrap_demo.SessionFactory,
    argv: Sequence[str] | None = ("--run",),
) -> int:
    return bootstrap_database.main(
        argv, runner=cast(bootstrap_demo.CommandRunner, recorder), factory=factory
    )


def assert_status(
    capsys: pytest.CaptureFixture[str],
    status: str,
    stage: str,
) -> None:
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": status, "stage": stage}
    assert captured.out.count("\n") == 1
    assert SECRET not in captured.out
    assert captured.err == ""


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
def test_requires_exact_opt_in_before_effects(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder()
    sessions: list[str] = []

    def forbidden_factory() -> Session:
        sessions.append("seed")
        raise AssertionError(SECRET)

    assert invoke(recorder, forbidden_factory, argv) == 1
    assert_status(capsys, "failed", "arguments")
    assert recorder.calls == []
    assert sessions == []


@pytest.mark.parametrize("argv", [["--help"], ["-h"], ["--run", "--help"]])
def test_help_has_no_effects(
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder = Recorder()
    sessions: list[str] = []

    def forbidden_factory() -> Session:
        sessions.append("seed")
        raise AssertionError(SECRET)

    monkeypatch.setattr(sys, "argv", [SECRET, *argv])
    assert invoke(recorder, forbidden_factory, None) == 0
    captured = capsys.readouterr()
    assert "python -m app.bootstrap_database" in captured.out
    assert "--run" in captured.out
    assert SECRET not in captured.out
    assert captured.err == ""
    assert recorder.calls == []
    assert sessions == []


def test_success_runs_only_migration_before_seed(
    factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder()

    def tracking_factory() -> Session:
        assert recorder.calls == [
            (
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                bootstrap_demo.BACKEND_BASE,
                bootstrap_demo.COMMAND_TIMEOUT_SECONDS,
            )
        ]
        return factory()

    assert invoke(recorder, tracking_factory) == 0
    assert_status(capsys, "ok", "complete")
    assert len(recorder.calls) == 1
    with factory() as session:
        user = session.get(models.User, 1)
        assert user is not None
        assert user.display_name == "FEWIA demo"


def test_default_runner_captures_output_without_shell_or_environment_override(
    factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(
        argv: Sequence[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append((list(argv), kwargs))
        return subprocess.CompletedProcess(
            list(argv), 0, stdout=SECRET.encode(), stderr=SECRET.encode()
        )

    monkeypatch.setenv("DATABASE_URL", SECRET)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("app.db.SessionLocal", factory)
    assert bootstrap_database.main(["--run"]) == 0
    assert_status(capsys, "ok", "complete")
    assert calls == [
        (
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            {
                "cwd": bootstrap_demo.BACKEND_BASE,
                "timeout": bootstrap_demo.COMMAND_TIMEOUT_SECONDS,
                "capture_output": True,
                "check": False,
                "shell": False,
            },
        )
    ]


@pytest.mark.parametrize(
    "recorder",
    [
        Recorder(code=1),
        Recorder(code=-9),
        Recorder(
            failure=subprocess.TimeoutExpired(
                cmd=[SECRET], timeout=30, output=SECRET, stderr=SECRET
            )
        ),
        Recorder(failure=OSError(SECRET)),
        Recorder(failure=RuntimeError(SECRET)),
    ],
)
def test_migration_failure_hides_output_and_skips_seed(
    recorder: Recorder, capsys: pytest.CaptureFixture[str]
) -> None:
    sessions: list[str] = []

    def forbidden_factory() -> Session:
        sessions.append("seed")
        raise AssertionError(SECRET)

    assert invoke(recorder, forbidden_factory) == 1
    assert_status(capsys, "failed", "migrate")
    assert len(recorder.calls) == 1
    assert sessions == []


@pytest.mark.parametrize(
    "failure,code,status,expected_events",
    [
        (RuntimeError(SECRET), 1, "failed", ["rollback", "close"]),
        (KeyboardInterrupt(SECRET), 130, "interrupted", ["close"]),
    ],
)
def test_seed_failure_rolls_back_and_closes(
    failure: BaseException,
    code: int,
    status: str,
    expected_events: list[str],
    factory: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []

    class FailingSession(Session):
        def commit(self) -> None:
            self.flush()
            raise failure

        def rollback(self) -> None:
            events.append("rollback")
            super().rollback()

        def close(self) -> None:
            events.append("close")
            super().close()

    with factory() as session:
        bind = session.get_bind()
    failing_factory = sessionmaker(bind=bind, class_=FailingSession)
    recorder = Recorder()
    assert invoke(recorder, failing_factory) == code
    assert_status(capsys, status, "seed")
    assert events == expected_events
    assert len(recorder.calls) == 1
    with factory() as session:
        assert session.get(models.User, 1) is None


def test_session_creation_failure_is_static(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failing_factory() -> Session:
        raise RuntimeError(SECRET)

    assert invoke(Recorder(), failing_factory) == 1
    assert_status(capsys, "failed", "seed")


@pytest.mark.parametrize("existing_name", [None, "Existing owner"])
def test_repeated_execution_preserves_users(
    existing_name: str | None,
    factory: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with factory() as session:
        session.add(models.User(id=7, display_name="Unrelated owner"))
        if existing_name is not None:
            session.add(models.User(id=1, display_name=existing_name))
        session.commit()
    recorder = Recorder()
    for _ in range(2):
        assert invoke(recorder, factory) == 0
        assert_status(capsys, "ok", "complete")
    assert len(recorder.calls) == 2
    with factory() as session:
        demo = session.get(models.User, 1)
        unrelated = session.get(models.User, 7)
        assert demo is not None
        assert demo.display_name == (existing_name or "FEWIA demo")
        assert unrelated is not None
        assert unrelated.display_name == "Unrelated owner"
        assert session.scalar(select(func.count()).select_from(models.User)) == 2


@pytest.mark.parametrize("stage", ["migrate", "seed"])
def test_interrupt_returns_static_status(
    stage: str, factory: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    recorder = Recorder(
        failure=KeyboardInterrupt(SECRET) if stage == "migrate" else None
    )
    sessions: list[str] = []

    def interrupted_factory() -> Session:
        sessions.append("seed")
        raise KeyboardInterrupt(SECRET)

    assert invoke(recorder, interrupted_factory) == 130
    assert_status(capsys, "interrupted", stage)
    assert len(recorder.calls) == 1
    assert sessions == ([] if stage == "migrate" else ["seed"])
    with factory() as session:
        assert session.get(models.User, 1) is None


def test_import_does_not_migrate_or_open_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append("effect")
        raise AssertionError(SECRET)

    with monkeypatch.context() as patches:
        patches.setattr(bootstrap_demo, "run_command", forbidden)
        patches.setattr(bootstrap_demo, "seed_demo_user", forbidden)
        patches.setattr("app.db.SessionLocal", forbidden)
        importlib.reload(bootstrap_database)
    importlib.reload(bootstrap_database)
    assert calls == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize("argv", [None, [], ["--help"], ["-h"], ["--run", "--help"]])
def test_fresh_process_skips_database_imports_and_effects(
    argv: list[str] | None,
) -> None:
    script = f"""
import subprocess
import sys

def forbidden(*args: object, **kwargs: object) -> None:
    raise AssertionError("{DRIVER_MARKER}")

subprocess.run = forbidden
subprocess.Popen = forbidden
from app import bootstrap_database
argv = {argv!r}
code = 0 if argv is None else bootstrap_database.main(argv)
assert "app.bootstrap_demo" not in sys.modules
assert "app.db" not in sys.modules
assert "app.config" not in sys.modules
raise SystemExit(code)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=bootstrap_demo.BACKEND_BASE,
        env={"DATABASE_URL": MALFORMED_DATABASE_URL},
        capture_output=True,
        text=True,
        check=False,
        timeout=bootstrap_demo.COMMAND_TIMEOUT_SECONDS,
    )
    assert result.returncode == (1 if argv == [] else 0)
    assert DRIVER_MARKER not in result.stdout + result.stderr
    assert result.stderr == ""
    if argv is None:
        assert result.stdout == ""
    elif argv == []:
        assert json.loads(result.stdout) == {"status": "failed", "stage": "arguments"}
    else:
        assert "--run" in result.stdout


@pytest.mark.parametrize(
    "argv,code,stage",
    [([], 1, "arguments"), (["--help"], 0, None), (["--run"], 1, "migrate")],
)
def test_fresh_cli_bounds_malformed_database_failure(
    argv: list[str], code: int, stage: str | None
) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.bootstrap_database", *argv],
        cwd=bootstrap_demo.BACKEND_BASE,
        env={"DATABASE_URL": MALFORMED_DATABASE_URL},
        capture_output=True,
        text=True,
        check=False,
        timeout=bootstrap_demo.COMMAND_TIMEOUT_SECONDS,
    )
    assert result.returncode == code
    assert DRIVER_MARKER not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert result.stderr == ""
    if stage is None:
        assert "--run" in result.stdout
    else:
        assert json.loads(result.stdout) == {"status": "failed", "stage": stage}
        assert result.stdout.count("\n") == 1
