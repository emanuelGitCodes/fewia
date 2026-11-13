import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "compose.yaml"
DOCKERFILE = ROOT / "backend" / "Dockerfile"

BACKEND_SERVICES = ("bootstrap", "api", "worker", "sync-worker")
WRITABLE_ROOT_SERVICE = "worker"
OTHER_SERVICES = ("postgres", "floci", "web")
HARDENING_KEYS = ("user", "read_only", "cap_drop", "security_opt", "tmpfs")


@pytest.fixture
def local_state_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    path = ROOT / "backend/app/local_secret_state.py"
    name = "container_hardening_local_state"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _services() -> dict[str, dict[str, object]]:
    # safe_load resolves the `<<` merge keys of the x-backend anchor.
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return document["services"]


@pytest.mark.parametrize("name", BACKEND_SERVICES)
def test_backend_service_is_hardened(name: str) -> None:
    service = _services()[name]

    # The worker mounts an environment secret, so its root file system is writable.
    assert service["read_only"] is (name != WRITABLE_ROOT_SERVICE)
    assert service["user"] == (
        "${FEWIA_HOST_UID:?Run make up}:${FEWIA_HOST_GID:?Run make up}"
    )
    assert "ALL" in service["cap_drop"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert "/tmp" in service["tmpfs"]


def test_worker_is_the_only_backend_service_without_read_only_root() -> None:
    services = _services()

    writable = [
        name for name in BACKEND_SERVICES if services[name]["read_only"] is not True
    ]

    assert writable == [WRITABLE_ROOT_SERVICE]


@pytest.mark.parametrize("name", OTHER_SERVICES)
def test_other_service_has_no_hardening_keys(name: str) -> None:
    service = _services()[name]

    for key in HARDENING_KEYS:
        assert key not in service


def test_dockerfile_drops_root_after_last_run() -> None:
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    run_lines = [i for i, line in enumerate(lines) if line.startswith("RUN")]
    user_lines = [i for i, line in enumerate(lines) if line.strip() == "USER 1000:1000"]

    assert run_lines
    assert user_lines
    assert user_lines[-1] > run_lines[-1]


def test_dockerfile_disables_bytecode_writes() -> None:
    assert "PYTHONDONTWRITEBYTECODE=1" in DOCKERFILE.read_text(encoding="utf-8")


def test_local_state_rejects_root_before_creating_private_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local_state_module: ModuleType,
) -> None:
    monkeypatch.setattr(local_state_module.os, "getuid", lambda: 0)

    with pytest.raises(local_state_module.LocalStateError, match="nonroot host user"):
        local_state_module.prepare_local_state(tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_launcher_uses_validated_local_state_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    local_state_module: ModuleType,
) -> None:
    monkeypatch.setattr(local_state_module.os, "getuid", lambda: 12001)
    monkeypatch.setattr(local_state_module.os, "getgid", lambda: 12002)
    launcher = ROOT / "infra/openai/compose-up.sh"
    text = launcher.read_text(encoding="utf-8")
    marker = "<<'PYTHON' || exit 1\n"
    start = text.index(marker) + len(marker)
    source = ast.parse(text[start : text.index("\nPYTHON\n", start)])
    source.body = [
        node
        for node in source.body
        if not (
            isinstance(node, ast.ImportFrom) and node.module == "app.local_secret_state"
        )
    ]
    namespace: dict[str, Any] = {
        "__name__": "launcher_under_test",
        "prepare_local_state": local_state_module.prepare_local_state,
        "read_password": local_state_module.read_password,
        "read_private_file": local_state_module.read_private_file,
    }
    exec(compile(source, str(launcher), "exec"), namespace)
    (tmp_path / ".env").touch(mode=0o600)
    identities: list[tuple[str, str]] = []

    def run(command: list[str], *, env: dict[str, str], **kwargs: object) -> None:
        assert command[-4:] == ["config", "--no-path-resolution", "--format", "json"]
        identities.append((env["FEWIA_HOST_UID"], env["FEWIA_HOST_GID"]))
        raise RuntimeError("Stop before Docker.")

    namespace.update(
        os=SimpleNamespace(environ={"FEWIA_HOST_UID": "0", "FEWIA_HOST_GID": "0"}),
        sys=SimpleNamespace(argv=[str(launcher), str(tmp_path)]),
        subprocess=SimpleNamespace(run=run),
        key_is_set=lambda root: True,
        check_openai_key=lambda root: None,
        report_failure=lambda detail: 1,
    )

    assert namespace["main"]() == 1
    assert identities == [("12001", "12002")]
    environment = (tmp_path / ".env0600").read_text(encoding="utf-8").splitlines()
    assert "FEWIA_HOST_UID='12001'" in environment
    assert "FEWIA_HOST_GID='12002'" in environment
