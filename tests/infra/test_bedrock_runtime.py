import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2]))

from infra.bedrock_runtime import (
    compose_command,
    main,
)
from infra.bedrock_runtime_validation import (
    ERROR_MESSAGE,
    SOURCE_ROOT,
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


def test_cli_compose_uses_fixed_override_without_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout = _checkout(tmp_path)
    path = _write_private(
        tmp_path.resolve() / "outside" / "runtime-credentials", _ini()
    )
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((cmd, dict(kwargs)))
        return subprocess.CompletedProcess(cmd, 0)

    def fake_checkout(value: Path, source_root: Path = SOURCE_ROOT) -> Path:
        del source_root
        assert Path(value).resolve() == checkout
        return checkout

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("infra.bedrock_runtime.validate_checkout", fake_checkout)
    monkeypatch.setattr("infra.bedrock_runtime.default_credential_path", lambda: path)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOST_PORT", "8080")
    for name in SENTINEL_VARS:
        monkeypatch.setenv(name, f"sentinel-{name}")
    code = main(["--checkout", str(checkout), "--project", "fewia-grocery-b7d4"])
    captured = capsys.readouterr()
    assert code == 0
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == compose_command(checkout, "fewia-grocery-b7d4")
    assert kwargs["shell"] is False
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert env["FEWIA_RUNTIME_CREDENTIALS_FILE"] == str(path)
    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOST_PORT"] == "8080"
    for name in SENTINEL_VARS:
        assert name not in env
    assert ACCESS not in env.values()
    assert SECRET not in env.values()
    assert ACCESS not in cmd
    assert SECRET not in cmd
    assert ACCESS not in captured.out
    assert SECRET not in captured.out
    assert ACCESS not in captured.err
    assert SECRET not in captured.err
    assert cmd[-2:] == ["api", "worker"]
    assert "sync-worker" not in cmd
    assert "--no-deps" in cmd
    assert "--force-recreate" in cmd
    override = str(SOURCE_ROOT / "compose.bedrock-runtime.yaml")
    assert cmd[cmd.index("-f") + 1] == str(checkout / "compose.yaml")
    assert cmd[cmd.index("-f", cmd.index("-f") + 1) + 1] == override
    assert cmd[1:6] == [
        "compose",
        "--project-directory",
        str(checkout),
        "-p",
        "fewia-grocery-b7d4",
    ]


def test_cli_skips_subprocess_when_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout = _checkout(tmp_path)
    path = _write_private(
        tmp_path.resolve() / "outside" / "runtime-credentials",
        _ini() + f"aws_session_token = {TOKEN}\n",
    )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("subprocess ran")

    def fake_checkout(value: Path, source_root: Path = SOURCE_ROOT) -> Path:
        del value, source_root
        return checkout

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr("infra.bedrock_runtime.validate_checkout", fake_checkout)
    monkeypatch.setattr("infra.bedrock_runtime.default_credential_path", lambda: path)
    code = main(["--checkout", str(checkout), "--project", "fewia-grocery-b7d4"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.err.strip() == ERROR_MESSAGE
    assert ACCESS not in captured.out
    assert SECRET not in captured.out
    assert TOKEN not in captured.out
    assert ACCESS not in captured.err
    assert SECRET not in captured.err
    assert TOKEN not in captured.err
    for project in ("Fewia", "-fewia"):
        assert main(["--checkout", str(checkout), f"--project={project}"]) == 1
    monkeypatch.undo()
    monkeypatch.setattr(subprocess, "run", boom)
    empty = tmp_path.resolve() / "empty"
    empty.mkdir()
    assert main(["--checkout", str(empty), "--project", "fewia"]) == 1


def test_override_yaml_pins_runtime_profile() -> None:
    text = (SOURCE_ROOT / "compose.bedrock-runtime.yaml").read_text(encoding="utf-8")
    assert "FEWIA_AWS_PROFILE: fewia-bedrock-runtime" in text
    assert "${FEWIA_AWS_PROFILE}" not in text
    assert "FEWIA_BEDROCK_MODEL_ID: us.amazon.nova-2-lite-v1:0" in text
    assert "FEWIA_BEDROCK_REGION: us-east-1" in text
    assert "FEWIA_RUNTIME_CREDENTIALS_FILE:?Use the validated runtime launcher" in text
    assert "create_host_path: false" in text
    assert "read_only: true" in text
    assert "AWS_ACCESS_KEY_ID" not in text
    assert "AWS_SECRET_ACCESS_KEY" not in text
    assert "AWS_SESSION_TOKEN" not in text
    assert "  api:" in text
    assert "  worker:" in text
    assert "sync-worker" not in text
