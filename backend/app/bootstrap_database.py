import argparse
import sys
from collections.abc import Sequence
from typing import NoReturn

from app.bootstrap_demo import (
    BACKEND_BASE,
    COMMAND_TIMEOUT_SECONDS,
    CommandRunner,
    SessionFactory,
    emit,
    invoke_command,
    run_command,
    seed_demo_user,
)
from app.db import SessionLocal


class StaticArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("Invalid arguments.")


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: CommandRunner | None = None,
    factory: SessionFactory | None = None,
) -> int:
    stage = "arguments"
    try:
        parser = StaticArgumentParser(
            prog="python -m app.bootstrap_database",
            description="Apply database migrations and seed the demo user.",
            add_help=False,
            allow_abbrev=False,
        )
        parser.add_argument("-h", "--help", action="store_true", help="Show help.")
        parser.add_argument(
            "--run", action="store_true", help="Run the database setup."
        )
        args = parser.parse_args(argv)
        if args.help:
            parser.print_help()
            return 0
        if not args.run:
            emit("failed", stage)
            return 1
        selected_runner: CommandRunner = run_command if runner is None else runner
        selected_factory: SessionFactory = SessionLocal if factory is None else factory
        stage = "migrate"
        if invoke_command(
            selected_runner,
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_BASE,
            timeout=COMMAND_TIMEOUT_SECONDS,
        ):
            emit("failed", stage)
            return 1
        stage = "seed"
        seed_demo_user(selected_factory)
    except KeyboardInterrupt:
        emit("interrupted", stage)
        return 130
    except Exception:  # noqa: BLE001
        emit("failed", stage)
        return 1
    emit("ok", "complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
