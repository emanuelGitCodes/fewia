"""Check the OpenAI Compose launcher with a local Docker stub."""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "infra/openai/compose-up.sh"
COMPOSE = ROOT / "compose.yaml"
COMPOSE_KROGER = ROOT / "compose.kroger.yaml"
KROGER_FIXTURE = (
    "The Compose configuration does not set FEWIA_KROGER_MODE to fixture "
    "on api and worker."
)
KROGER_LIVE = (
    "The Compose configuration does not set FEWIA_KROGER_MODE to live "
    "on api and worker."
)
ERROR = "OpenAI Compose launch failed.\n"
KEY_VALUE = "sk-PRIVATE_KEY_SENTINEL"
KEY_MISSING = "Set FEWIA_OPENAI_API_KEY in .env."
SECRET = "The OpenAI key secret in compose.yaml is not valid."
CONFIG = (
    "Docker Compose could not read the configuration. Check that Docker is "
    "running and that .env is valid."
)
SECRET_PATH = "/run/secrets/openai_api_key"
URL_INVALID = (
    "FEWIA_OPENAI_MODELS_URL must start with http://127.0.0.1: and name that host."
)
SETUP_FAILED = "Setup did not finish. Run: docker compose logs bootstrap"
API_FAILED = "The API did not become healthy. Run: docker compose logs api"
SKIPPED = "Skipped the OpenAI key check."
CHECK_ENV = "Checking .env."
CHECK_KEY = "Checking the OpenAI key."
CHECK_CONFIG = "Checking the Compose configuration."
SETUP_STAGE = "Setting up the database and demo user."
API_STAGE = "Waiting for the API."
VISIBLE_STDERR = "COMPOSE_PULL_STDERR\nCOMPOSE_BUILD_STDERR\nCOMPOSE_UP_STDERR\n"
FAKE_DOCKER = """\
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
sub = args[args.index("--project-directory") + 2]
with Path(os.environ["FAKE_LOG"]).open("a") as log:
    log.write(json.dumps({
        "args": args,
        "cwd": os.getcwd(),
        "project": os.environ.get("COMPOSE_PROJECT_NAME"),
        "profiles": os.environ.get("COMPOSE_PROFILES"),
    }) + "\\n")
if sub == "config":
    print("PRIVATE_ERROR_SENTINEL", file=sys.stderr)
    print(os.environ["FAKE_CONFIG"])
    sys.exit(int(os.environ["FAKE_CONFIG_STATUS"]))
if sub == "ps":
    print("PRIVATE_ERROR_SENTINEL", file=sys.stderr)
    if args[-1] == "bootstrap":
        state = os.environ.get("FAKE_BOOTSTRAP", "exited:0")
        if state == "none":
            sys.exit(0)
        entry = {"Service": "bootstrap", "State": state.split(":")[0]}
        if ":" in state:
            entry["ExitCode"] = int(state.split(":")[1])
    else:
        entry = {
            "Service": "api",
            "State": "running",
            "Health": os.environ.get("FAKE_API_HEALTH", "healthy"),
        }
    if os.environ.get("FAKE_PS_STYLE", "array") == "array":
        print(json.dumps([entry]))
    else:
        print(json.dumps(entry))
    sys.exit(0)
name = sub.upper()
print(f"COMPOSE_{name}_STDOUT")
print(f"COMPOSE_{name}_STDERR", file=sys.stderr)
sys.exit(int(os.environ.get(f"FAKE_{name}_STATUS", "0")))
"""


def _stages(key_line: str = SKIPPED, port: str = "5173") -> list[str]:
    return [
        CHECK_ENV,
        CHECK_KEY,
        key_line,
        CHECK_CONFIG,
        "Downloading images.",
        "COMPOSE_PULL_STDOUT",
        "Building images. The first run takes several minutes.",
        "COMPOSE_BUILD_STDOUT",
        "Starting services.",
        "COMPOSE_UP_STDOUT",
        "OpenAI Compose services started.",
        SETUP_STAGE,
        API_STAGE,
        f"FEWIA is ready at http://127.0.0.1:{port}/prototype",
    ]


