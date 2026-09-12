import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from infra.bedrock_runtime_validation import (
    ERROR_MESSAGE,
    SOURCE_ROOT,
    default_credential_path,
    validate_checkout,
    validated_environment,
)

PROJECT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def compose_command(checkout: Path, project: str) -> list[str]:
    override = str(SOURCE_ROOT / "compose.bedrock-runtime.yaml")
    prefix = ["docker", "compose", "--project-directory", str(checkout), "-p", project]
    files = ["-f", str(checkout / "compose.yaml"), "-f", override]
    action = ["up", "-d", "--no-deps", "--force-recreate", "api", "worker"]
    return prefix + files + action


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recreate api and worker with the Bedrock runtime override."
    )
    parser.add_argument("--checkout", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--project", required=True)
    args = parser.parse_args(None if argv is None else list(argv))
    try:
        if PROJECT_PATTERN.fullmatch(args.project) is None:
            raise ValueError(ERROR_MESSAGE)
        checkout = validate_checkout(args.checkout)
        env = validated_environment(checkout, default_credential_path())
        result = subprocess.run(
            compose_command(checkout, args.project),
            shell=False,
            env=env,
            check=False,
        )
    except (RuntimeError, ValueError):
        print(ERROR_MESSAGE, file=sys.stderr)
        return 1
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
