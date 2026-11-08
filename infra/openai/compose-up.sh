#!/usr/bin/env bash
# Run from the extracted source root: bash infra/openai/compose-up.sh
# An absolute script path also works from another directory.
# Pass Compose up arguments to replace the default: -d --build.
# Compose project names and profiles use the caller's environment.
set +x
set -euo pipefail

fail() {
    printf '%s\n' 'OpenAI Compose launch failed.' >&2
    if [ "$#" -gt 0 ]; then
        printf '%s\n' "$1" >&2
    fi
    exit 1
}

source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd -P) || fail
command -v python3 >/dev/null 2>&1 \
    || fail 'Install Python 3; the launcher validates the key path with it.'
[ -f "$source_root/.env" ] \
    || fail 'Create .env from .env.example and set FEWIA_OPENAI_API_KEY_FILE.'
command -v docker >/dev/null 2>&1 \
    || fail 'Install Docker Desktop with Docker Compose.'

# The Python step prints both failure lines itself; only the exit status is used here.
python3 - "$source_root" "$@" <<'PYTHON' || exit 1
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


class LaunchError(Exception):
    pass


MOUNT_INVALID = "The OpenAI key mount in compose.openai.yaml is not valid."


def validate_mounts(config: object, root: Path) -> None:
    if not isinstance(config, dict):
        raise ValueError
    services = config["services"]
    sources: list[str] = []
    for name in ("api", "worker"):
        mounts = services[name]["volumes"]
        matches = [
            mount for mount in mounts
            if mount.get("target") == "/run/fewia/openai-api-key"
        ]
        if len(matches) != 1:
            raise ValueError
        mount = matches[0]
        source = mount.get("source")
        if (
            mount.get("type") != "bind"
            or mount.get("read_only") is not True
            or not isinstance(source, str)
        ):
            raise ValueError
        path = Path(source)
        if not path.is_absolute():
            raise LaunchError("FEWIA_OPENAI_API_KEY_FILE MUST be an absolute path.")
        try:
            regular = stat.S_ISREG(path.lstat().st_mode)
        except OSError:
            regular = False
        if not regular:
            raise LaunchError(
                "FEWIA_OPENAI_API_KEY_FILE MUST name an existing regular file."
            )
        resolved = path.resolve(strict=True)
        if resolved == root or root in resolved.parents:
            raise LaunchError(
                "FEWIA_OPENAI_API_KEY_FILE MUST be outside the repository."
            )
        sources.append(source)
    if sources[0] != sources[1]:
        raise ValueError


def main() -> int:
    root = Path(sys.argv[1]).resolve(strict=True)
    environment = os.environ.copy()
    compose = [
        "docker", "compose", "--env-file", ".env",
        "-f", "compose.yaml", "-f", "compose.openai.yaml",
        "--project-directory", str(root),
    ]
    detail = MOUNT_INVALID
    try:
        try:
            result = subprocess.run(
                [*compose, "config", "--no-path-resolution", "--format", "json"],
                cwd=root,
                env=environment,
                capture_output=True,
                check=True,
            )
        except Exception:
            detail = (
                "Docker Compose could not read the configuration. Check that "
                "Docker is running and that FEWIA_OPENAI_API_KEY_FILE is set "
                "in .env."
            )
            raise
        try:
            validate_mounts(json.loads(result.stdout), root)
        except LaunchError as error:
            detail = str(error)
            raise
        arguments = sys.argv[2:] or ["-d", "--build"]
        try:
            subprocess.run(
                [*compose, "up", *arguments],
                cwd=root,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except subprocess.CalledProcessError as error:
            detail = (
                f"Docker Compose up failed with exit code {error.returncode}. "
                "Run the same command without the launcher to see the Compose output."
            )
            raise
        except Exception:
            detail = (
                "Docker Compose up failed with exit code 1. "
                "Run the same command without the launcher to see the Compose output."
            )
            raise
    except Exception:
        print("OpenAI Compose launch failed.", file=sys.stderr)
        print(detail, file=sys.stderr)
        return 1
    print("OpenAI Compose services started.")
    return 0


sys.exit(main())
PYTHON