def _text(lines: list[str]) -> str:
    return "".join(f"{line}\n" for line in lines)


@dataclass
class Launcher:
    root: Path
    outside: Path
    log: Path
    environment: dict[str, str]

    def run(
        self,
        config: object,
        *,
        from_root: bool = False,
        arguments: tuple[str, ...] = (),
        config_status: int = 0,
        up_status: int = 0,
        raw_config: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            **self.environment,
            "FAKE_CONFIG": json.dumps(config) if raw_config is None else raw_config,
            "FAKE_CONFIG_STATUS": str(config_status),
            "FAKE_UP_STATUS": str(up_status),
            **(extra or {}),
        }
        script = self.root / "infra/openai/compose-up.sh"
        return subprocess.run(
            [
                "bash",
                "infra/openai/compose-up.sh" if from_root else str(script),
                *arguments,
            ],
            cwd=self.root if from_root else self.outside,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def calls(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def write_env(self, *lines: str) -> None:
        (self.root / ".env").write_text("".join(f"{line}\n" for line in lines))


@pytest.fixture
def launcher(tmp_path: Path) -> Launcher:
    root = tmp_path / "extracted source"
    scripts = root / "infra/openai"
    scripts.mkdir(parents=True)
    (scripts / "compose-up.sh").write_text(LAUNCHER.read_text())
    (root / "compose.yaml").write_text("services: {}\n")
    (root / "compose.kroger.yaml").write_text("services: {}\n")
    (root / ".env").write_text(
        f"touch SHELL_EVALUATION_MARKER\nFEWIA_OPENAI_API_KEY={KEY_VALUE}\n"
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(f"#!{sys.executable}\n{FAKE_DOCKER}")
    docker.chmod(0o755)
    log = tmp_path / "docker-calls.jsonl"
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("COMPOSE_", "FEWIA_", "FAKE_"))
        and name != "WEB_HOST_PORT"
    }
    # Tests never reach OpenAI: the key check is skipped unless a test turns it on
    # and points it at a local server.
    environment.update(
        PATH=f"{binaries}{os.pathsep}{os.environ['PATH']}",
        FAKE_LOG=str(log),
        COMPOSE_PROJECT_NAME="launcher-test",
        COMPOSE_PROFILES="sample",
        COMPOSE_FILE="unrelated.yaml",
        FEWIA_SKIP_KEY_CHECK="1",
        FEWIA_SETUP_TIMEOUT_SECONDS="1",
        FEWIA_API_TIMEOUT_SECONDS="1",
    )
    return Launcher(root, outside, log, environment)


class _ModelsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        server = cast("_ModelsServer", self.server)
        server.requests.append((self.path, self.headers.get("Authorization")))
        self.send_response(server.status)
        if 300 <= server.status < 400:
            self.send_header("Location", "/v1/redirected")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return None


class _ModelsServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ModelsHandler)
        self.status = 200
        self.requests: list[tuple[str, str | None]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/v1/models"


@pytest.fixture
def models_server() -> Iterator[_ModelsServer]:
    server = _ModelsServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _key_check(url: str) -> dict[str, str]:
    return {"FEWIA_SKIP_KEY_CHECK": "0", "FEWIA_OPENAI_MODELS_URL": url}


def _config(
    *,
    secret_environment: str = "FEWIA_OPENAI_API_KEY",
    worker_secrets: list[object] | None = None,
    api_secrets: list[object] | None = None,
    api_path: str = SECRET_PATH,
    worker_path: str = SECRET_PATH,
    api_mode: str | None = "fixture",
    worker_mode: str | None = "fixture",
) -> dict[str, object]:
    api_environment = {"FEWIA_OPENAI_API_KEY_FILE": api_path}
    worker_environment = {"FEWIA_OPENAI_API_KEY_FILE": worker_path}
    if api_mode is not None:
        api_environment["FEWIA_KROGER_MODE"] = api_mode
    if worker_mode is not None:
        worker_environment["FEWIA_KROGER_MODE"] = worker_mode
    api: dict[str, object] = {"environment": api_environment}
    if api_secrets is not None:
        api["secrets"] = api_secrets
    if worker_secrets is None:
        worker_secrets = [{"source": "openai_api_key", "target": "openai_api_key"}]
    return {
        "secrets": {"openai_api_key": {"environment": secret_environment}},
        "services": {
            "api": api,
            "worker": {
                "environment": worker_environment,
                "secrets": worker_secrets,
            },
        },
        "private": "PRIVATE_CONFIG_SENTINEL",
    }


def _assert_no_leak(
    launcher: Launcher, result: subprocess.CompletedProcess[str]
) -> None:
    for output in (result.stdout, result.stderr):
        assert "PRIVATE_" not in output
        assert KEY_VALUE not in output
    if launcher.log.exists():
        assert KEY_VALUE not in launcher.log.read_text()


def _assert_rejected(
    launcher: Launcher,
    result: subprocess.CompletedProcess[str],
    detail: str = SECRET,
) -> None:
    assert result.returncode != 0
    assert result.stdout == _text(_stages()[:4])
    assert result.stderr == f"{ERROR}{detail}\n"
    _assert_no_leak(launcher, result)
    calls = launcher.calls()
    assert len(calls) == 1
    assert "config" in calls[0]["args"]


def _assert_key_missing(
    launcher: Launcher, result: subprocess.CompletedProcess[str]
) -> None:
    assert result.returncode != 0
    assert result.stdout == f"{CHECK_ENV}\n"
    assert result.stderr == f"{ERROR}{KEY_MISSING}\n"
    _assert_no_leak(launcher, result)
    assert not launcher.log.exists()


def _compose_prefix(launcher: Launcher, files: tuple[str, ...]) -> list[str]:
    return [
        "compose",
        "--env-file",
        ".env",
        *[part for name in files for part in ("-f", name)],
        "--project-directory",
        str(launcher.root),
    ]


@pytest.mark.parametrize("from_root", [True, False])
@pytest.mark.parametrize("arguments", [(), ("--build", "api")])
@pytest.mark.parametrize("live", [False, True])
def test_valid_config_starts_with_the_validated_inputs(
    launcher: Launcher, from_root: bool, arguments: tuple[str, ...], live: bool
) -> None:
    mode = "live" if live else "fixture"
    files = ("compose.yaml", "compose.kroger.yaml") if live else ("compose.yaml",)
    result = launcher.run(
        _config(api_mode=mode, worker_mode=mode),
        from_root=from_root,
        arguments=(("--kroger-live",) if live else ()) + arguments,
    )
    assert result.returncode == 0
    assert result.stdout == _text(_stages())
    assert result.stderr == VISIBLE_STDERR
    common = _compose_prefix(launcher, files)
    calls = launcher.calls()
    assert [call["args"] for call in calls] == [
        [*common, "config", "--no-path-resolution", "--format", "json"],
        [*common, "pull", "--ignore-buildable"],
        [*common, "build"],
        [*common, "up", "-d", *arguments],
        [*common, "ps", "-a", "--format", "json", "bootstrap"],
        [*common, "ps", "--format", "json", "api"],
    ]
    for call in calls:
        assert call["cwd"] == str(launcher.root)
        assert call["project"] == "launcher-test"
        assert call["profiles"] == "sample"
    _assert_no_leak(launcher, result)
    assert not (launcher.root / "SHELL_EVALUATION_MARKER").exists()
    assert not (launcher.outside / "SHELL_EVALUATION_MARKER").exists()


def test_stage_lines_keep_their_order_around_compose_output(
    launcher: Launcher,
) -> None:
    result = launcher.run(_config())
    stages = [
        line for line in result.stdout.splitlines() if not line.startswith("COMPOSE_")
    ]
    assert stages == [
        CHECK_ENV,
        CHECK_KEY,
        SKIPPED,
        CHECK_CONFIG,
        "Downloading images.",
        "Building images. The first run takes several minutes.",
        "Starting services.",
        "OpenAI Compose services started.",
        SETUP_STAGE,
        API_STAGE,
        "FEWIA is ready at http://127.0.0.1:5173/prototype",
    ]


def test_ndjson_ps_output_is_understood(launcher: Launcher) -> None:
    result = launcher.run(_config(), extra={"FAKE_PS_STYLE": "lines"})
    assert result.returncode == 0
    assert result.stdout == _text(_stages())


def test_ready_line_uses_web_host_port_from_the_environment(
    launcher: Launcher,
) -> None:
    launcher.write_env(f"FEWIA_OPENAI_API_KEY={KEY_VALUE}", "WEB_HOST_PORT=9090")
    result = launcher.run(_config(), extra={"WEB_HOST_PORT": "8081"})
    ready = "FEWIA is ready at http://127.0.0.1:8081/prototype\n"
    assert result.stdout.endswith(ready)


@pytest.mark.parametrize(
    ("line", "port"),
    [
        ("WEB_HOST_PORT=9090", "9090"),
        ('WEB_HOST_PORT="9091" # comment', "9091"),
        ("WEB_HOST_PORT=", "5173"),
        ("WEB_HOST_PORT=not-a-port", "5173"),
    ],
)
def test_ready_line_uses_web_host_port_from_env_file(
    launcher: Launcher, line: str, port: str
) -> None:
    launcher.write_env(f"FEWIA_OPENAI_API_KEY={KEY_VALUE}", line)
    result = launcher.run(_config())
    assert result.returncode == 0
    ready = f"FEWIA is ready at http://127.0.0.1:{port}/prototype\n"
    assert result.stdout.endswith(ready)


@pytest.mark.parametrize(
    "lines",
    [
        [],
        ["OTHER=1"],
        ["FEWIA_OPENAI_API_KEY="],
        ["FEWIA_OPENAI_API_KEY=   "],
        ['FEWIA_OPENAI_API_KEY=""'],
        ["FEWIA_OPENAI_API_KEY='  '"],
        [f"# FEWIA_OPENAI_API_KEY={KEY_VALUE}"],
        ["FEWIA_OPENAI_API_KEY= # comment only"],
        [f"FEWIA_OPENAI_API_KEY={KEY_VALUE}", "FEWIA_OPENAI_API_KEY="],
    ],
)
def test_missing_or_blank_key_fails_before_docker(
    launcher: Launcher, lines: list[str]
) -> None:
    launcher.write_env("touch SHELL_EVALUATION_MARKER", *lines)
    _assert_key_missing(launcher, launcher.run(_config()))
    assert not (launcher.root / "SHELL_EVALUATION_MARKER").exists()


@pytest.mark.parametrize(
    "line",
    [
        f"export FEWIA_OPENAI_API_KEY={KEY_VALUE}",
        f"FEWIA_OPENAI_API_KEY = {KEY_VALUE}",
        f'FEWIA_OPENAI_API_KEY="{KEY_VALUE}"',
        f"FEWIA_OPENAI_API_KEY='{KEY_VALUE}'",
        f"export FEWIA_OPENAI_API_KEY = '{KEY_VALUE}' # comment",
        f"FEWIA_OPENAI_API_KEY={KEY_VALUE} # comment",
    ],
)
def test_accepted_env_file_key_forms_start(launcher: Launcher, line: str) -> None:
    launcher.write_env("touch SHELL_EVALUATION_MARKER", line)
    result = launcher.run(_config())
    assert result.returncode == 0
    assert result.stdout == _text(_stages())
    assert result.stderr == VISIBLE_STDERR
    assert len(launcher.calls()) == 6
    assert not (launcher.root / "SHELL_EVALUATION_MARKER").exists()


def test_last_matching_line_wins(launcher: Launcher) -> None:
    launcher.write_env("FEWIA_OPENAI_API_KEY=", f"FEWIA_OPENAI_API_KEY={KEY_VALUE}")
    assert launcher.run(_config()).returncode == 0


def test_key_only_in_process_environment_starts(launcher: Launcher) -> None:
    launcher.write_env("OTHER=1")
    launcher.environment["FEWIA_OPENAI_API_KEY"] = KEY_VALUE
    result = launcher.run(_config())
    assert result.returncode == 0
    assert result.stderr == VISIBLE_STDERR
    assert len(launcher.calls()) == 6


@pytest.mark.parametrize(
    "config",
    [
        _config(secret_environment="OTHER_KEY"),
        _config(worker_secrets=[]),
        _config(worker_secrets=[{"source": "other", "target": "openai_api_key"}]),
        _config(worker_secrets=[{"source": "openai_api_key", "target": "other"}]),
        _config(
            worker_secrets=[
                {"source": "openai_api_key", "target": "openai_api_key"},
                {"source": "openai_api_key", "target": SECRET_PATH},
            ]
        ),
        _config(api_secrets=[{"source": "openai_api_key", "target": "openai_api_key"}]),
        _config(api_secrets=["openai_api_key"]),
        _config(api_path="/run/fewia/openai-api-key"),
        _config(worker_path="/run/fewia/openai-api-key"),
        _config(api_path=""),
    ],
)
def test_invalid_secret_shapes_fail_before_up(
    launcher: Launcher, config: dict[str, object]
) -> None:
    _assert_rejected(launcher, launcher.run(config))


@pytest.mark.parametrize(
    "config",
    [
        _config(api_mode=None),
        _config(worker_mode=None),
        _config(api_mode="live"),
        _config(worker_mode="live"),
        _config(api_mode="", worker_mode=""),
    ],
)
def test_missing_or_wrong_kroger_mode_fails_before_up(
    launcher: Launcher, config: dict[str, object]
) -> None:
    _assert_rejected(launcher, launcher.run(config), KROGER_FIXTURE)


@pytest.mark.parametrize(
    "config",
    [
        _config(api_mode=None, worker_mode="live"),
        _config(api_mode="live", worker_mode=None),
        _config(api_mode="fixture", worker_mode="live"),
        _config(api_mode="live", worker_mode="fixture"),
        _config(api_mode="fixture", worker_mode="fixture"),
        _config(api_mode="", worker_mode=""),
    ],
)
def test_missing_or_wrong_kroger_mode_fails_in_live_launch(
    launcher: Launcher, config: dict[str, object]
) -> None:
    result = launcher.run(config, arguments=("--kroger-live",))
    _assert_rejected(launcher, result, KROGER_LIVE)


def test_live_mode_config_is_rejected_by_default_launch(launcher: Launcher) -> None:
    config = _config(api_mode="live", worker_mode="live")
    _assert_rejected(launcher, launcher.run(config), KROGER_FIXTURE)


def test_kroger_live_flag_only_counts_as_the_first_argument(
    launcher: Launcher,
) -> None:
    result = launcher.run(_config(), arguments=("--build", "--kroger-live"))
    assert result.returncode == 0
    up = launcher.calls()[3]["args"]
    assert "compose.kroger.yaml" not in up
    assert up[-3:] == ["-d", "--build", "--kroger-live"]


def test_real_kroger_overlay_switches_api_and_worker_to_live() -> None:
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load(COMPOSE_KROGER.read_text())
    for name in ("api", "worker"):
        environment = compose["services"][name]["environment"]
        assert environment["FEWIA_KROGER_MODE"] == "live"
        assert "FEWIA_KROGER_CLIENT_ID_FILE" in environment


def test_full_secret_target_path_is_accepted(launcher: Launcher) -> None:
    config = _config(
        worker_secrets=[{"source": "openai_api_key", "target": SECRET_PATH}]
    )
    assert launcher.run(config).returncode == 0


@pytest.mark.parametrize(
    "config",
    [None, [], {}, {"services": {}}, {"secrets": {}, "services": {}}],
)
def test_malformed_config_fails_closed(launcher: Launcher, config: object) -> None:
    _assert_rejected(launcher, launcher.run(config))


def test_invalid_json_fails_closed(launcher: Launcher) -> None:
    _assert_rejected(launcher, launcher.run(None, raw_config="PRIVATE_CONFIG_SENTINEL"))


def test_config_failure_does_not_start_services(launcher: Launcher) -> None:
    result = launcher.run(_config(), config_status=1)
    _assert_rejected(launcher, result, CONFIG)


@pytest.mark.parametrize("status", [1, 17])
def test_up_failure_reports_the_exit_code(launcher: Launcher, status: int) -> None:
    result = launcher.run(_config(), up_status=status)
    assert result.returncode != 0
    assert result.stdout == _text(_stages()[:10])
    assert result.stderr == (
        f"{VISIBLE_STDERR}{ERROR}Docker Compose up failed with exit code {status}. "
        "Run the same command without the launcher to see the Compose output.\n"
    )
    _assert_no_leak(launcher, result)
    assert len(launcher.calls()) == 4


@pytest.mark.parametrize(("name", "calls"), [("PULL", 2), ("BUILD", 3)])
def test_pull_or_build_failure_stops_before_up(
    launcher: Launcher, name: str, calls: int
) -> None:
    result = launcher.run(_config(), extra={f"FAKE_{name}_STATUS": "9"})
    assert result.returncode == 1
    assert result.stderr.endswith(
        f"{ERROR}Docker Compose {name.lower()} failed with exit code 9. "
        "See the output above.\n"
    )
    assert "Starting services." not in result.stdout
    assert len(launcher.calls()) == calls
    _assert_no_leak(launcher, result)


def test_failed_setup_stops_before_the_api_wait(launcher: Launcher) -> None:
    result = launcher.run(_config(), extra={"FAKE_BOOTSTRAP": "exited:3"})
    assert result.returncode == 1
    assert result.stdout == _text(_stages()[:12])
    assert result.stderr == f"{VISIBLE_STDERR}{ERROR}{SETUP_FAILED}\n"
    assert API_STAGE not in result.stdout
    assert len(launcher.calls()) == 5
    _assert_no_leak(launcher, result)


@pytest.mark.parametrize("state", ["running", "created", "none"])
def test_setup_timeout_stops_the_launch(launcher: Launcher, state: str) -> None:
    result = launcher.run(_config(), extra={"FAKE_BOOTSTRAP": state})
    assert result.returncode == 1
    assert result.stdout == _text(_stages()[:12])
    assert result.stderr == f"{VISIBLE_STDERR}{ERROR}{SETUP_FAILED}\n"
    polls = [call for call in launcher.calls() if "ps" in call["args"]]
    assert len(polls) >= 2
    _assert_no_leak(launcher, result)


@pytest.mark.parametrize("health", ["starting", "unhealthy"])
def test_api_health_timeout_stops_the_launch(launcher: Launcher, health: str) -> None:
    result = launcher.run(_config(), extra={"FAKE_API_HEALTH": health})
    assert result.returncode == 1
    assert result.stdout == _text(_stages()[:13])
    assert result.stderr == f"{VISIBLE_STDERR}{ERROR}{API_FAILED}\n"
    assert "FEWIA is ready" not in result.stdout
    _assert_no_leak(launcher, result)


def _restricted_path(launcher: Launcher, *names: str) -> None:
    tools = launcher.root.parent / "limited-bin"
    tools.mkdir()
    for name in names:
        found = shutil.which(name)
        assert found is not None
        (tools / name).symlink_to(found)
    launcher.environment["PATH"] = str(tools)


def _run_bare(launcher: Launcher) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    assert bash is not None
    return subprocess.run(
        [bash, str(launcher.root / "infra/openai/compose-up.sh")],
        cwd=launcher.outside,
        env=launcher.environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_missing_python_names_the_step(launcher: Launcher) -> None:
    _restricted_path(launcher, "dirname")
    result = _run_bare(launcher)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == (
        f"{ERROR}Install Python 3; the launcher validates the configuration with it.\n"
    )


def test_missing_env_file_fails_before_docker(launcher: Launcher) -> None:
    (launcher.root / ".env").unlink()
    result = launcher.run(_config())
    assert result.returncode != 0
    assert result.stdout == f"{CHECK_ENV}\n"
    assert result.stderr == (
        f"{ERROR}Create .env from .env.example and set FEWIA_OPENAI_API_KEY.\n"
    )
    assert not launcher.log.exists()


def test_missing_docker_names_the_step(launcher: Launcher) -> None:
    _restricted_path(launcher, "dirname", "python3")
    result = _run_bare(launcher)
    assert result.returncode != 0
    assert result.stdout == f"{CHECK_ENV}\n"
    assert result.stderr == f"{ERROR}Install Docker Desktop with Docker Compose.\n"


@pytest.mark.parametrize("from_environment", [True, False])
def test_accepted_key_is_sent_as_a_bearer_token(
    launcher: Launcher, models_server: _ModelsServer, from_environment: bool
) -> None:
    if from_environment:
        launcher.write_env("OTHER=1")
        launcher.environment["FEWIA_OPENAI_API_KEY"] = KEY_VALUE
    else:
        launcher.write_env(f'FEWIA_OPENAI_API_KEY="{KEY_VALUE}" # comment')
    result = launcher.run(_config(), extra=_key_check(models_server.url))
    assert result.returncode == 0
    assert result.stdout == _text(_stages("OpenAI key accepted."))
    assert models_server.requests == [("/v1/models", f"Bearer {KEY_VALUE}")]
    _assert_no_leak(launcher, result)


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_stops_before_any_docker_command(
    launcher: Launcher, models_server: _ModelsServer, status: int
) -> None:
    models_server.status = status
    result = launcher.run(_config(), extra=_key_check(models_server.url))
    assert result.returncode == 1
    assert result.stdout == _text([CHECK_ENV, CHECK_KEY])
    assert result.stderr == (
        f"{ERROR}OpenAI rejected FEWIA_OPENAI_API_KEY (HTTP {status}). "
        "Create a new key at https://platform.openai.com/api-keys and update .env.\n"
    )
    assert not launcher.log.exists()
    assert len(models_server.requests) == 1
    _assert_no_leak(launcher, result)


@pytest.mark.parametrize("status", [500, 429, 404, 302])
def test_other_statuses_continue_with_a_notice(
    launcher: Launcher, models_server: _ModelsServer, status: int
) -> None:
    models_server.status = status
    result = launcher.run(_config(), extra=_key_check(models_server.url))
    assert result.returncode == 0
    assert result.stdout == _text(
        _stages("Could not check the OpenAI key. Continuing.")
    )
    # A redirect is never followed, so the key cannot reach another host.
    assert len(models_server.requests) == 1
    _assert_no_leak(launcher, result)


def test_connection_refused_continues_with_a_notice(launcher: Launcher) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/v1/models"
    result = launcher.run(_config(), extra=_key_check(url))
    assert result.returncode == 0
    assert result.stdout == _text(
        _stages("Could not check the OpenAI key. Continuing.")
    )
    assert result.stderr == VISIBLE_STDERR
    _assert_no_leak(launcher, result)


def test_key_with_a_newline_never_reaches_the_output(
    launcher: Launcher, models_server: _ModelsServer
) -> None:
    secret = f"{KEY_VALUE}\nInjected: header"
    launcher.environment["FEWIA_OPENAI_API_KEY"] = secret
    result = launcher.run(_config(), extra=_key_check(models_server.url))
    assert result.returncode == 0
    assert "Could not check the OpenAI key. Continuing." in result.stdout
    assert models_server.requests == []
    _assert_no_leak(launcher, result)


def test_skip_flag_skips_the_key_check(
    launcher: Launcher, models_server: _ModelsServer
) -> None:
    models_server.status = 401
    extra = {**_key_check(models_server.url), "FEWIA_SKIP_KEY_CHECK": "1"}
    result = launcher.run(_config(), extra=extra)
    assert result.returncode == 0
    assert result.stdout == _text(_stages())
    assert models_server.requests == []


def _bad_urls(port: int) -> list[str]:
    return [
        "https://api.openai.com/v1/models",
        "http://localhost:1/v1/models",
        "http://127.0.0.1/v1/models",
        "http://127.0.0.1:@example.invalid/v1/models",
        "http://127.0.0.1:80@example.invalid/v1/models",
        "http://127.0.0.1:abc/v1/models",
        "http://127.0.0.1.example.invalid:80/v1/models",
        f"http://127.0.0.1:{port}@127.0.0.1:{port}/v1/models",
        f"HTTP://127.0.0.1:{port}/v1/models",
    ]


@pytest.mark.parametrize("skip", ["0", "1"])
def test_non_loopback_models_url_is_rejected_before_any_request(
    launcher: Launcher, models_server: _ModelsServer, skip: str
) -> None:
    port = models_server.server_address[1]
    for url in _bad_urls(port):
        launcher.log.unlink(missing_ok=True)
        extra = {**_key_check(url), "FEWIA_SKIP_KEY_CHECK": skip}
        result = launcher.run(_config(), extra=extra)
        assert result.returncode == 1, url
        assert result.stdout == _text([CHECK_ENV, CHECK_KEY]), url
        assert result.stderr == f"{ERROR}{URL_INVALID}\n", url
        assert not launcher.log.exists(), url
        _assert_no_leak(launcher, result)
    assert models_server.requests == []


def _load_launcher() -> dict[str, Any]:
    text = LAUNCHER.read_text()
    marker = "<<'PYTHON' || exit 1\n"
    start = text.index(marker) + len(marker)
    source = text[start : text.index("\nPYTHON\n", start)]
    namespace: dict[str, Any] = {"__name__": "launcher_under_test"}
    exec(compile(source, str(LAUNCHER), "exec"), namespace)
    return namespace


@pytest.mark.parametrize(
    ("environment", "lines", "expected"),
    [
        (None, [], "https://api.openai.com/v1/models"),
        ("us", [], "https://us.api.openai.com/v1/models"),
        ("global", [], "https://api.openai.com/v1/models"),
        (None, ["FEWIA_OPENAI_REGION=us"], "https://us.api.openai.com/v1/models"),
        (
            None,
            ['FEWIA_OPENAI_REGION="us" # comment'],
            "https://us.api.openai.com/v1/models",
        ),
        ("global", ["FEWIA_OPENAI_REGION=us"], "https://api.openai.com/v1/models"),
        ("US", [], "https://api.openai.com/v1/models"),
    ],
)
def test_models_url_follows_the_openai_region(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    environment: str | None,
    lines: list[str],
    expected: str,
) -> None:
    monkeypatch.delenv("FEWIA_OPENAI_MODELS_URL", raising=False)
    monkeypatch.delenv("FEWIA_OPENAI_REGION", raising=False)
    if environment is not None:
        monkeypatch.setenv("FEWIA_OPENAI_REGION", environment)
    (tmp_path / ".env").write_text("".join(f"{line}\n" for line in lines))
    assert _load_launcher()["models_url"](tmp_path) == expected


def test_real_compose_file_has_the_services_the_launcher_waits_for() -> None:
    yaml = pytest.importorskip("yaml")
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    assert services["bootstrap"]["restart"] == "no"
    assert "healthcheck" in services["api"]
    assert "WEB_HOST_PORT:-5173" in "".join(services["web"]["ports"])


def test_real_compose_file_mounts_the_secret_in_the_worker_only() -> None:
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load(COMPOSE.read_text())
    assert compose["secrets"]["openai_api_key"]["environment"] == (
        "FEWIA_OPENAI_API_KEY"
    )
    services = compose["services"]
    assert services["worker"]["secrets"] == [
        {"source": "openai_api_key", "target": "openai_api_key"}
    ]
    for name, service in services.items():
        if name != "worker":
            assert "secrets" not in service
    for name in ("api", "worker"):
        environment = services[name]["environment"]
        assert environment["FEWIA_OPENAI_API_KEY_FILE"] == SECRET_PATH
        assert environment["FEWIA_OPENAI_REGION"] == "${FEWIA_OPENAI_REGION:-global}"
        assert environment["FEWIA_KROGER_MODE"] == "fixture"
        assert environment["DATABASE_URL"].startswith("postgresql+psycopg://")


def test_real_compose_file_has_no_bedrock_or_global_endpoint() -> None:
    text = COMPOSE.read_text().lower()
    assert "bedrock" not in text
    assert "aws_endpoint_url:" not in text
