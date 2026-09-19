import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from infra.bedrock_runtime_validation import (
    ERROR_MESSAGE,
    PROFILE,
    default_credential_path,
    validate_checkout,
    validate_runtime_credentials,
    validated_environment,
)

ACCESS = "AKIAFAKEACCESSKEYTEST01"
SECRET = "fakeSecretAccessKeyValueForTests01"
TOKEN = "fakeSessionTokenForTests01"
SENTINEL_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_CONFIG_FILE",
    "AWS_ENDPOINT_URL",
    "FEWIA_AWS_PROFILE",
    "FEWIA_BEDROCK_ROLE_ARN",
    "FEWIA_BEDROCK_MFA_SERIAL",
    "FEWIA_BEDROCK_CREDENTIALS_FILE",
)


def _ini(
    *,
    access: str = ACCESS,
    secret: str = SECRET,
    extra: str = "",
    header: str = PROFILE,
) -> str:
    return (
        f"[{header}]\n"
        f"aws_access_key_id = {access}\n"
        f"aws_secret_access_key = {secret}\n"
        f"{extra}"
    )


def _write_private(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _checkout(tmp_path: Path) -> Path:
    checkout = tmp_path.resolve() / "repo"
    checkout.mkdir()
    (checkout / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    return checkout


def _outside(tmp_path: Path, body: str | None = None) -> Path:
    path = tmp_path.resolve() / "outside" / "runtime-credentials"
    return _write_private(path, body if body is not None else _ini())


def _reject(
    checkout: Path,
    credential_path: Path,
    *,
    source_root: Path | None = None,
) -> None:
    kwargs: dict[str, Path] = {}
    if source_root is not None:
        kwargs["source_root"] = source_root
    with pytest.raises((RuntimeError, ValueError), match=re.escape(ERROR_MESSAGE)):
        validate_runtime_credentials(checkout, credential_path, **kwargs)


def _git_env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "GIT_AUTHOR_NAME": "FEWIA Test",
        "GIT_AUTHOR_EMAIL": "fewia-test@example.invalid",
        "GIT_COMMITTER_NAME": "FEWIA Test",
        "GIT_COMMITTER_EMAIL": "fewia-test@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _run_git(home: Path, cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=_git_env(home),
        shell=False,
    )


def _init_repo(home: Path, root: Path) -> Path:
    root.mkdir()
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    _run_git(home, root, "init", "--initial-branch=main")
    _run_git(home, root, "config", "user.name", "FEWIA Test")
    _run_git(home, root, "config", "user.email", "fewia-test@example.invalid")
    _run_git(home, root, "add", "compose.yaml")
    _run_git(home, root, "commit", "-m", "init")
    return root


def _source_repo(tmp_path: Path) -> Path:
    home = tmp_path.resolve() / "git-home"
    home.mkdir()
    return _init_repo(home, tmp_path.resolve() / "source")


def test_relative_and_inside_checkout_rejected(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    _reject(checkout, Path("runtime-credentials"))
    _reject(checkout, Path(".config/fewia/bedrock/runtime-credentials"))
    inside = checkout / "nested" / "runtime-credentials"
    _write_private(inside, _ini())
    _reject(checkout, inside)


def test_inside_source_root_rejected(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    source = tmp_path.resolve() / "source"
    source.mkdir()
    (source / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    nested = source / "nested" / "runtime-credentials"
    _write_private(nested, _ini())
    _reject(checkout, nested, source_root=source)


def test_symlink_checkout_rejects_credentials_in_real_root(tmp_path: Path) -> None:
    real = _checkout(tmp_path)
    link = tmp_path.resolve() / "link-checkout"
    link.symlink_to(real)
    nested = real / "nested" / "runtime-credentials"
    _write_private(nested, _ini())
    _reject(link, nested)


def test_symlink_file_and_ancestor_rejected(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    base = tmp_path.resolve()
    real_dir = base / "real"
    real_dir.mkdir()
    os.chmod(real_dir, 0o700)
    real = _write_private(real_dir / "runtime-credentials", _ini())
    link_dir = base / "links"
    link_dir.mkdir()
    os.chmod(link_dir, 0o700)
    linked = link_dir / "runtime-credentials"
    linked.symlink_to(real)
    _reject(checkout, linked)

    target_dir = base / "target"
    target_dir.mkdir()
    os.chmod(target_dir, 0o700)
    link_parent = base / "alias"
    link_parent.symlink_to(target_dir)
    nested = link_parent / "nested"
    nested.mkdir()
    os.chmod(nested, 0o700)
    ancestor_path = nested / "runtime-credentials"
    _write_private(ancestor_path, _ini())
    _reject(checkout, ancestor_path)


def test_group_world_and_wrong_owner_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout(tmp_path)
    path = _outside(tmp_path)
    os.chmod(path, 0o640)
    _reject(checkout, path)
    os.chmod(path, 0o644)
    _reject(checkout, path)
    os.chmod(path, 0o600)
    os.chmod(path.parent, 0o750)
    _reject(checkout, path)
    os.chmod(path.parent, 0o700)
    uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    _reject(checkout, path)


def test_default_session_extra_blank_and_malformed_rejected(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    defaulted = (
        "[DEFAULT]\nregion = us-east-1\n"
        f"[{PROFILE}]\naws_access_key_id = {ACCESS}\n"
        f"aws_secret_access_key = {SECRET}\n"
    )
    _reject(checkout, _outside(tmp_path, defaulted))
    _reject(checkout, _outside(tmp_path, _ini(header="default")))
    _reject(
        checkout,
        _outside(tmp_path, _ini(extra=f"aws_session_token = {TOKEN}\n")),
    )
    _reject(
        checkout,
        _outside(tmp_path, _ini(extra="[other]\naws_access_key_id = x\n")),
    )
    _reject(checkout, _outside(tmp_path, _ini(access="  ")))
    _reject(checkout, _outside(tmp_path, _ini(secret="")))
    _reject(checkout, _outside(tmp_path, f"[{PROFILE}\naws_access_key_id = {ACCESS}\n"))
    missing = tmp_path.resolve() / "missing-parent" / "runtime-credentials"
    _reject(checkout, missing)


def test_parser_errors_omit_secret_values(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    path = _outside(tmp_path, _ini(extra=f"aws_session_token = {TOKEN}\n"))
    with pytest.raises((RuntimeError, ValueError)) as exc:
        validate_runtime_credentials(checkout, path)
    message = str(exc.value)
    assert message == ERROR_MESSAGE
    assert ACCESS not in message
    assert SECRET not in message
    assert TOKEN not in message


def test_valid_private_file_sets_absolute_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout(tmp_path)
    path = _outside(tmp_path)
    evil = tmp_path.resolve() / "evil-credentials"
    evil.write_text("leak\n", encoding="utf-8")
    monkeypatch.setenv("FEWIA_RUNTIME_CREDENTIALS_FILE", str(evil))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOST_PORT", "8080")
    monkeypatch.setenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    for name in SENTINEL_VARS:
        monkeypatch.setenv(name, f"sentinel-{name}")
    env = validated_environment(checkout, path)
    assert env["FEWIA_RUNTIME_CREDENTIALS_FILE"] == str(path)
    assert path.is_absolute()
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOST_PORT"] == "8080"
    assert env["DOCKER_HOST"] == "unix:///var/run/docker.sock"
    for name in SENTINEL_VARS:
        assert name not in env
    assert ACCESS not in env.values()
    assert SECRET not in env.values()
    assert TOKEN not in env.values()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    home = tmp_path.resolve() / "home"
    default = home / ".config" / "fewia" / "bedrock" / "runtime-credentials"
    _write_private(default, _ini())
    monkeypatch.setattr(Path, "home", lambda *_args: home)
    assert default_credential_path() == default
    home_env = validated_environment(checkout)
    assert home_env["FEWIA_RUNTIME_CREDENTIALS_FILE"] == str(default)
    for name in SENTINEL_VARS:
        assert name not in home_env


def test_source_checkout_and_same_worktree_accepted(tmp_path: Path) -> None:
    source = _source_repo(tmp_path)
    home = tmp_path.resolve() / "git-home"
    worktree = tmp_path.resolve() / "worktree"
    _run_git(home, source, "worktree", "add", str(worktree), "HEAD")
    assert validate_checkout(source, source_root=source) == source
    assert validate_checkout(worktree, source_root=source) == worktree
    link = tmp_path.resolve() / "worktree-link"
    link.symlink_to(worktree)
    assert validate_checkout(link, source_root=source) == worktree


def test_unrelated_nongit_and_subdir_checkout_rejected(tmp_path: Path) -> None:
    source = _source_repo(tmp_path)
    home = tmp_path.resolve() / "git-home"
    other = _init_repo(home, tmp_path.resolve() / "other")
    with pytest.raises((RuntimeError, ValueError), match=re.escape(ERROR_MESSAGE)):
        validate_checkout(other, source_root=source)
    plain = tmp_path.resolve() / "plain"
    plain.mkdir()
    (plain / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    with pytest.raises((RuntimeError, ValueError), match=re.escape(ERROR_MESSAGE)):
        validate_checkout(plain, source_root=source)
    nested = source / "nested"
    nested.mkdir()
    (nested / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    with pytest.raises((RuntimeError, ValueError), match=re.escape(ERROR_MESSAGE)):
        validate_checkout(nested, source_root=source)


def test_git_dir_and_worktree_env_cannot_spoof_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _source_repo(tmp_path)
    home = tmp_path.resolve() / "git-home"
    worktree = tmp_path.resolve() / "worktree"
    _run_git(home, source, "worktree", "add", str(worktree), "HEAD")
    fake = tmp_path.resolve() / "malicious"
    fake.mkdir()
    (fake / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    monkeypatch.setenv("GIT_DIR", str(source / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(fake))
    with pytest.raises((RuntimeError, ValueError), match=re.escape(ERROR_MESSAGE)):
        validate_checkout(fake, source_root=source)
    assert validate_checkout(worktree, source_root=source) == worktree
