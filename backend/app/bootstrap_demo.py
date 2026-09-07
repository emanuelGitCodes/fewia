import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal

ALLOWED_ENDPOINTS = frozenset(
    {"http://127.0.0.1:4566", "http://localhost:4566", "http://floci:4566"}
)
COMMAND_TIMEOUT_SECONDS = 30
FLOCI_ATTEMPTS = 3
WaitFn = Callable[[float], object]
SessionFactory = Callable[[], Session]


class CommandResult(Protocol):
    returncode: int


CommandRunner = Callable[..., CommandResult]
BACKEND_BASE = Path(__file__).resolve().parents[1]


def resolve_infra_script(base: Path) -> Path:
    docker_script = base / "infra" / "floci_bootstrap.py"
    if docker_script.is_file():
        return docker_script
    return base.parent / "infra" / "floci_bootstrap.py"


def emit(status: str, stage: str) -> None:
    print(json.dumps({"status": status, "stage": stage}, sort_keys=True))


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        check=False,
        shell=False,
    )


def invoke_command(
    runner: CommandRunner,
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> int:
    try:
        return runner(argv, cwd=cwd, timeout=timeout).returncode
    except (subprocess.TimeoutExpired, OSError):
        return 1


def seed_demo_user(factory: SessionFactory) -> None:
    session = factory()
    try:
        if session.get(models.User, 1) is None:
            session.add(models.User(id=1, display_name="FEWIA demo"))
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def provision_floci(
    endpoint: str, runner: CommandRunner, wait: WaitFn, script: Path
) -> bool:
    argv = [sys.executable, str(script), "--endpoint", endpoint]
    for attempt in range(FLOCI_ATTEMPTS):
        if invoke_command(runner, argv, timeout=COMMAND_TIMEOUT_SECONDS) == 0:
            return True
        if attempt + 1 < FLOCI_ATTEMPTS:
            wait(1.0)
    return False


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner | None = None,
    factory: SessionFactory | None = None,
    wait: WaitFn | None = None,
    infra_path: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Seed the local demo stack.")
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args(argv)
    if args.endpoint not in ALLOWED_ENDPOINTS:
        emit("failed", "endpoint")
        return 1
    selected_runner: CommandRunner = run_command if runner is None else runner
    selected_wait: WaitFn = time.sleep if wait is None else wait
    selected_factory: SessionFactory = SessionLocal if factory is None else factory
    migrate_argv = [sys.executable, "-m", "alembic", "upgrade", "head"]
    if invoke_command(
        selected_runner,
        migrate_argv,
        cwd=BACKEND_BASE,
        timeout=COMMAND_TIMEOUT_SECONDS,
    ):
        emit("failed", "migrate")
        return 1
    try:
        seed_demo_user(selected_factory)
    except Exception:
        emit("failed", "seed")
        return 1
    script = infra_path or resolve_infra_script(BACKEND_BASE)
    if not provision_floci(args.endpoint, selected_runner, selected_wait, script):
        emit("failed", "floci")
        return 1
    emit("ok", "complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
