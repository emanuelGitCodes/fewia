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
from infra.spoonacular_runtime_validation import validate_spoonacular_credentials

PROJECT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SPOONACULAR_ENV_KEYS = (
    "FEWIA_SPOONACULAR_KEY",
    "FEWIA_SPOONACULAR_KEY_FILE",
    "FEWIA_SPOONACULAR_CREDENTIALS_FILE",
)


def compose_command(
    checkout: Path, project: str, spoonacular: bool = False
) -> list[str]:
    override = str(SOURCE_ROOT / "compose.bedrock-runtime.yaml")
    prefix = ["docker", "compose", "--project-directory", str(checkout), "-p", project]
    files = ["-f", str(checkout / "compose.yaml"), "-f", override]
    if spoonacular:
        files += ["-f", str(SOURCE_ROOT / "compose.spoonacular.yaml")]
    action = ["up", "-d", "--no-deps", "--force-recreate", "api", "worker"]
    return prefix + files + action


def _child_environment(
    env: dict[str, str], credential_path: Path | None
) -> dict[str, str]:
    child = dict(env)
    for key in _SPOONACULAR_ENV_KEYS:
        child.pop(key, None)
    if credential_path is not None:
        child["FEWIA_SPOONACULAR_CREDENTIALS_FILE"] = str(credential_path)
    return child


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recreate api and worker with the Bedrock runtime override."
    )
    parser.add_argument("--checkout", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--project", required=True)
    parser.add_argument("--spoonacular-key-file", type=Path, default=None)
    args = parser.parse_args(None if argv is None else list(argv))
    try:
        if PROJECT_PATTERN.fullmatch(args.project) is None:
            raise ValueError(ERROR_MESSAGE)
        checkout = validate_checkout(args.checkout)
        env = validated_environment(checkout, default_credential_path())
        key_file = args.spoonacular_key_file
        spoonacular_path: Path | None = None
        if key_file is not None:
            spoonacular_path = validate_spoonacular_credentials(checkout, key_file)
        result = subprocess.run(
            compose_command(checkout, args.project, spoonacular_path is not None),
            shell=False,
            env=_child_environment(env, spoonacular_path),
            check=False,
        )
    except (RuntimeError, ValueError):
        print(ERROR_MESSAGE, file=sys.stderr)
        return 1
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
