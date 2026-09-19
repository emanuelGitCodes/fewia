import getpass
import importlib
import os
import stat
import sys
import warnings
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from infra.bedrock_session import (
    DEFAULT_SOURCE_PROFILE,
    DEST_PROFILE,
    DURATION_SECONDS,
    ERROR_MESSAGE,
    SESSION_NAME,
    SessionRefreshError,
    main,
    prompt_mfa_token,
    refresh_session,
)

ACCOUNT = "123456789012"
ROLE = f"arn:aws:iam::{ACCOUNT}:role/FewiaBedrockDev-chat"
MFA = f"arn:aws:iam::{ACCOUNT}:mfa/device"
USER = f"arn:aws:iam::{ACCOUNT}:user/dev"
TOKEN = "123456"
ACCESS = "ASIAEXAMPLEKEYID01"
SECRET = "wJalEXAMPLESECRETKEY"
SESSION = "FwoGZXIvYXdzEXAMPLETOKEN"


def _expiry(*, seconds: int = 3300) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=seconds)


class FakeSts:
    def __init__(
        self,
        *,
        account: str = ACCOUNT,
        user_arn: str = USER,
        credentials: Mapping[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.account = account
        self.user_arn = user_arn
        self.credentials = credentials
        self.error = error
        self.assume_kwargs: dict[str, object] | None = None

    def get_caller_identity(self) -> dict[str, object]:
        return {"Account": self.account, "Arn": self.user_arn}

    def assume_role(self, **kwargs: object) -> dict[str, object]:
        self.assume_kwargs = dict(kwargs)
        if self.error is not None:
            raise self.error
        blob: Mapping[str, object] = self.credentials or {
            "AccessKeyId": ACCESS,
            "SecretAccessKey": SECRET,
            "SessionToken": SESSION,
            "Expiration": _expiry(),
        }
        return {"Credentials": blob}


def _prompt(_message: str) -> str:
    return TOKEN


def _dest(tmp_path: Path, *parts: str) -> Path:
    return tmp_path.resolve().joinpath(*parts)


def _refresh(
    path: Path,
    sts: FakeSts | None = None,
    *,
    role_arn: str = ROLE,
    mfa_serial: str = MFA,
) -> str:
    return refresh_session(
        role_arn=role_arn,
        mfa_serial=mfa_serial,
        token_code=TOKEN,
        credentials_path=path,
        sts_client=sts or FakeSts(),
    )


def test_valid_request_writes_private_ini(tmp_path: Path) -> None:
    path = _dest(tmp_path, "fewia", "bedrock", "credentials")
    sts = FakeSts()
    stamp = _refresh(path, sts)
    datetime.fromisoformat(stamp)
    assert sts.assume_kwargs == {
        "RoleArn": ROLE,
        "RoleSessionName": SESSION_NAME,
        "DurationSeconds": DURATION_SECONDS,
        "SerialNumber": MFA,
        "TokenCode": TOKEN,
    }
    text = path.read_text(encoding="utf-8")
    assert text.startswith(f"[{DEST_PROFILE}]\n")
    assert f"aws_access_key_id = {ACCESS}\n" in text
    assert f"aws_secret_access_key = {SECRET}\n" in text
    assert f"aws_session_token = {SESSION}\n" in text
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.parent.stat().st_mode) == 0o700


def test_cross_account_and_bad_identity_rejected(tmp_path: Path) -> None:
    path = _dest(tmp_path, "credentials")
    other = "999999999999"
    cross = FakeSts(
        account=other,
        user_arn=f"arn:aws:iam::{other}:user/dev",
    )
    with pytest.raises(SessionRefreshError):
        _refresh(path, cross)
    assert cross.assume_kwargs is None
    with pytest.raises(SessionRefreshError):
        _refresh(path, role_arn=f"arn:aws:iam::{ACCOUNT}:role/Admin")
    with pytest.raises(SessionRefreshError):
        _refresh(
            path,
            role_arn=f"arn:aws:iam::{ACCOUNT}:role/FewiaBedrockDev-admin",
        )
    with pytest.raises(SessionRefreshError):
        _refresh(path, mfa_serial=f"arn:aws:iam::{ACCOUNT}:user/device")
    with pytest.raises(SessionRefreshError):
        _refresh(path, mfa_serial=f"arn:aws:iam::{other}:mfa/device")
    assert not path.exists()


def test_mfa_code_not_echoed_and_getpass_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _dest(tmp_path, "bedrock", "credentials")
    code = main(
        ["--role-arn", ROLE, "--mfa-serial", MFA],
        token_prompt=_prompt,
        sts_client=FakeSts(),
        credentials_path=path,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    with pytest.raises(SystemExit) as help_exit:
        main(["--help"])
    help_text = capsys.readouterr().out
    assert help_exit.value.code == 0
    assert "--token-code" not in help_text
    assert "--role-arn" in help_text

    def echo(_prompt: str) -> str:
        warnings.warn("echo", getpass.GetPassWarning, stacklevel=2)
        return TOKEN

    monkeypatch.setattr("infra.bedrock_session.getpass.getpass", echo)
    with pytest.raises(SessionRefreshError):
        prompt_mfa_token("MFA token: ")


def test_malformed_credentials_and_expiration_rejected(tmp_path: Path) -> None:
    path = _dest(tmp_path, "bedrock", "credentials")
    cases: list[Mapping[str, object]] = [
        {
            "AccessKeyId": "ASIA\nKEY",
            "SecretAccessKey": SECRET,
            "SessionToken": SESSION,
            "Expiration": _expiry(),
        },
        {
            "AccessKeyId": ACCESS,
            "SecretAccessKey": SECRET,
            "SessionToken": SESSION,
            "Expiration": datetime.now(UTC).replace(tzinfo=None)
            + timedelta(seconds=60),
        },
        {
            "AccessKeyId": ACCESS,
            "SecretAccessKey": SECRET,
            "SessionToken": SESSION,
            "Expiration": "not-a-timestamp",
        },
        {
            "AccessKeyId": ACCESS,
            "SecretAccessKey": SECRET,
            "SessionToken": SESSION,
            "Expiration": "2020-01-01T00:00:00+00:00",
        },
        {
            "AccessKeyId": ACCESS,
            "SecretAccessKey": SECRET,
            "SessionToken": SESSION,
            "Expiration": "2099-01-01T00:00:00",
        },
        {
            "AccessKeyId": ACCESS,
            "SecretAccessKey": SECRET,
            "SessionToken": SESSION,
            "Expiration": datetime.now(UTC) + timedelta(hours=2),
        },
    ]
    for blob in cases:
        sts = FakeSts(credentials=blob)
        with pytest.raises(SessionRefreshError):
            _refresh(path, sts)
        assert not path.exists()


def test_symlink_ancestor_and_target_refused(tmp_path: Path) -> None:
    base = tmp_path.resolve()
    real = base / "real"
    real.mkdir()
    os.chmod(real, 0o700)
    link = base / "link"
    link.symlink_to(real)
    nested = link / "nested"
    nested.mkdir()
    os.chmod(nested, 0o700)
    ancestor = FakeSts()
    ancestor_path = nested / "credentials"
    with pytest.raises(SessionRefreshError):
        _refresh(ancestor_path, ancestor)
    assert ancestor.assume_kwargs is None
    assert not ancestor_path.exists()
    assert not (real / "nested" / "credentials").exists()

    directory = base / "bedrock"
    directory.mkdir()
    os.chmod(directory, 0o700)
    target = base / "outside"
    target.write_text("keep\n", encoding="utf-8")
    path = directory / "credentials"
    path.symlink_to(target)
    linked = FakeSts()
    with pytest.raises(SessionRefreshError):
        _refresh(path, linked)
    assert linked.assume_kwargs is None
    assert path.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep\n"


def test_unsafe_existing_dir_refused_without_permission_mutation(
    tmp_path: Path,
) -> None:
    directory = _dest(tmp_path, "bedrock")
    directory.mkdir()
    os.chmod(directory, 0o755)
    before = stat.S_IMODE(directory.stat().st_mode)
    path = directory / "credentials"
    sts = FakeSts()
    with pytest.raises(SessionRefreshError):
        _refresh(path, sts)
    assert sts.assume_kwargs is None
    assert stat.S_IMODE(directory.stat().st_mode) == before
    assert not path.exists()


def test_unrelated_profile_preserved(tmp_path: Path) -> None:
    directory = _dest(tmp_path, "bedrock")
    directory.mkdir()
    os.chmod(directory, 0o700)
    path = directory / "credentials"
    original = "[other]\naws_access_key_id = old\n"
    path.write_text(original, encoding="utf-8")
    os.chmod(path, 0o600)
    sts = FakeSts()
    with pytest.raises(SessionRefreshError):
        _refresh(path, sts)
    assert sts.assume_kwargs is None
    assert path.read_text(encoding="utf-8") == original


def test_atomic_failure_preserves_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _dest(tmp_path, "bedrock")
    directory.mkdir()
    os.chmod(directory, 0o700)
    path = directory / "credentials"
    original = f"[{DEST_PROFILE}]\naws_access_key_id = old\n"
    path.write_text(original, encoding="utf-8")
    os.chmod(path, 0o600)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(SessionRefreshError):
        _refresh(path)
    assert path.read_text(encoding="utf-8") == original
    assert list(directory.glob(".credentials-*")) == []


def test_provider_exception_secrets_not_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _dest(tmp_path, "bedrock", "credentials")
    leak = "secret=ASIA_SHOULD_NOT_PRINT"
    code = main(
        ["--role-arn", ROLE, "--mfa-serial", MFA],
        token_prompt=_prompt,
        sts_client=FakeSts(error=RuntimeError(leak)),
        credentials_path=path,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.strip() == ERROR_MESSAGE
    assert leak not in captured.out
    assert leak not in captured.err
    assert not path.exists()


def test_import_has_no_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path.resolve()
    monkeypatch.setenv("HOME", str(home))
    sys.modules.pop("infra.bedrock_session", None)
    importlib.import_module("infra.bedrock_session")
    assert DEFAULT_SOURCE_PROFILE == "aws-admin"
    assert not (home / ".config" / "fewia" / "bedrock" / "credentials").exists()
