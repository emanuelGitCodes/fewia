import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from infra.bedrock_runtime import compose_command, main
from infra.bedrock_runtime_validation import (
    ERROR_MESSAGE as LAUNCHER_ERROR_MESSAGE,
)
from infra.bedrock_runtime_validation import (
    SOURCE_ROOT,
)
from infra.spoonacular_runtime_validation import (
    ERROR_MESSAGE,
    validate_spoonacular_credentials,
)

ACCESS = "AKIAFAKEACCESSKEYTEST01"
SECRET = "fakeSecretAccessKeyValueForTests01"
SENTINEL = "SPOONACULAR_TEST_MARKER_VALUE"
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
SPOONACULAR_VARS = (
    "FEWIA_SPOONACULAR_KEY",
    "FEWIA_SPOONACULAR_KEY_FILE",
    "FEWIA_SPOONACULAR_CREDENTIALS_FILE",
)
SPOONACULAR_OVERRIDE = str(SOURCE_ROOT / "compose.spoonacular.yaml")
BEDROCK_OVERRIDE = str(SOURCE_ROOT / "compose.bedrock-runtime.yaml")


def _ini() -> str:
    return (
        "[fewia-bedrock-runtime]\n"
        f"aws_access_key_id = {ACCESS}\n"
        f"aws_secret_access_key = {SECRET}\n"
    )


def _write_private(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o600)
    path.parent.chmod(0o700)
    return path


def _checkout(tmp_path: Path) -> Path:
    checkout = tmp_path.resolve() / "repo"
    checkout.mkdir()
    (checkout / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    return checkout


def _outside_key(tmp_path: Path, body: str = SENTINEL) -> Path:
    return _write_private(tmp_path.resolve() / "outside" / "spoonacular-key", body)


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
        validate_spoonacular_credentials(checkout, credential_path, **kwargs)


def _boom(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("subprocess ran")


def _bind_aws(
    checkout: Path,
    aws_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run: object,
) -> None:
    def fake_checkout(value: Path, source_root: Path = SOURCE_ROOT) -> Path:
        del source_root
        assert Path(value).resolve() == checkout
        return checkout

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("infra.bedrock_runtime.validate_checkout", fake_checkout)
    monkeypatch.setattr(
        "infra.bedrock_runtime.default_credential_path", lambda: aws_path
    )


def test_compose_command_default_matches_two_argument_form(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    project = "fewia-grocery-b7d4"
    assert compose_command(checkout, project) == compose_command(
        checkout, project, False
    )
    cmd = compose_command(checkout, project)
    assert SPOONACULAR_OVERRIDE not in cmd
    assert cmd.count("-f") == 2
    assert cmd[cmd.index("-f") + 1] == str(checkout / "compose.yaml")
    assert cmd[cmd.index("-f", cmd.index("-f") + 1) + 1] == BEDROCK_OVERRIDE
    assert cmd[-2:] == ["api", "worker"]
    assert "--no-deps" in cmd
    assert "--force-recreate" in cmd


def test_cli_without_flag_strips_inherited_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout = _checkout(tmp_path)
    aws_path = _write_private(
        tmp_path.resolve() / "outside" / "runtime-credentials", _ini()
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, dict(kwargs)))
        return subprocess.CompletedProcess(cmd, 0)

    _bind_aws(checkout, aws_path, monkeypatch, fake_run)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    for name in SENTINEL_VARS:
        monkeypatch.setenv(name, f"sentinel-{name}")
    for name in SPOONACULAR_VARS:
        monkeypatch.setenv(name, SENTINEL)
    code = main(["--checkout", str(checkout), "--project", "fewia-grocery-b7d4"])
    captured = capsys.readouterr()
    assert code == 0
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == compose_command(checkout, "fewia-grocery-b7d4")
    assert SPOONACULAR_OVERRIDE not in cmd
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert env["FEWIA_RUNTIME_CREDENTIALS_FILE"] == str(aws_path)
    for name in SPOONACULAR_VARS:
        assert name not in env
    for name in SENTINEL_VARS:
        assert name not in env
    assert SENTINEL not in env.values()
    assert SENTINEL not in cmd
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err
    assert ACCESS not in env.values()
    assert SECRET not in env.values()


def test_cli_valid_flag_adds_override_and_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout = _checkout(tmp_path)
    aws_path = _write_private(
        tmp_path.resolve() / "outside" / "runtime-credentials", _ini()
    )
    key_path = _outside_key(tmp_path)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, dict(kwargs)))
        return subprocess.CompletedProcess(cmd, 0)

    _bind_aws(checkout, aws_path, monkeypatch, fake_run)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    for name in SENTINEL_VARS:
        monkeypatch.setenv(name, f"sentinel-{name}")
    monkeypatch.setenv("FEWIA_SPOONACULAR_KEY", SENTINEL)
    monkeypatch.setenv("FEWIA_SPOONACULAR_KEY_FILE", SENTINEL)
    monkeypatch.setenv("FEWIA_SPOONACULAR_CREDENTIALS_FILE", SENTINEL)
    argv = [
        "--checkout",
        str(checkout),
        "--project",
        "fewia-grocery-b7d4",
        "--spoonacular-key-file",
        str(key_path),
    ]
    code = main(argv)
    captured = capsys.readouterr()
    assert code == 0
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == compose_command(checkout, "fewia-grocery-b7d4", True)
    assert SPOONACULAR_OVERRIDE in cmd
    files = [cmd[i + 1] for i, part in enumerate(cmd) if part == "-f"]
    assert files == [
        str(checkout / "compose.yaml"),
        BEDROCK_OVERRIDE,
        SPOONACULAR_OVERRIDE,
    ]
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert env["FEWIA_RUNTIME_CREDENTIALS_FILE"] == str(aws_path)
    assert env["FEWIA_SPOONACULAR_CREDENTIALS_FILE"] == str(key_path.resolve())
    assert "FEWIA_SPOONACULAR_KEY" not in env
    assert "FEWIA_SPOONACULAR_KEY_FILE" not in env
    assert SENTINEL not in env.values()
    assert SENTINEL not in cmd
    assert SENTINEL not in argv
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err
    for name in SENTINEL_VARS:
        assert name not in env
    assert ACCESS not in env.values()
    assert SECRET not in env.values()
    assert kwargs["shell"] is False
    assert cmd[-2:] == ["api", "worker"]


