import base64
import os
import stat
from pathlib import Path

import pytest

from app.local_secret_state import (
    LocalStateError,
    prepare_local_state,
    read_password,
    read_private_file,
)


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getuid", lambda: 12345)
    monkeypatch.setattr(os, "getgid", lambda: 23456)


@pytest.mark.usefixtures("host")
def test_generates_private_credentials_and_preserves_them(tmp_path: Path) -> None:
    state = prepare_local_state(tmp_path)
    admin, runtime = read_password(state.admin), read_password(state.runtime)
    assert admin != runtime
    assert len(base64.urlsafe_b64decode(read_private_file(state.pairing))) == 32
    assert stat.S_IMODE(state.admin.parent.stat().st_mode) == 0o700
    for path in (state.admin, state.runtime, state.pairing, state.environment):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    environment = read_private_file(state.environment)
    assert "FEWIA_HOST_UID='12345'" in environment
    assert "FEWIA_HOST_GID='23456'" in environment
    for secret in (admin, runtime, read_private_file(state.pairing)):
        assert secret not in environment
        assert secret not in repr(state)
    assert prepare_local_state(tmp_path) == state
    assert read_password(state.admin) == admin
    assert read_password(state.runtime) == runtime


def test_rejects_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getuid", lambda: 0)
    with pytest.raises(LocalStateError, match="nonroot"):
        prepare_local_state(tmp_path)
    assert not (tmp_path / ".fewia-state").exists()


@pytest.mark.usefixtures("host")
@pytest.mark.parametrize("mode", [0o755, 0o777, 0o750, 0o1700])
def test_rejects_unsafe_directory(tmp_path: Path, mode: int) -> None:
    directory = tmp_path / ".fewia-state"
    directory.mkdir()
    directory.chmod(mode)
    with pytest.raises(LocalStateError):
        prepare_local_state(tmp_path)
    assert list(directory.iterdir()) == []


@pytest.mark.usefixtures("host")
def test_rejects_symlink_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    (tmp_path / ".fewia-state").symlink_to(target, target_is_directory=True)
    with pytest.raises(LocalStateError):
        prepare_local_state(tmp_path)
    assert list(target.iterdir()) == []


@pytest.mark.parametrize("mode", [0o644, 0o666, 0o400, 0o1600])
def test_rejects_unsafe_file_mode(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "secret"
    path.write_text("A" * 32)
    path.chmod(mode)
    with pytest.raises(LocalStateError):
        read_password(path)


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_rejects_nonregular_files(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "secret"
    if kind == "symlink":
        target = tmp_path / "target"
        target.write_text("A" * 32)
        target.chmod(0o600)
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir(mode=0o600)
    else:
        os.mkfifo(path, 0o600)
    with pytest.raises(LocalStateError):
        read_private_file(path)


@pytest.mark.parametrize("value", ["", "A" * 31, "A" * 33, "'" * 32, "ä" * 32])
def test_rejects_invalid_password(tmp_path: Path, value: str) -> None:
    path = tmp_path / "secret"
    path.write_text(value)
    path.chmod(0o600)
    with pytest.raises(LocalStateError):
        read_password(path)


@pytest.mark.usefixtures("host")
@pytest.mark.parametrize(
    "name",
    [
        "database-admin-password",
        "database-runtime-password",
        "kroger-pairing-key",
        ".env0600",
    ],
)
def test_rejects_existing_unsafe_state(tmp_path: Path, name: str) -> None:
    state = prepare_local_state(tmp_path)
    path = state.environment if name == ".env0600" else state.admin.parent / name
    path.chmod(0o644)
    with pytest.raises(LocalStateError):
        prepare_local_state(tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


@pytest.mark.usefixtures("host")
def test_rejects_changed_env_without_overwriting(tmp_path: Path) -> None:
    state = prepare_local_state(tmp_path)
    state.environment.write_text("FEWIA_HOST_UID='0'\n")
    with pytest.raises(LocalStateError):
        prepare_local_state(tmp_path)
    assert read_private_file(state.environment) == "FEWIA_HOST_UID='0'\n"


@pytest.mark.usefixtures("host")
def test_file_owner_mapping_does_not_block_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapped_uid = tmp_path.stat().st_uid + 1
    monkeypatch.setattr(os, "getuid", lambda: mapped_uid)
    state = prepare_local_state(tmp_path)
    assert state.admin.stat().st_uid != state.uid
    assert read_password(state.admin)
