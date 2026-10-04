import importlib
import json
import subprocess
import sys
import traceback
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import pytest

import preflight_cli as cli
from deployment_config import DeploymentConfig, RuntimeConfig
from preflight_checks import PreflightError

_MARKER = "SYNTHETIC_PRIVATE_INPUT"
_ACCOUNT = "111122223333"
_PROFILE = "test-profile_1.example"
_CERTIFICATE = (
    f"arn:aws:acm:us-east-1:{_ACCOUNT}:certificate/12345678-1234-abcd-1234-123456789abc"
)
_CLUSTER = f"arn:aws:ecs:us-east-1:{_ACCOUNT}:cluster/fewia-dev"
_TASK = f"arn:aws:ecs:us-east-1:{_ACCOUNT}:task/fewia-dev/" + "a" * 32
_DIGEST = "sha256:" + "b" * 64
_BASE = ["--region=us-east-1", "--output=json", "--no-cli-pager"]
_COMMANDS = [
    ["aws", "sts", "get-caller-identity", *_BASE],
    ["aws", "acm", "describe-certificate", *_BASE, f"--certificate-arn={_CERTIFICATE}"],
    [
        "aws",
        "cloudformation",
        "describe-stacks",
        *_BASE,
        "--stack-name=FewiaHostedDemoDev",
    ],
    [
        "aws",
        "ecr",
        "describe-images",
        *_BASE,
        f"--registry-id={_ACCOUNT}",
        "--repository-name=fewia/backend",
        f"--image-ids=imageDigest={_DIGEST}",
    ],
    [
        "aws",
        "ecs",
        "describe-tasks",
        *_BASE,
        f"--cluster={_CLUSTER}",
        f"--tasks={_TASK}",
    ],
]
_ENVIRONMENT = {
    "PATH": "/synthetic/bin",
    "AWS_PAGER": "synthetic-pager",
    "AWS_CLI_AUTO_PROMPT": "on",
    "UNRELATED_TEST_VALUE": "retained",
}


class _Process:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.stdout = json.dumps({"Account": _ACCOUNT}).encode()
        self.returncode = 0
        self.error: BaseException | None = None

    def __call__(
        self, arguments: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((arguments.copy(), kwargs))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(
            arguments, self.returncode, self.stdout, _MARKER.encode()
        )


@pytest.fixture(autouse=True)
def process(monkeypatch: pytest.MonkeyPatch) -> _Process:
    spy = _Process()
    monkeypatch.setattr(cli.subprocess, "run", spy)
    monkeypatch.setattr(cli.os, "environ", _ENVIRONMENT.copy())
    return spy


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / f"{_MARKER}.json"
    path.write_text(json.dumps(asdict(_config())), encoding="utf-8")
    return path


def _config(
    phase: Literal["foundation", "bootstrap", "active"] = "foundation",
) -> DeploymentConfig:
    runtime = RuntimeConfig(
        "app.example.test", "fewia-dev", _CERTIFICATE, _DIGEST, _DIGEST
    )
    return DeploymentConfig(_ACCOUNT, phase, None if phase == "foundation" else runtime)


def _arguments(path: Path, profile: str = _PROFILE) -> list[str]:
    return ["--config", str(path), "--profile", profile]


def _assert_status(capsys: pytest.CaptureFixture[str], status: str, stage: str) -> None:
    captured = capsys.readouterr()
    assert captured.out == json.dumps({"status": status, "stage": stage}) + "\n"
    assert captured.err == ""
    assert _MARKER not in captured.out


def _assert_static_error(call: Callable[[], object]) -> None:
    with pytest.raises(PreflightError) as raised:
        call()
    assert raised.value.args == ("preflight invocation is invalid",)
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None
    rendered = "".join(traceback.format_exception(raised.value))
    for value in (_MARKER, _ACCOUNT, _CERTIFICATE, _TASK, _PROFILE):
        assert value not in rendered


@pytest.mark.parametrize("command", _COMMANDS)
def test_adapter_exact_read_only_subprocess_contract(
    command: list[str], process: _Process
) -> None:
    original = command.copy()
    inherited_environment = dict(cli.os.environ)
    assert cli._invoke_aws(command, profile=_PROFILE) == {"Account": _ACCOUNT}
    assert command == original
    assert process.calls == [
        (
            [
                *original,
                f"--profile={_PROFILE}",
                "--cli-connect-timeout=10",
                "--cli-read-timeout=30",
            ],
            {
                "shell": False,
                "stdin": subprocess.DEVNULL,
                "timeout": 45,
                "capture_output": True,
                "check": False,
                "env": {
                    **inherited_environment,
                    "AWS_PAGER": "",
                    "AWS_CLI_AUTO_PROMPT": "off",
                },
            },
        )
    ]
    assert dict(cli.os.environ) == inherited_environment
    assert process.calls[0][1]["env"] is not cli.os.environ


@pytest.mark.parametrize(
    "stdout",
    [
        b"",
        _MARKER.encode(),
        b"{} trailing",
        b"\xff",
        b"\xef\xbb\xbf{}",
        b'{"x":1,"x":2}',
        b'{"nested":{"x":1,"x":2}}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":-Infinity}',
        b'{"x":1e9999}',
        b'{"x":-1e9999}',
        b"{}" + b" " * (1024 * 1024 - 1),
    ],
)
def test_adapter_rejects_invalid_json_with_static_errors(
    stdout: bytes, process: _Process
) -> None:
    process.stdout = stdout
    _assert_static_error(lambda: cli._invoke_aws(_COMMANDS[0], profile=_PROFILE))
    assert len(process.calls) == 1


def test_adapter_accepts_json_at_response_limit(process: _Process) -> None:
    process.stdout = b"{}" + b" " * (1024 * 1024 - 2)
    assert cli._invoke_aws(_COMMANDS[0], profile=_PROFILE) == {}


@pytest.mark.parametrize("returncode", [1, 2, 255, -9])
def test_adapter_rejects_nonzero_exit(returncode: int, process: _Process) -> None:
    process.returncode = returncode
    _assert_static_error(lambda: cli._invoke_aws(_COMMANDS[0], profile=_PROFILE))
    assert len(process.calls) == 1


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(_MARKER),
        OSError(_MARKER),
        subprocess.TimeoutExpired(_MARKER, 45, output=_MARKER, stderr=_MARKER),
        RuntimeError(_MARKER),
    ],
)
def test_adapter_sanitizes_invocation_exceptions(
    error: Exception, process: _Process
) -> None:
    process.error = error
    _assert_static_error(lambda: cli._invoke_aws(_COMMANDS[0], profile=_PROFILE))
    assert len(process.calls) == 1


