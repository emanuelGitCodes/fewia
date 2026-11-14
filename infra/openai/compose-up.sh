#!/usr/bin/env bash
# Run from the extracted source root: bash infra/openai/compose-up.sh
# An absolute script path also works from another directory.
# The launcher prints one line per stage and lets Compose show its own pull,
# build, and start progress. It checks the OpenAI key before it builds, waits
# for the one-shot setup service, waits for the API, and prints the app URL.
# Extra arguments go to "docker compose up -d". Skip the key check with
# FEWIA_SKIP_KEY_CHECK=1.
# Use leading --kroger-live and --tools flags to select local overlays.
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
printf '%s\n' 'Checking .env.'
[ -f "$source_root/.env" ] \
    || fail 'Create .env from .env.example and set FEWIA_OPENAI_API_KEY.'
command -v docker >/dev/null 2>&1 \
    || fail 'Install Docker Desktop with Docker Compose.'

# The Python step prints both failure lines itself; only the exit status is used here.
python3 - "$source_root" "$@" <<'PYTHON' || exit 1
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

if __name__ == "__main__":
    sys.path.insert(0, str(Path(sys.argv[1]) / "backend"))
from app.local_secret_state import prepare_local_state, read_password, read_private_file


class LaunchError(Exception):
    pass


KEY_NAME = "FEWIA_OPENAI_API_KEY"
KEY_MISSING = "Set FEWIA_OPENAI_API_KEY in .env."
SECRET_INVALID = "The OpenAI key secret in compose.yaml is not valid."
SECRET_PATH = "/run/secrets/openai_api_key"
KROGER_LIVE_FLAG = "--kroger-live"
KROGER_INVALID = (
    "The Compose configuration does not set FEWIA_KROGER_MODE to {mode} "
    "on api and worker."
)
US_MODELS_URL = "https://us.api.openai.com/v1/models"
GLOBAL_MODELS_URL = "https://api.openai.com/v1/models"
LOOPBACK_PREFIX = "http://127.0.0.1:"
MODELS_URL_NAME = "FEWIA_OPENAI_MODELS_URL"
URL_INVALID = "FEWIA_OPENAI_MODELS_URL must start with http://127.0.0.1: and name that host."
KEY_REJECTED = (
    "OpenAI rejected FEWIA_OPENAI_API_KEY (HTTP {code}). "
    "Create a new key at https://platform.openai.com/api-keys and update .env."
)
PULL_FAILED = "Docker Compose pull failed with exit code {code}. See the output above."
BUILD_FAILED = "Docker Compose build failed with exit code {code}. See the output above."
UP_FAILED = (
    "Docker Compose up failed with exit code {code}. "
    "Run the same command without the launcher to see the Compose output."
)
SETUP_FAILED = "Setup did not finish. Run: docker compose logs bootstrap"
API_FAILED = "The API did not become healthy. Run: docker compose logs api"
DEFAULT_PORT = "5173"
POLL_SECONDS = 2.0
KEY_CHECK_TIMEOUT = 10


def stage(text: str) -> None:
    print(text, flush=True)


def parse_env_value(raw: str) -> str:
    value = raw.strip()
    if value[:1] in ("'", '"') and value.count(value[0]) >= 2:
        value = value[1 : value.index(value[0], 1)]
    else:
        value = "" if value.startswith("#") else re.split(r"\s#", value, maxsplit=1)[0]
    return value.strip()


def env_file_value(path: Path, name: str) -> str:
    pattern = re.compile(rf"^(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$")
    found = ""
    for line in read_private_file(path).splitlines():
        match = pattern.match(line.strip())
        if match is not None:
            found = parse_env_value(match.group(1))
    return found


def setting(root: Path, name: str) -> str:
    # The process environment wins over .env, as it does for Compose.
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        return env_file_value(root / ".env", name)
    except OSError:
        return ""


def key_is_set(root: Path) -> bool:
    return bool(setting(root, KEY_NAME))


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


def validate_kroger_mode(config: object, mode: str) -> None:
    services = config["services"]  # type: ignore[index]
    for name in ("api", "worker"):
        if services[name]["environment"].get("FEWIA_KROGER_MODE") != mode:
            raise ValueError


