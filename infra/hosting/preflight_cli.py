import argparse
import json
import os
import re
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Never

from hosted_app import (
    _finite_float,
    _reject_constant,
    _unique_object,
    load_deployment_config,
)
from preflight_checks import PreflightError
from preflight_runner import run_preflight

_ERROR = "preflight invocation is invalid"
_LIMIT = 1024 * 1024
_BASE = ["--region=us-east-1", "--output=json", "--no-cli-pager"]
_NAME = r"[A-Za-z0-9_-]{1,255}"
_ECS = r"arn:aws:ecs:us-east-1:[0-9]{12}:"
_OPTIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("sts", "get-caller-identity"): (),
    ("acm", "describe-certificate"): (
        r"--certificate-arn=arn:aws:acm:us-east-1:[0-9]{12}:certificate/"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    ),
    ("cloudformation", "describe-stacks"): ("--stack-name=FewiaHostedDemoDev",),
    ("ecr", "describe-images"): (
        r"--registry-id=[0-9]{12}",
        r"--repository-name=[a-z0-9]+(?:[._-][a-z0-9]+)*"
        r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*",
        r"--image-ids=imageDigest=sha256:[0-9a-f]{64}",
    ),
    ("ecs", "describe-tasks"): (
        rf"--cluster={_ECS}cluster/{_NAME}",
        rf"--tasks={_ECS}task/{_NAME}/[0-9a-f]{{32}}",
    ),
}


def _valid_profile(profile: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", profile) is not None


def _invoke_aws(command: list[str], *, profile: str) -> object:
    try:
        if (
            type(command) is not list
            or any(type(part) is not str for part in command)
            or len(command) < 6
            or command[0] != "aws"
            or command[3:6] != _BASE
            or not _valid_profile(profile)
        ):
            raise PreflightError(_ERROR)
        patterns = _OPTIONS.get((command[1], command[2]))
        if patterns is None or len(command) != 6 + len(patterns):
            raise PreflightError(_ERROR)
        if any(
            re.fullmatch(pattern, argument) is None
            for pattern, argument in zip(patterns, command[6:], strict=True)
        ):
            raise PreflightError(_ERROR)
        environment = os.environ.copy()
        environment.update(AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off")
        result = subprocess.run(
            [
                *command,
                f"--profile={profile}",
                "--cli-connect-timeout=10",
                "--cli-read-timeout=30",
            ],
            shell=False,
            stdin=subprocess.DEVNULL,
            timeout=45,
            capture_output=True,
            check=False,
            env=environment,
        )
        # The limit applies after capture. It does not limit OS memory use.
        if result.returncode != 0 or len(result.stdout) > _LIMIT:
            raise PreflightError(_ERROR)
        return json.loads(
            result.stdout.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except Exception:
        pass
    raise PreflightError(_ERROR)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValueError("arguments are invalid")


def _status(status: str, stage: str, code: int) -> int:
    print(json.dumps({"status": status, "stage": stage}))
    return code


def main(argv: Sequence[str] | None = None) -> int:
    stage = "arguments"
    try:
        parser = _Parser(
            prog="python preflight_cli.py",
            allow_abbrev=False,
            description="Metadata preflight. No deployment proof or authorization.",
        )
        parser.add_argument("--config", type=Path, required=True)
        parser.add_argument("--profile", required=True)
        parser.add_argument("--bootstrap-task-arn")
        try:
            args = parser.parse_args(argv)
        except SystemExit as error:
            if error.code == 0:
                return 0
            return _status("failed", stage, 1)
        if not _valid_profile(args.profile):
            return _status("failed", stage, 1)
        stage = "configuration"
        config = load_deployment_config(args.config)
        stage = "preflight"
        checks = run_preflight(
            config,
            lambda command: _invoke_aws(command, profile=args.profile),
            bootstrap_task_arn=args.bootstrap_task_arn,
            now=datetime.now(UTC),
        )
        print(json.dumps({"status": "passed", "phase": config.phase, "checks": checks}))
        return 0
    except KeyboardInterrupt:
        return _status("interrupted", stage, 130)
    except (Exception, SystemExit):
        return _status("failed", stage, 1)


if __name__ == "__main__":
    raise SystemExit(main())
