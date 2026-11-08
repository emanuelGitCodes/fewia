#!/usr/bin/env bash
# Run from the extracted source root: bash infra/openai/compose-up.sh
# An absolute script path also works from another directory.
# Pass Compose up arguments to replace the default: -d --build.
# Compose project names and profiles use the caller's environment.
# Put FEWIA_OPENAI_API_KEY=<key> in .env. Compose mounts it as a secret in the worker only.
# The launcher reads .env as text, never evaluates it, and never prints the key.
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
    || fail 'Install Python 3; the launcher validates the configuration with it.'
[ -f "$source_root/.env" ] \
    || fail 'Create .env from .env.example and set FEWIA_OPENAI_API_KEY.'
command -v docker >/dev/null 2>&1 \
    || fail 'Install Docker Desktop with Docker Compose.'

# The Python step prints both failure lines itself; only the exit status is used here.
python3 - "$source_root" "$@" <<'PYTHON' || exit 1
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class LaunchError(Exception):
    pass


KEY_NAME = "FEWIA_OPENAI_API_KEY"
KEY_MISSING = "Set FEWIA_OPENAI_API_KEY in .env."
SECRET_INVALID = "The OpenAI key secret in compose.openai.yaml is not valid."
SECRET_PATH = "/run/secrets/openai_api_key"
LINE = re.compile(r"^(?:export\s+)?FEWIA_OPENAI_API_KEY\s*=\s*(.*)$")


def env_file_value_is_set(path: Path) -> bool:
    found = False
    for line in path.read_text(errors="replace").splitlines():
        match = LINE.match(line.strip())
        if match is None:
            continue
        value = match.group(1).strip()
        if value[:1] in ("'", '"') and value.count(value[0]) >= 2:
            value = value[1 : value.index(value[0], 1)]
        else:
            value = "" if value.startswith("#") else re.split(r"\s#", value, maxsplit=1)[0]
        found = bool(value.strip())
    return found


def key_is_set(root: Path) -> bool:
    if os.environ.get(KEY_NAME, "").strip():
        return True
    try:
        return env_file_value_is_set(root / ".env")
    except OSError:
        return False


def secret_names(entries: object) -> list[object]:
    if not isinstance(entries, list):
        raise ValueError
    return [
        entry.get("source") if isinstance(entry, dict) else entry
        for entry in entries
    ]


def validate_secret(config: object) -> None:
    if not isinstance(config, dict):
        raise ValueError
    if config["secrets"]["openai_api_key"]["environment"] != KEY_NAME:
        raise ValueError
    services = config["services"]
    worker = services["worker"].get("secrets")
    if (
        not isinstance(worker, list)
        or len(worker) != 1
        or not isinstance(worker[0], dict)
        or worker[0].get("source") != "openai_api_key"
        or worker[0].get("target") not in ("openai_api_key", SECRET_PATH)
    ):
        raise ValueError
    if "openai_api_key" in secret_names(services["api"].get("secrets", [])):
        raise ValueError
    for name in ("api", "worker"):
        if services[name]["environment"].get("FEWIA_OPENAI_API_KEY_FILE") != SECRET_PATH:
            raise ValueError


def main() -> int:
    root = Path(sys.argv[1]).resolve(strict=True)
    environment = os.environ.copy()
    compose = [
        "docker", "compose", "--env-file", ".env",
        "-f", "compose.yaml", "-f", "compose.openai.yaml",
        "--project-directory", str(root),
    ]
    detail = KEY_MISSING
    try:
        if not key_is_set(root):
            raise LaunchError(KEY_MISSING)
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
                "Docker is running and that .env is valid."
            )
            raise
        detail = SECRET_INVALID
        validate_secret(json.loads(result.stdout))
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