def loopback_url(url: str) -> bool:
    if not url.startswith(LOOPBACK_PREFIX):
        return False
    try:
        parts = urlsplit(url)
        return (
            parts.hostname == "127.0.0.1"
            and parts.username is None
            and parts.password is None
            and parts.port is not None
        )
    except ValueError:
        return False


def models_url(root: Path) -> str:
    override = os.environ.get(MODELS_URL_NAME, "")
    if override:
        if not loopback_url(override):
            raise LaunchError(URL_INVALID)
        return override
    if setting(root, "FEWIA_OPENAI_REGION") == "us":
        return US_MODELS_URL
    return GLOBAL_MODELS_URL


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


def key_status(url: str, key: str) -> int | None:
    # Print nothing from here: an exception message can contain the header.
    try:
        handlers: list[object] = [NoRedirect()]
        if url.startswith(LOOPBACK_PREFIX):
            handlers.append(urllib.request.ProxyHandler({}))
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(
            url, headers={"User-Agent": "fewia-compose-launcher"}
        )
        request.add_unredirected_header("Authorization", f"Bearer {key}")
        with opener.open(request, timeout=KEY_CHECK_TIMEOUT) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:
        return None


def check_openai_key(root: Path) -> None:
    stage("Checking the OpenAI key.")
    url = models_url(root)
    if os.environ.get("FEWIA_SKIP_KEY_CHECK") == "1":
        stage("Skipped the OpenAI key check.")
        return
    status = key_status(url, setting(root, KEY_NAME))
    if status == 200:
        stage("OpenAI key accepted.")
    elif status in (401, 403):
        raise LaunchError(KEY_REJECTED.format(code=status))
    else:
        stage("Could not check the OpenAI key. Continuing.")


def run_visible(command: list[str], root: Path, environment: dict[str, str], failure: str) -> None:
    try:
        subprocess.run(command, cwd=root, env=environment, check=True)
    except subprocess.CalledProcessError as error:
        raise LaunchError(failure.format(code=error.returncode)) from None
    except Exception:
        raise LaunchError(failure.format(code=1)) from None


def parse_entries(text: str) -> list[dict[str, object]]:
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        items = data if isinstance(data, list) else [data]
    except ValueError:
        items = []
        for line in text.splitlines():
            try:
                items.append(json.loads(line))
            except ValueError:
                continue
    return [item for item in items if isinstance(item, dict)]


def service_entry(
    compose: list[str], service: str, root: Path, environment: dict[str, str], *, all_states: bool
) -> dict[str, object] | None:
    command = [*compose, "ps", *(["-a"] if all_states else []), "--format", "json", service]
    try:
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            errors="replace",
            check=True,
        )
    except Exception:
        return None
    entries = parse_entries(result.stdout)
    return entries[0] if entries else None


def poll(probe: object, timeout: float) -> bool | None:
    deadline = time.monotonic() + timeout
    while True:
        outcome = probe()  # type: ignore[operator]
        if outcome is not None:
            return outcome
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(POLL_SECONDS, remaining))


