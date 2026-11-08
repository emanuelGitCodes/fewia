"""Check the OpenAI Compose launcher with a local Docker stub."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

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
FAKE_DOCKER = """\
import json
import os
from pathlib import Path
import sys

with Path(os.environ["FAKE_LOG"]).open("a") as log:
    log.write(json.dumps({
        "args": sys.argv[1:],
        "cwd": os.getcwd(),
        "project": os.environ.get("COMPOSE_PROJECT_NAME"),
        "profiles": os.environ.get("COMPOSE_PROFILES"),
    }) + "\\n")
print("PRIVATE_ERROR_SENTINEL", file=sys.stderr)
if "config" in sys.argv:
    print(os.environ["FAKE_CONFIG"])
    sys.exit(int(os.environ["FAKE_CONFIG_STATUS"]))
print("PRIVATE_UP_SENTINEL")
sys.exit(int(os.environ["FAKE_UP_STATUS"]))
"""


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
    ) -> subprocess.CompletedProcess[str]:
        environment = {
            **self.environment,
            "FAKE_CONFIG": json.dumps(config) if raw_config is None else raw_config,
            "FAKE_CONFIG_STATUS": str(config_status),
            "FAKE_UP_STATUS": str(up_status),
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

    def calls(self) -> list[dict[str, object]]:
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
        if not name.startswith("COMPOSE_") and name != "FEWIA_OPENAI_API_KEY"
    }
    environment.update(
        PATH=f"{binaries}{os.pathsep}{os.environ['PATH']}",
        FAKE_LOG=str(log),
        COMPOSE_PROJECT_NAME="launcher-test",
        COMPOSE_PROFILES="sample",
        COMPOSE_FILE="unrelated.yaml",
    )
    return Launcher(root, outside, log, environment)


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


def _assert_no_leak(result: subprocess.CompletedProcess[str]) -> None:
    for output in (result.stdout, result.stderr):
        assert "PRIVATE_" not in output
        assert KEY_VALUE not in output


def _assert_rejected(
    launcher: Launcher,
    result: subprocess.CompletedProcess[str],
    detail: str = SECRET,
) -> None:
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == f"{ERROR}{detail}\n"
    _assert_no_leak(result)
    calls = launcher.calls()
    assert len(calls) == 1
    assert "config" in calls[0]["args"]


def _assert_key_missing(
    launcher: Launcher, result: subprocess.CompletedProcess[str]
) -> None:
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == f"{ERROR}{KEY_MISSING}\n"
    _assert_no_leak(result)
    assert not launcher.log.exists()


@pytest.mark.parametrize("from_root", [True, False])
@pytest.mark.parametrize("arguments", [(), ("--build", "api")])
@pytest.mark.parametrize("live", [False, True])
def test_valid_config_starts_with_the_validated_inputs(
    launcher: Launcher, from_root: bool, arguments: tuple[str, ...], live: bool
) -> None:
    mode = "live" if live else "fixture"
    files = ["-f", "compose.yaml"]
    if live:
        files += ["-f", "compose.kroger.yaml"]
    result = launcher.run(
        _config(api_mode=mode, worker_mode=mode),
        from_root=from_root,
        arguments=(("--kroger-live",) if live else ()) + arguments,
    )
    assert result.returncode == 0
    assert result.stdout == "OpenAI Compose services started.\n"
    assert result.stderr == ""
    common = [
        "compose",
        "--env-file",
        ".env",
        *files,
        "--project-directory",
        str(launcher.root),
    ]
    calls = launcher.calls()
    assert [call["args"] for call in calls] == [
        [*common, "config", "--no-path-resolution", "--format", "json"],
        [*common, "up", *(arguments or ("-d", "--build"))],
    ]
    for call in calls:
        assert call["cwd"] == str(launcher.root)
        assert call["project"] == "launcher-test"
        assert call["profiles"] == "sample"
    assert not (launcher.root / "SHELL_EVALUATION_MARKER").exists()
    assert not (launcher.outside / "SHELL_EVALUATION_MARKER").exists()


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
    assert result.stdout == "OpenAI Compose services started.\n"
    assert result.stderr == ""
    assert len(launcher.calls()) == 2
    assert not (launcher.root / "SHELL_EVALUATION_MARKER").exists()


def test_last_matching_line_wins(launcher: Launcher) -> None:
    launcher.write_env("FEWIA_OPENAI_API_KEY=", f"FEWIA_OPENAI_API_KEY={KEY_VALUE}")
    assert launcher.run(_config()).returncode == 0


def test_key_only_in_process_environment_starts(launcher: Launcher) -> None:
    launcher.write_env("OTHER=1")
    launcher.environment["FEWIA_OPENAI_API_KEY"] = KEY_VALUE
    result = launcher.run(_config())
    assert result.returncode == 0
    assert result.stderr == ""
    assert len(launcher.calls()) == 2


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
    up = launcher.calls()[1]["args"]
    assert "compose.kroger.yaml" not in up
    assert up[-2:] == ["--build", "--kroger-live"]


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
def test_up_failure_hides_provider_output(launcher: Launcher, status: int) -> None:
    result = launcher.run(_config(), up_status=status)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == (
        f"{ERROR}Docker Compose up failed with exit code {status}. "
        "Run the same command without the launcher to see the Compose output.\n"
    )
    _assert_no_leak(result)
    assert len(launcher.calls()) == 2


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
    assert result.stdout == ""
    assert result.stderr == (
        f"{ERROR}Create .env from .env.example and set FEWIA_OPENAI_API_KEY.\n"
    )
    assert not launcher.log.exists()


def test_missing_docker_names_the_step(launcher: Launcher) -> None:
    _restricted_path(launcher, "dirname", "python3")
    result = _run_bare(launcher)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == f"{ERROR}Install Docker Desktop with Docker Compose.\n"


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
