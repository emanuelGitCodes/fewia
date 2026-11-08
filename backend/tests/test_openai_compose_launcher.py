"""Check the OpenAI Compose launcher with a local Docker stub."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[2] / "infra/openai/compose-up.sh"
ERROR = "OpenAI Compose launch failed.\n"
MOUNT = "The OpenAI key mount in compose.openai.yaml is not valid."
ABSOLUTE = "FEWIA_OPENAI_API_KEY_FILE MUST be an absolute path."
REGULAR = "FEWIA_OPENAI_API_KEY_FILE MUST name an existing regular file."
OUTSIDE = "FEWIA_OPENAI_API_KEY_FILE MUST be outside the repository."
CONFIG = (
    "Docker Compose could not read the configuration. Check that Docker is "
    "running and that FEWIA_OPENAI_API_KEY_FILE is set in .env."
)
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
    key: Path
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


@pytest.fixture
def launcher(tmp_path: Path) -> Launcher:
    root = tmp_path / "extracted source"
    scripts = root / "infra/openai"
    scripts.mkdir(parents=True)
    (scripts / "compose-up.sh").write_text(LAUNCHER.read_text())
    (root / "compose.yaml").write_text("services: {}\n")
    (root / "compose.openai.yaml").write_text("services: {}\n")
    (root / ".env").write_text("touch SHELL_EVALUATION_MARKER\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    key = outside / "key $(touch SHELL_EVALUATION_MARKER)"
    key.touch()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    docker = binaries / "docker"
    docker.write_text(f"#!{sys.executable}\n{FAKE_DOCKER}")
    docker.chmod(0o755)
    log = tmp_path / "docker-calls.jsonl"
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("COMPOSE_")
    }
    environment.update(
        PATH=f"{binaries}{os.pathsep}{os.environ['PATH']}",
        FAKE_LOG=str(log),
        COMPOSE_PROJECT_NAME="launcher-test",
        COMPOSE_PROFILES="sample",
        COMPOSE_FILE="unrelated.yaml",
    )
    return Launcher(root, outside, key, log, environment)


def _mount(source: Path | str, **changes: object) -> dict[str, object]:
    return {
        "type": "bind",
        "source": str(source),
        "target": "/run/fewia/openai-api-key",
        "read_only": True,
        **changes,
    }


def _config(api: object, worker: object | None = None) -> dict[str, object]:
    return {
        "services": {
            "api": {"volumes": [api]},
            "worker": {"volumes": [api if worker is None else worker]},
        },
        "private": "PRIVATE_CONFIG_SENTINEL",
    }


def _assert_rejected(
    launcher: Launcher, result: subprocess.CompletedProcess[str], detail: str = MOUNT
) -> None:
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == f"{ERROR}{detail}\n"
    assert "PRIVATE_" not in result.stderr
    assert str(launcher.key) not in result.stderr
    calls = launcher.calls()
    assert len(calls) == 1
    assert "config" in calls[0]["args"]


@pytest.mark.parametrize("from_root", [True, False])
@pytest.mark.parametrize("arguments", [(), ("--build", "api")])
def test_absolute_external_file_starts_with_the_validated_inputs(
    launcher: Launcher, from_root: bool, arguments: tuple[str, ...]
) -> None:
    result = launcher.run(
        _config(_mount(launcher.key)), from_root=from_root, arguments=arguments
    )
    assert result.returncode == 0
    assert result.stdout == "OpenAI Compose services started.\n"
    assert result.stderr == ""
    common = [
        "compose",
        "--env-file",
        ".env",
        "-f",
        "compose.yaml",
        "-f",
        "compose.openai.yaml",
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
    "kind",
    [
        "relative",
        "missing",
        "directory",
        "symlink",
        "internal",
        "internal_alias",
        "internal_traversal",
    ],
)
def test_unsafe_sources_fail_before_up(launcher: Launcher, kind: str) -> None:
    source: Path | str
    detail = REGULAR if kind in ("missing", "directory", "symlink") else OUTSIDE
    if kind == "relative":
        detail = ABSOLUTE
        source = os.path.relpath(launcher.key, launcher.root)
    elif kind == "missing":
        source = launcher.outside / "missing"
    elif kind == "directory":
        source = launcher.outside
    elif kind == "symlink":
        source = launcher.outside / "link"
        source.symlink_to(launcher.key)
    else:
        source = launcher.root / "internal-key"
        source.touch()
        if kind == "internal_alias":
            alias = launcher.outside / "source-alias"
            alias.symlink_to(launcher.root, target_is_directory=True)
            source = alias / "internal-key"
        elif kind == "internal_traversal":
            source = launcher.outside / ".." / launcher.root.name / "internal-key"
    _assert_rejected(launcher, launcher.run(_config(_mount(source))), detail)


def test_file_contents_do_not_need_read_access(launcher: Launcher) -> None:
    launcher.key.chmod(0)
    try:
        result = launcher.run(_config(_mount(launcher.key)))
    finally:
        launcher.key.chmod(0o600)
    assert result.returncode == 0
    assert len(launcher.calls()) == 2


@pytest.mark.parametrize("service", ["api", "worker"])
@pytest.mark.parametrize(
    "changes",
    [
        {"type": "volume"},
        {"read_only": False},
        {"read_only": "true"},
        {"target": "/wrong-target"},
        {"source": None},
        {"source": 123},
    ],
)
def test_each_service_requires_a_read_only_key_bind(
    launcher: Launcher, service: str, changes: dict[str, object]
) -> None:
    valid = _mount(launcher.key)
    invalid = {**valid, **changes}
    config = _config(invalid, valid) if service == "api" else _config(valid, invalid)
    _assert_rejected(launcher, launcher.run(config))


def test_services_cannot_mount_different_files(launcher: Launcher) -> None:
    other = launcher.outside / "other-key"
    other.touch()
    config = _config(_mount(launcher.key), _mount(other))
    _assert_rejected(launcher, launcher.run(config))


@pytest.mark.parametrize(
    "config",
    [None, [], {}, {"services": {}}, {"services": {"api": {"volumes": [None]}}}],
)
def test_malformed_config_fails_closed(launcher: Launcher, config: object) -> None:
    _assert_rejected(launcher, launcher.run(config))


def test_duplicate_key_mounts_fail_closed(launcher: Launcher) -> None:
    mount = _mount(launcher.key)
    config = {
        "services": {
            "api": {"volumes": [mount, mount]},
            "worker": {"volumes": [mount]},
        }
    }
    _assert_rejected(launcher, launcher.run(config))


def test_invalid_json_fails_closed(launcher: Launcher) -> None:
    _assert_rejected(launcher, launcher.run(None, raw_config="PRIVATE_CONFIG_SENTINEL"))


def test_config_failure_does_not_start_services(launcher: Launcher) -> None:
    result = launcher.run(_config(_mount(launcher.key)), config_status=1)
    _assert_rejected(launcher, result, CONFIG)


@pytest.mark.parametrize("status", [1, 17])
def test_up_failure_hides_provider_output(launcher: Launcher, status: int) -> None:
    result = launcher.run(_config(_mount(launcher.key)), up_status=status)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == (
        f"{ERROR}Docker Compose up failed with exit code {status}. "
        "Run the same command without the launcher to see the Compose output.\n"
    )
    assert "PRIVATE_" not in result.stderr
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
        f"{ERROR}Install Python 3; the launcher validates the key path with it.\n"
    )


def test_missing_env_file_fails_before_docker(launcher: Launcher) -> None:
    (launcher.root / ".env").unlink()
    result = launcher.run(_config(_mount(launcher.key)))
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == (
        f"{ERROR}Create .env from .env.example and set FEWIA_OPENAI_API_KEY_FILE.\n"
    )
    assert not launcher.log.exists()


def test_missing_docker_names_the_step(launcher: Launcher) -> None:
    _restricted_path(launcher, "dirname", "python3")
    result = _run_bare(launcher)
    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr == f"{ERROR}Install Docker Desktop with Docker Compose.\n"