def seconds(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value >= 0 else default


def wait_for_setup(compose: list[str], root: Path, environment: dict[str, str]) -> None:
    def probe() -> bool | None:
        entry = service_entry(compose, "bootstrap", root, environment, all_states=True)
        if entry is None or entry.get("State") != "exited":
            return None
        code = entry.get("ExitCode")
        return type(code) is int and code == 0

    if poll(probe, seconds("FEWIA_SETUP_TIMEOUT_SECONDS", 300)) is not True:
        raise LaunchError(SETUP_FAILED)


def wait_for_api(compose: list[str], root: Path, environment: dict[str, str]) -> None:
    def probe() -> bool | None:
        entry = service_entry(compose, "api", root, environment, all_states=False)
        return True if entry is not None and entry.get("Health") == "healthy" else None

    if poll(probe, seconds("FEWIA_API_TIMEOUT_SECONDS", 180)) is not True:
        raise LaunchError(API_FAILED)


def wait_for_database(compose: list[str], root: Path, environment: dict[str, str]) -> None:
    def probe() -> bool | None:
        entry = service_entry(compose, "postgres", root, environment, all_states=False)
        return True if entry is not None and entry.get("Health") == "healthy" else None

    if poll(probe, seconds("FEWIA_DATABASE_TIMEOUT_SECONDS", 180)) is not True:
        raise LaunchError("The internal database did not become healthy.")


def rotate_database_password(
    compose: list[str], root: Path, environment: dict[str, str], password_file: Path
) -> None:
    password = read_password(password_file)
    command = [
        *compose, "exec", "-T", "--user", "postgres", "postgres",
        "psql", "-X", "--no-password", "--host", "/var/run/postgresql",
        "--username", "fewia", "--dbname", "fewia", "--set", "ON_ERROR_STOP=1",
    ]
    try:
        subprocess.run(
            command, cwd=root, env=environment, check=True, capture_output=True,
            text=True, timeout=30,
            input=(
                "SET password_encryption = 'scram-sha-256';\n"
                "\\password fewia\n"
                f"{password}\n{password}\n"
            ),
        )
    except Exception:
        raise LaunchError("Internal database credential rotation failed.") from None


def report_failure(detail: str) -> int:
    print("OpenAI Compose launch failed.", file=sys.stderr)
    print(detail, file=sys.stderr)
    return 1


def main() -> int:
    root = Path(sys.argv[1]).resolve(strict=True)
    environment = os.environ.copy()
    arguments = sys.argv[2:]
    kroger_live = False
    tools = False
    while arguments[:1] in ([KROGER_LIVE_FLAG], ["--tools"]):
        kroger_live = kroger_live or arguments[0] == KROGER_LIVE_FLAG
        tools = tools or arguments[0] == "--tools"
        arguments = arguments[1:]
    mode = "live" if kroger_live else "fixture"
    files = ["-f", "compose.yaml"]
    if kroger_live:
        files += ["-f", "compose.kroger.yaml"]
    if tools:
        files += ["-f", "compose.tools.yaml"]
    compose = [
        "docker", "compose", "--env-file", ".env", "--env-file", ".env0600",
        *files,
        "--project-directory", str(root),
    ]
    detail = "The .env file MUST be a regular private file with mode 0600."
    try:
        read_private_file(root / ".env")
        detail = KEY_MISSING
        if not key_is_set(root):
            raise LaunchError(KEY_MISSING)
        check_openai_key(root)
        stage("Preparing private local state.")
        detail = "Private local state is unsafe or invalid. Run as a nonroot host user."
        state = prepare_local_state(root)
        environment.update({
            "FEWIA_LOCAL_ADMIN_PASSWORD_FILE": str(state.admin),
            "FEWIA_LOCAL_RUNTIME_PASSWORD_FILE": str(state.runtime),
            "FEWIA_LOCAL_PAIRING_KEY_FILE": str(state.pairing),
            "FEWIA_HOST_UID": str(state.uid),
            "FEWIA_HOST_GID": str(state.gid),
        })
        stage("Checking the Compose configuration.")
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
        config = json.loads(result.stdout)
        validate_secret(config)
        detail = KROGER_INVALID.format(mode=mode)
        validate_kroger_mode(config, mode)
        stage("Downloading images.")
        run_visible([*compose, "pull", "--ignore-buildable"], root, environment, PULL_FAILED)
        stage("Building images. The first run takes several minutes.")
        run_visible([*compose, "build"], root, environment, BUILD_FAILED)
        stage("Stopping application services.")
        run_visible(
            [*compose, "stop", "api", "worker", "sync-worker", "bootstrap"],
            root, environment, "Could not stop application services.",
        )
        stage("Starting the internal database.")
        run_visible(
            [*compose, "up", "-d", "--no-deps", "postgres"],
            root, environment, UP_FAILED,
        )
        wait_for_database(compose, root, environment)
        stage("Rotating the internal database credential.")
        rotate_database_password(compose, root, environment, state.admin)
        stage("Setting up the database and demo user.")
        run_visible(
            [*compose, "up", "-d", "--force-recreate", "bootstrap"],
            root, environment, UP_FAILED,
        )
        wait_for_setup(compose, root, environment)
        stage("Starting services.")
        run_visible([*compose, "up", "-d", *arguments], root, environment, UP_FAILED)
        stage("OpenAI Compose services started.")
        wait_for_setup(compose, root, environment)
        stage("Waiting for the API.")
        wait_for_api(compose, root, environment)
    except LaunchError as error:
        return report_failure(str(error))
    except Exception:
        return report_failure(detail)
    port = setting(root, "WEB_HOST_PORT")
    if not (port.isascii() and port.isdigit()):
        port = DEFAULT_PORT
    stage(f"FEWIA is ready at http://127.0.0.1:{port}/prototype")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYTHON
