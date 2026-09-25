import argparse
import getpass
import os
import re
import stat
import sys
import tempfile
import warnings
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol, TextIO, cast

import boto3  # type: ignore[import-untyped]

DEFAULT_SOURCE_PROFILE = "aws-admin"
DEST_PROFILE = "fewia-bedrock-dev"
DURATION_SECONDS = 3600
CLOCK_SKEW_SECONDS = 300
ERROR_MESSAGE = "Unable to refresh the Bedrock session."
SESSION_NAME = "fewia-development-chat"
_HELP = (
    "Write a one-hour fewia-bedrock-dev session to "
    "~/.config/fewia/bedrock/credentials. The API and worker MUST "
    "restart after renewal. This helper does not refresh a running process."
)
_MFA = re.compile(r"^arn:aws:iam::(\d{12}):mfa/[A-Za-z0-9+=,.@_/-]+$")
_ROLE = re.compile(
    r"^arn:aws:iam::(\d{12}):role/(FewiaBedrockDev-[A-Za-z0-9+=,.@_-]+)$"
)
_USER = re.compile(r"^arn:aws:iam::(\d{12}):user/.+$")
_PROFILE_HEADER = f"[{DEST_PROFILE}]"
_BLOCKED_ROLE_SUFFIXES = frozenset({"admin", "administrator", "poweruser"})


class SessionRefreshError(Exception):
    def __init__(self) -> None:
        super().__init__(ERROR_MESSAGE)


class StsClient(Protocol):
    def get_caller_identity(self) -> Mapping[str, object]: ...
    def assume_role(self, **kwargs: object) -> Mapping[str, object]: ...


def validate_mfa_token(token: object) -> str:
    if not isinstance(token, str) or re.fullmatch(r"\d{6}", token) is None:
        raise SessionRefreshError()
    return token


def prompt_mfa_token(prompt: str) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise SessionRefreshError() from None


def _credential_text(value: object) -> str:
    if not isinstance(value, str):
        raise SessionRefreshError()
    text = value.strip()
    if not text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise SessionRefreshError()
    return text


def _parse_expiration(raw: object, *, now: datetime) -> str:
    parsed: datetime
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            raise SessionRefreshError()
        parsed = raw.astimezone(UTC)
    elif isinstance(raw, str):
        stamp = _credential_text(raw)
        try:
            parsed = datetime.fromisoformat(stamp)
        except ValueError:
            raise SessionRefreshError() from None
        if parsed.tzinfo is None:
            raise SessionRefreshError()
        parsed = parsed.astimezone(UTC)
    else:
        raise SessionRefreshError()
    latest = now + timedelta(seconds=DURATION_SECONDS + CLOCK_SKEW_SECONDS)
    if parsed <= now or parsed > latest:
        raise SessionRefreshError()
    return parsed.isoformat()


def _reject_symlink_ancestors(path: Path) -> None:
    if path.is_symlink():
        raise SessionRefreshError()
    cursor = path.parent
    while True:
        if cursor.is_symlink():
            raise SessionRefreshError()
        parent = cursor.parent
        if parent == cursor:
            return
        cursor = parent


def _require_private_dir(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir():
        raise SessionRefreshError()
    info = directory.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise SessionRefreshError()


def _prepare_directory(directory: Path) -> None:
    if directory.exists():
        _require_private_dir(directory)
        return
    missing: list[Path] = []
    cursor = directory
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            raise SessionRefreshError()
        cursor = parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise SessionRefreshError()
    for item in reversed(missing):
        try:
            os.mkdir(item, 0o700)
            os.chmod(item, 0o700)
        except OSError:
            raise SessionRefreshError() from None
    _require_private_dir(directory)


def _require_dedicated_credentials(path: Path) -> None:
    if not path.exists():
        return
    try:
        info = path.lstat()
    except OSError:
        raise SessionRefreshError() from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
    ):
        raise SessionRefreshError()
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        raise SessionRefreshError() from None
    for line in existing.splitlines():
        stripped = line.strip()
        if (
            stripped.startswith("[")
            and stripped.endswith("]")
            and stripped != _PROFILE_HEADER
        ):
            raise SessionRefreshError()


def _atomic_write(path: Path, directory: Path, payload: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".credentials-", dir=directory)
    tmp_path = Path(tmp)
    handle: TextIO | None = None
    try:
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8")
        fd = -1
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(tmp_path, path)
    except OSError:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        elif fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        tmp_path.unlink(missing_ok=True)
        raise SessionRefreshError() from None


def refresh_session(
    *,
    role_arn: str,
    mfa_serial: str,
    token_code: str,
    source_profile: str = DEFAULT_SOURCE_PROFILE,
    credentials_path: Path | None = None,
    sts_client: StsClient | None = None,
) -> str:
    token = validate_mfa_token(token_code)
    if not source_profile.strip():
        raise SessionRefreshError()
    client = sts_client or cast(
        StsClient, boto3.Session(profile_name=source_profile).client("sts")
    )

    def match(pattern: re.Pattern[str], value: object) -> re.Match[str] | None:
        if not isinstance(value, str) or "*" in value:
            return None
        return pattern.fullmatch(value)

    ident = client.get_caller_identity()
    user = match(_USER, ident.get("Arn"))
    serial = match(_MFA, mfa_serial)
    role = match(_ROLE, role_arn)
    account = ident.get("Account")
    suffix = role.group(2).removeprefix("FewiaBedrockDev-") if role else ""
    if not (
        isinstance(account, str)
        and user
        and user.group(1) == account
        and serial
        and serial.group(1) == account
        and role
        and role.group(1) == account
        and suffix
        and suffix.lower() not in _BLOCKED_ROLE_SUFFIXES
    ):
        raise SessionRefreshError()
    path = credentials_path or (
        Path.home() / ".config" / "fewia" / "bedrock" / "credentials"
    )
    _reject_symlink_ancestors(path)
    directory = path.parent
    _prepare_directory(directory)
    _require_dedicated_credentials(path)
    blob = client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=SESSION_NAME,
        DurationSeconds=DURATION_SECONDS,
        SerialNumber=mfa_serial,
        TokenCode=token,
    ).get("Credentials")
    if not isinstance(blob, Mapping):
        raise SessionRefreshError()
    access = _credential_text(blob.get("AccessKeyId"))
    secret = _credential_text(blob.get("SecretAccessKey"))
    sess = _credential_text(blob.get("SessionToken"))
    stamp = _parse_expiration(blob.get("Expiration"), now=datetime.now(UTC))
    payload = (
        f"{_PROFILE_HEADER}\naws_access_key_id = {access}\n"
        f"aws_secret_access_key = {secret}\naws_session_token = {sess}\n"
    )
    _atomic_write(path, directory, payload)
    return stamp


def main(
    argv: Sequence[str] | None = None,
    *,
    token_prompt: Callable[[str], str] = prompt_mfa_token,
    sts_client: StsClient | None = None,
    credentials_path: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=_HELP)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--mfa-serial", required=True)
    parser.add_argument("--source-profile", default=DEFAULT_SOURCE_PROFILE)
    try:
        args = parser.parse_args(None if argv is None else list(argv))
        expiration = refresh_session(
            role_arn=args.role_arn,
            mfa_serial=args.mfa_serial,
            token_code=token_prompt("MFA token: "),
            source_profile=args.source_profile,
            credentials_path=credentials_path,
            sts_client=sts_client,
        )
    except Exception:  # noqa: BLE001
        print(ERROR_MESSAGE, file=sys.stderr)
        return 1
    print(f"Wrote {DEST_PROFILE} credentials. Expires {expiration}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
