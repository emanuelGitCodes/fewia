from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "compose.yaml"
DOCKERFILE = ROOT / "backend" / "Dockerfile"

BACKEND_SERVICES = ("bootstrap", "api", "worker", "sync-worker")
WRITABLE_ROOT_SERVICE = "worker"
OTHER_SERVICES = ("postgres", "floci", "web")
HARDENING_KEYS = ("user", "read_only", "cap_drop", "security_opt", "tmpfs")


def _services() -> dict[str, dict[str, object]]:
    # safe_load resolves the `<<` merge keys of the x-backend anchor.
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return document["services"]


@pytest.mark.parametrize("name", BACKEND_SERVICES)
def test_backend_service_is_hardened(name: str) -> None:
    service = _services()[name]

    # The worker mounts an environment secret, so its root file system is writable.
    assert service["read_only"] is (name != WRITABLE_ROOT_SERVICE)
    assert service["user"] == "1000:1000"
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
