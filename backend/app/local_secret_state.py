"""Private files for the local Compose stack."""

import base64
import os
import re
import secrets
import stat
import string
from dataclasses import dataclass
from pathlib import Path

PASSWORD_PATTERN = re.compile(r"[A-Za-z0-9]{32}\Z")


class LocalStateError(ValueError):
    """The local state is unsafe or invalid."""


def read_private_file(path: Path) -> str:
    """Read a regular file with mode 0600 without following a symlink."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise LocalStateError("Unsafe local state file.")
            value = stream.read(4097)
        if len(value) > 4096:
            raise LocalStateError("Invalid local state file.")
        return value
    except (OSError, UnicodeError) as error:
        raise LocalStateError("Cannot read local state file.") from error


def read_password(path: Path) -> str:
    value = read_private_file(path).strip()
    if PASSWORD_PATTERN.fullmatch(value) is None:
        raise LocalStateError("Invalid local database password file.")
    return value


def _create_private_file(path: Path, value: str) -> None:
    try:
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
    except FileExistsError:
        return
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(value)


@dataclass(frozen=True)
class LocalState:
    admin: Path
    runtime: Path
    pairing: Path
    environment: Path
    uid: int
    gid: int


def prepare_local_state(root: Path) -> LocalState:
    """Create private local credentials without replacing existing files."""
    uid, gid = os.getuid(), os.getgid()
    if uid == 0:
        raise LocalStateError("Run the local stack as a nonroot host user.")
    directory = root / ".fewia-state"
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise LocalStateError("Unsafe local state directory.")
    state = LocalState(
        directory / "database-admin-password",
        directory / "database-runtime-password",
        directory / "kroger-pairing-key",
        root / ".env0600",
        uid,
        gid,
    )
    alphabet = string.ascii_letters + string.digits
    for path in (state.admin, state.runtime):
        _create_private_file(path, "".join(secrets.choice(alphabet) for _ in range(32)))
        read_password(path)
    _create_private_file(
        state.pairing, base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    )
    pairing = read_private_file(state.pairing).strip()
    try:
        decoded = base64.b64decode(pairing, altchars=b"-_", validate=True)
    except ValueError as error:
        raise LocalStateError("Invalid local pairing key file.") from error
    if len(decoded) != 32:
        raise LocalStateError("Invalid local pairing key file.")
    entries = {
        "FEWIA_LOCAL_ADMIN_PASSWORD_FILE": str(state.admin),
        "FEWIA_LOCAL_RUNTIME_PASSWORD_FILE": str(state.runtime),
        "FEWIA_LOCAL_PAIRING_KEY_FILE": str(state.pairing),
        "FEWIA_HOST_UID": str(uid),
        "FEWIA_HOST_GID": str(gid),
    }
    if any(any(char in value for char in "\n\r'\\") for value in entries.values()):
        raise LocalStateError("Unsupported local state path.")
    content = "".join(f"{name}='{value}'\n" for name, value in entries.items())
    _create_private_file(state.environment, content)
    if read_private_file(state.environment) != content:
        raise LocalStateError("Local environment paths or host identity changed.")
    return state