def test_relative_missing_symlink_repo_and_insecure_fail_before_docker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout = _checkout(tmp_path)
    aws_path = _write_private(
        tmp_path.resolve() / "outside" / "runtime-credentials", _ini()
    )
    _bind_aws(checkout, aws_path, monkeypatch, _boom)
    base = tmp_path.resolve()
    missing = base / "missing-parent" / "spoonacular-key"
    empty = _outside_key(tmp_path, "")
    oversize = _write_private(base / "big" / "spoonacular-key", "x" * 8193)
    inside = checkout / "nested" / "spoonacular-key"
    _write_private(inside, SENTINEL)
    source = base / "source"
    source.mkdir()
    (source / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    nested_source = source / "nested" / "spoonacular-key"
    _write_private(nested_source, SENTINEL)
    real_dir = base / "real"
    real_dir.mkdir()
    os.chmod(real_dir, 0o700)
    real = _write_private(real_dir / "spoonacular-key", SENTINEL)
    link_dir = base / "links"
    link_dir.mkdir()
    os.chmod(link_dir, 0o700)
    linked = link_dir / "spoonacular-key"
    linked.symlink_to(real)
    target_dir = base / "target"
    target_dir.mkdir()
    os.chmod(target_dir, 0o700)
    link_parent = base / "alias"
    link_parent.symlink_to(target_dir)
    nested = link_parent / "nested"
    nested.mkdir()
    os.chmod(nested, 0o700)
    ancestor_path = nested / "spoonacular-key"
    _write_private(ancestor_path, SENTINEL)
    group_file = _write_private(base / "group" / "spoonacular-key", SENTINEL)
    os.chmod(group_file, 0o640)
    world_parent = _write_private(base / "world" / "spoonacular-key", SENTINEL)
    os.chmod(world_parent.parent, 0o750)
    no_read = _write_private(base / "noread" / "spoonacular-key", SENTINEL)
    os.chmod(no_read, 0o000)
    owned = _write_private(base / "owner" / "spoonacular-key", SENTINEL)

    def reject(flag: str) -> None:
        code = main(
            [
                "--checkout",
                str(checkout),
                "--project",
                "fewia-grocery-b7d4",
                "--spoonacular-key-file",
                flag,
            ]
        )
        captured = capsys.readouterr()
        assert code == 1
        assert captured.err.strip() == LAUNCHER_ERROR_MESSAGE
        assert flag not in captured.out
        assert flag not in captured.err
        assert SENTINEL not in captured.out
        assert SENTINEL not in captured.err
        assert ACCESS not in captured.out
        assert SECRET not in captured.out
        assert ACCESS not in captured.err
        assert SECRET not in captured.err

    reject("relative-key")
    reject(str(missing))
    reject(str(empty))
    reject(str(oversize))
    reject(str(inside))
    reject(str(linked))
    reject(str(ancestor_path))
    reject(str(group_file))
    reject(str(world_parent))
    reject(str(no_read))
    _reject(checkout, nested_source, source_root=source)
    _reject(checkout, no_read)
    uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: uid + 1)
    _reject(checkout, owned)


