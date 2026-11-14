import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import psycopg
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.local_database_settings import local_database_url
from app.local_secret_state import read_password

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
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        check=False,
        shell=False,
        env=env,
    )


def invoke_command(
    runner: CommandRunner,
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = COMMAND_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> int:
    try:
        if env is not None:
            return runner(argv, cwd=cwd, timeout=timeout, env=env).returncode
        return runner(argv, cwd=cwd, timeout=timeout).returncode
    except (subprocess.TimeoutExpired, OSError):
        return 1


def seed_demo_user(factory: SessionFactory) -> None:
    session = factory()
    try:
        from app import models

        if session.get(models.User, 1) is None:
            session.add(models.User(id=1, display_name="FEWIA demo"))
            session.commit()
    except Exception:  # noqa: BLE001
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


def _bootstrap(
    endpoint: str,
    runner: CommandRunner,
    factory: SessionFactory,
    wait: WaitFn,
    infra_path: Path | None,
    admin_url: URL | None,
    migration_environment: dict[str, str] | None,
) -> int:
    migrate_argv = [sys.executable, "-m", "alembic", "upgrade", "head"]
    if invoke_command(
        runner,
        migrate_argv,
        cwd=BACKEND_BASE,
        timeout=COMMAND_TIMEOUT_SECONDS,
        env=migration_environment,
    ):
        emit("failed", "migrate")
        return 1
    try:
        seed_demo_user(factory)
    except Exception:  # noqa: BLE001
        emit("failed", "seed")
        return 1
    if admin_url is not None:
        try:
            from app.runtime_database_access import provision_runtime_access

            runtime_password = read_password(
                Path(os.environ["FEWIA_LOCAL_DATABASE_PASSWORD_FILE"])
            )
            with psycopg.connect(
                admin_url.set(drivername="postgresql").render_as_string(
                    hide_password=False
                ),
                autocommit=True,
            ) as connection:
                provision_runtime_access(connection, runtime_password)
        except Exception:  # noqa: BLE001
            emit("failed", "runtime-access")
            return 1
    script = infra_path or resolve_infra_script(BACKEND_BASE)
    if not provision_floci(endpoint, runner, wait, script):
        emit("failed", "floci")
        return 1
    emit("ok", "complete")
    return 0


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
    engine: Engine | None = None
    admin_url: URL | None = None
    migration_environment: dict[str, str] | None = None
    try:
        if os.environ.get("FEWIA_LOCAL_ADMIN_PASSWORD_FILE"):
            admin_url = local_database_url(admin=True)
            if admin_url is None:
                raise ValueError
            engine = create_engine(admin_url, hide_parameters=True)
            selected_factory: SessionFactory = sessionmaker(bind=engine)
            migration_environment = os.environ.copy()
            migration_environment["FEWIA_LOCAL_BOOTSTRAP_DATABASE"] = "1"
        elif factory is not None:
            selected_factory = factory
        else:
            raise ValueError
    except Exception:  # noqa: BLE001
        if engine is not None:
            engine.dispose()
        emit("failed", "database-settings")
        return 1
    try:
        return _bootstrap(
            args.endpoint,
            selected_runner,
            selected_factory,
            selected_wait,
            infra_path,
            admin_url,
            migration_environment,
        )
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
