#!/usr/bin/env bash
# Run from the extracted source root: bash infra/openai/compose-up.sh
# An absolute script path also works from another directory.
# Pass Compose up arguments to replace the default: -d --build.
# Compose project names and profiles use the caller's environment.
set +x
set -euo pipefail

fail() {
    printf '%s\n' 'OpenAI Compose launch failed.' >&2
    exit 1
}

source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd -P) || fail
command -v python3 >/dev/null 2>&1 || fail

python3 - "$source_root" "$@" 2>/dev/null <<'PYTHON' || fail
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


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
        if not path.is_absolute() or not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError
        resolved = path.resolve(strict=True)
        if resolved == root or root in resolved.parents:
            raise ValueError
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
    try:
        result = subprocess.run(
            [*compose, "config", "--no-path-resolution", "--format", "json"],
            cwd=root,
            env=environment,
            capture_output=True,
            check=True,
        )
        validate_mounts(json.loads(result.stdout), root)
        arguments = sys.argv[2:] or ["-d", "--build"]
        subprocess.run(
            [*compose, "up", *arguments],
            cwd=root,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except Exception:
        return 1
    print("OpenAI Compose services started.")
    return 0


sys.exit(main())
PYTHON