def test_cli_subprocess_errors_print_static_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout = _checkout(tmp_path)
    aws_path = _write_private(
        tmp_path.resolve() / "outside" / "runtime-credentials", _ini()
    )
    key_path = _outside_key(tmp_path)
    leak = f"{SENTINEL} {key_path} key-text"
    argv = [
        "--checkout",
        str(checkout),
        "--project",
        "fewia-grocery-b7d4",
        "--spoonacular-key-file",
        str(key_path),
    ]

    def raise_runtime(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(leak)

    def raise_value(*_args: object, **_kwargs: object) -> None:
        raise ValueError(leak)

    _bind_aws(checkout, aws_path, monkeypatch, raise_runtime)
    for run in (raise_runtime, raise_value):
        monkeypatch.setattr(subprocess, "run", run)
        code = main(argv)
        captured = capsys.readouterr()
        assert code == 1
        assert captured.err.strip() == LAUNCHER_ERROR_MESSAGE
        assert captured.out == ""
        assert leak not in captured.err
        assert SENTINEL not in captured.out
        assert SENTINEL not in captured.err
        assert str(key_path) not in captured.out
        assert str(key_path) not in captured.err
        assert ACCESS not in captured.out
        assert SECRET not in captured.out
        assert ACCESS not in captured.err
        assert SECRET not in captured.err


def test_validator_accepts_private_canonical_file(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    path = _outside_key(tmp_path)
    assert validate_spoonacular_credentials(checkout, path) == path.resolve()
    assert path.is_absolute()
    assert not path.is_symlink()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    owner_read = _write_private(
        tmp_path.resolve() / "owner-read" / "spoonacular-key", SENTINEL
    )
    os.chmod(owner_read, 0o400)
    assert (
        validate_spoonacular_credentials(checkout, owner_read) == owner_read.resolve()
    )
    assert stat.S_IMODE(owner_read.stat().st_mode) == 0o400
    limit = _write_private(tmp_path.resolve() / "limit" / "spoonacular-key", "x" * 8192)
    assert validate_spoonacular_credentials(checkout, limit) == limit.resolve()


def test_spoonacular_compose_api_only_readonly_bind() -> None:
    path = SOURCE_ROOT / "compose.spoonacular.yaml"
    text = path.read_text(encoding="utf-8")
    assert "  api:" in text
    assert "  worker:" not in text
    assert "sync-worker" not in text
    assert "FEWIA_SPOONACULAR_KEY_FILE: /run/fewia/spoonacular-key" in text
    launcher = "FEWIA_SPOONACULAR_CREDENTIALS_FILE:?Use the validated runtime launcher"
    assert launcher in text
    assert "target: /run/fewia/spoonacular-key" in text
    assert "read_only: true" in text
    assert "create_host_path: false" in text
    assert "FEWIA_SPOONACULAR_KEY:" not in text
    loaded: object
    try:
        import yaml
    except ImportError:
        return
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict)
    services = loaded.get("services")
    assert isinstance(services, dict)
    assert list(services.keys()) == ["api"]
    api = services["api"]
    assert isinstance(api, dict)
    assert api.get("environment") == {
        "FEWIA_SPOONACULAR_KEY_FILE": "/run/fewia/spoonacular-key"
    }
    volumes = api.get("volumes")
    assert isinstance(volumes, list)
    assert len(volumes) == 1
    volume = volumes[0]
    assert isinstance(volume, dict)
    assert volume.get("read_only") is True
    assert volume.get("target") == "/run/fewia/spoonacular-key"
    source = volume.get("source")
    assert isinstance(source, str)
    assert launcher in source
    bind = volume.get("bind")
    assert isinstance(bind, dict)
    assert bind.get("create_host_path") is False