@pytest.mark.parametrize(
    "command",
    [
        None,
        "aws sts get-caller-identity",
        tuple(_COMMANDS[0]),
        [],
        ["aws"],
        ["aws", "sts", "get-caller-identity"],
        ["sh", *_COMMANDS[0][1:]],
        ["aws", "sts", "assume-role", *_BASE],
        ["aws", "secretsmanager", "get-secret-value", *_BASE],
        ["aws", "cloudformation", "deploy", *_BASE],
        ["aws", "ecs", "run-task", *_BASE],
        ["aws", "acm", "get-caller-identity", *_BASE],
        [*_COMMANDS[0], "--profile=other"],
        [*_COMMANDS[0], "--endpoint-url=http://localhost:4566"],
        [*_COMMANDS[0], "--debug"],
        [*_COMMANDS[0][:3], "--region=us-west-2", *_BASE[1:]],
        [*_COMMANDS[0][:3], _BASE[0], "--output=text", _BASE[2]],
        [*_COMMANDS[0][:-1], "--no-cli-pager="],
        [*_COMMANDS[0][:-1], None],
        [*_COMMANDS[1][:-1], "--certificate-arn=file:///private/input"],
        [*_COMMANDS[1][:-1], f"--certificate-arn={_CERTIFICATE}\n"],
        [*_COMMANDS[2][:-1], "--stack-name=other"],
        [*_COMMANDS[3][:-1], "--image-ids=imageDigest=bad"],
        [*_COMMANDS[3][:-2], "--repository-name=$(private-command)", _COMMANDS[3][-1]],
        [*_COMMANDS[4][:-1], "--tasks=file:///private/input"],
        [*_COMMANDS[4][:-1], f"--tasks={_TASK} --profile=other"],
    ],
)
def test_adapter_fails_closed_before_subprocess(
    command: object, process: _Process
) -> None:
    _assert_static_error(
        lambda: cli._invoke_aws(cast(list[str], command), profile=_PROFILE)
    )
    assert process.calls == []


@pytest.mark.parametrize(
    "profile",
    ["", "a" * 129, "-profile", "_profile", ".profile", "a/b", "é", "a\n", "a b"],
)
def test_invalid_profile_precedes_config_and_subprocess(
    profile: str,
    process: _Process,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(path: Path) -> DeploymentConfig:
        pytest.fail("configuration loaded before profile validation")

    monkeypatch.setattr(cli, "load_deployment_config", forbidden)
    assert cli.main(_arguments(config_path, profile)) == 1
    _assert_status(capsys, "failed", "arguments")
    _assert_static_error(lambda: cli._invoke_aws(_COMMANDS[0], profile=profile))
    assert process.calls == []


@pytest.mark.parametrize("profile", ["a", "1", "a" * 128, _PROFILE])
def test_valid_profile_boundaries(
    profile: str,
    process: _Process,
    config_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(_arguments(config_path, profile)) == 0
    assert process.calls[0][0][-3] == f"--profile={profile}"
    assert json.loads(capsys.readouterr().out) == {
        "status": "passed",
        "phase": "foundation",
        "checks": ["caller_account"],
    }


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--config", _MARKER],
        ["--profile", _PROFILE],
        ["--config", _MARKER, "--profile"],
        ["--config", _MARKER, "--profile", _PROFILE, "positional"],
        ["--conf", _MARKER, "--profile", _PROFILE],
        ["--config", _MARKER, "--prof", _PROFILE],
        ["--config", _MARKER, "--profile", _PROFILE, "--boot", _TASK],
        ["--config", _MARKER, "--profile", _PROFILE, "--unknown", _MARKER],
        ["--config", _MARKER, "--profile", _PROFILE, "--bootstrap-task-arn"],
        ["--config", _MARKER, "--profile", _PROFILE, "--", _MARKER],
    ],
)
def test_invalid_arguments_precede_config_and_subprocess(
    arguments: list[str],
    process: _Process,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(path: Path) -> DeploymentConfig:
        pytest.fail("configuration loaded before argument validation")

    monkeypatch.setattr(cli, "load_deployment_config", forbidden)
    assert cli.main(arguments) == 1
    _assert_status(capsys, "failed", "arguments")
    assert process.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        _MARKER.encode(),
        b"\xff",
        b'{"account":"111122223333","phase":"foundation","phase":"active"}',
        b'{"account":"111122223333","phase":"foundation","runtime":NaN}',
        b'{"account":"111122223333","phase":"foundation","runtime":1e9999}',
        b'{"account":"invalid","phase":"foundation"}',
        b"[]",
        b" " * 16385,
    ],
)
def test_invalid_bounded_config_precedes_subprocess(
    payload: bytes,
    process: _Process,
    config_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path.write_bytes(payload)
    assert cli.main(_arguments(config_path)) == 1
    _assert_status(capsys, "failed", "configuration")
    assert process.calls == []


def test_missing_config_precedes_subprocess(
    tmp_path: Path, process: _Process, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(_arguments(tmp_path / _MARKER)) == 1
    _assert_status(capsys, "failed", "configuration")
    assert process.calls == []


def test_help_has_no_calls(
    process: _Process,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(path: Path) -> DeploymentConfig:
        pytest.fail("help loaded configuration")

    monkeypatch.setattr(cli, "load_deployment_config", forbidden)
    assert cli.main(["--help"]) == 0
    captured = capsys.readouterr()
    assert "--config" in captured.out
    assert "--profile" in captured.out
    assert "No deployment proof or authorization" in captured.out
    assert captured.err == ""
    assert process.calls == []


@pytest.mark.parametrize("phase", ["foundation", "bootstrap", "active"])
def test_cli_passes_exact_config_task_and_aware_utc_to_runner(
    phase: Literal["foundation", "bootstrap", "active"],
    process: _Process,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _config(phase)
    config_path.write_text(json.dumps(asdict(config)), encoding="utf-8")
    expected = ["caller_account"]
    if phase != "foundation":
        expected.extend(["certificate", "stack", "backend_image", "frontend_image"])
    task = _TASK if phase == "active" else None
    if task is not None:
        expected.append("bootstrap_task")
    started = datetime.now(UTC)
    calls = 0

    def runner(
        supplied: DeploymentConfig,
        invoke: Callable[[list[str]], object],
        *,
        bootstrap_task_arn: str | None,
        now: datetime,
    ) -> list[str]:
        nonlocal calls
        calls += 1
        assert supplied == config
        assert bootstrap_task_arn == task
        assert now.tzinfo is UTC
        assert started <= now <= datetime.now(UTC)
        assert invoke(_COMMANDS[0]) == {"Account": _ACCOUNT}
        return expected.copy()

    monkeypatch.setattr(cli, "run_preflight", runner)
    arguments = _arguments(config_path)
    if task is not None:
        arguments.extend(["--bootstrap-task-arn", task])
    assert cli.main(arguments) == 0
    captured = capsys.readouterr()
    assert (
        captured.out
        == json.dumps({"status": "passed", "phase": phase, "checks": expected}) + "\n"
    )
    assert captured.err == ""
    assert calls == 1
    assert len(process.calls) == 1
    for value in (_MARKER, _ACCOUNT, _TASK, _PROFILE, str(config_path)):
        assert value not in captured.out


@pytest.mark.parametrize("task", ["", _TASK, _MARKER])
def test_runner_owns_task_validation_before_aws_calls(
    task: str, process: _Process, config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main([*_arguments(config_path), f"--bootstrap-task-arn={task}"]) == 1
    _assert_status(capsys, "failed", "preflight")
    assert process.calls == []


@pytest.mark.parametrize(
    ("stdout", "returncode", "error"),
    [
        (_MARKER.encode(), 0, None),
        (b"{}", 1, None),
        (b"{}", 0, FileNotFoundError(_MARKER)),
        (b"{}", 0, subprocess.TimeoutExpired(_MARKER, 45, stderr=_MARKER)),
        (b'{"Account":"999900001111"}', 0, None),
    ],
)
def test_cli_preflight_failures_emit_only_static_status(
    stdout: bytes,
    returncode: int,
    error: Exception | None,
    process: _Process,
    config_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    process.stdout = stdout
    process.returncode = returncode
    process.error = error
    assert cli.main(_arguments(config_path)) == 1
    _assert_status(capsys, "failed", "preflight")
    assert len(process.calls) == 1


@pytest.mark.parametrize("stage", ["arguments", "configuration", "preflight"])
@pytest.mark.parametrize("interrupt", [False, True])
def test_stage_errors_and_interrupts_are_static(
    stage: str,
    interrupt: bool,
    process: _Process,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = KeyboardInterrupt(_MARKER) if interrupt else RuntimeError(_MARKER)

    def fail(*args: object, **kwargs: object) -> object:
        try:
            raise ValueError(_MARKER)
        except ValueError as cause:
            raise error from cause

    if stage == "arguments":
        monkeypatch.setattr(cli._Parser, "parse_args", fail)
    elif stage == "configuration":
        monkeypatch.setattr(cli, "load_deployment_config", fail)
    else:
        monkeypatch.setattr(cli, "run_preflight", fail)
    assert cli.main(_arguments(config_path)) == (130 if interrupt else 1)
    _assert_status(capsys, "interrupted" if interrupt else "failed", stage)
    assert process.calls == []


def test_subprocess_interrupt_returns_130(
    process: _Process, config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    process.error = KeyboardInterrupt(_MARKER)
    assert cli.main(_arguments(config_path)) == 130
    _assert_status(capsys, "interrupted", "preflight")
    assert len(process.calls) == 1


def test_main_defaults_to_process_arguments(
    process: _Process,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["preflight_cli.py", *_arguments(config_path)])
    assert cli.main() == 0
    assert len(process.calls) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


@pytest.mark.parametrize("stage", ["arguments", "configuration", "preflight"])
def test_hostile_system_exit_is_static(
    stage: str,
    process: _Process,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(*args: object, **kwargs: object) -> object:
        raise SystemExit(_MARKER)

    if stage == "arguments":
        monkeypatch.setattr(cli._Parser, "parse_args", fail)
    elif stage == "configuration":
        monkeypatch.setattr(cli, "load_deployment_config", fail)
    else:
        monkeypatch.setattr(cli, "run_preflight", fail)
    assert cli.main(_arguments(config_path)) == 1
    _assert_status(capsys, "failed", stage)
    assert process.calls == []


def test_failed_runner_reports_no_partial_checks(
    process: _Process,
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def runner(
        config: DeploymentConfig,
        invoke: Callable[[list[str]], object],
        *,
        bootstrap_task_arn: str | None,
        now: datetime,
    ) -> list[str]:
        invoke(_COMMANDS[0])
        invoke(_COMMANDS[2])
        raise PreflightError(_MARKER)

    monkeypatch.setattr(cli, "run_preflight", runner)
    assert cli.main(_arguments(config_path)) == 1
    _assert_status(capsys, "failed", "preflight")
    assert len(process.calls) == 2


def test_import_has_no_config_or_process_side_effects(
    process: _Process,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(path: Path) -> DeploymentConfig:
        pytest.fail("import loaded configuration")

    monkeypatch.setattr("hosted_app.load_deployment_config", forbidden)
    try:
        importlib.reload(cli)
        assert process.calls == []
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""
    finally:
        monkeypatch.undo()
        importlib.reload(cli)
