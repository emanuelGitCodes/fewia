import builtins
import io
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from types import ModuleType
from typing import Never
from unittest.mock import Mock

import pytest

import hosted_app
from deployment_config import parse_deployment_config

_LIMIT = 16384
_MARKER = "HOSTILE_PRIVATE_INPUT"
_ACCOUNT = "111122223333"
_STACK = "FewiaHostedDemoDev"


def _raw(phase: str = "foundation") -> dict[str, object]:
    result: dict[str, object] = {"account": _ACCOUNT, "phase": phase}
    if phase != "foundation":
        result["runtime"] = {
            "hostname": "example.test",
            "domain_prefix": "fewia-dev",
            "certificate_arn": (
                f"arn:aws:acm:us-east-1:{_ACCOUNT}:certificate/"
                "12345678-1234-abcd-1234-123456789abc"
            ),
            "backend_digest": "sha256:" + "a" * 64,
            "frontend_digest": "sha256:" + "b" * 64,
        }
    return result


def _write(tmp_path: Path, raw: object) -> Path:
    path = tmp_path / (_MARKER + ".json")
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _assert_invalid(path: Path) -> None:
    with pytest.raises(ValueError) as caught:
        hosted_app.load_deployment_config(path)
    error = caught.value
    assert type(error) is ValueError
    assert error.args == ("deployment configuration is invalid",)
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert _MARKER not in rendered
    assert str(path) not in rendered
    assert _ACCOUNT not in rendered


@pytest.fixture
def cdk(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    application = Mock(return_value=Mock())
    stack = Mock()
    cdk_module = ModuleType("aws_cdk")
    stack_module = ModuleType("hosted_stack")
    monkeypatch.setattr(cdk_module, "App", application, raising=False)
    monkeypatch.setattr(stack_module, "HostedDemoStack", stack, raising=False)
    monkeypatch.setitem(sys.modules, "aws_cdk", cdk_module)
    monkeypatch.setitem(sys.modules, "hosted_stack", stack_module)
    return application, stack


@pytest.mark.parametrize("phase", ["foundation", "bootstrap", "active"])
def test_load_valid_config(tmp_path: Path, phase: str) -> None:
    path = _write(tmp_path, _raw(phase))
    expected = parse_deployment_config(_raw(phase))
    assert hosted_app.load_deployment_config(path) == expected


@pytest.mark.parametrize("extra", [0, 1])
def test_exact_byte_boundary(tmp_path: Path, extra: int) -> None:
    payload = json.dumps(_raw()).encode("utf-8")
    path = tmp_path / (_MARKER + ".json")
    path.write_bytes(payload + b" " * (_LIMIT - len(payload) + extra))
    if extra:
        _assert_invalid(path)
    else:
        assert hosted_app.load_deployment_config(path).phase == "foundation"


@pytest.mark.parametrize("oversized", [False, True])
def test_read_is_capped_once(monkeypatch: pytest.MonkeyPatch, oversized: bool) -> None:
    payload = b" " * (_LIMIT + 2) if oversized else json.dumps(_raw()).encode()
    reads: list[int] = []

    class BoundedFile(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            assert size is not None
            assert size == _LIMIT + 1
            reads.append(size)
            return super().read(size)

    def open_file(path: Path, mode: str) -> BoundedFile:
        assert path == Path(_MARKER)
        assert mode == "rb"
        return BoundedFile(payload)

    monkeypatch.setattr(Path, "open", open_file)
    if oversized:
        _assert_invalid(Path(_MARKER))
    else:
        assert hosted_app.load_deployment_config(Path(_MARKER)).phase == "foundation"
    assert reads == [_LIMIT + 1]


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"{HOSTILE_PRIVATE_INPUT",
        b"{} trailing HOSTILE_PRIVATE_INPUT",
        b"\xffHOSTILE_PRIVATE_INPUT",
        json.dumps(_raw()).encode("utf-16"),
        b"\xef\xbb\xbf" + json.dumps(_raw()).encode(),
        b"[]",
        b"null",
        b'"HOSTILE_PRIVATE_INPUT"',
        b'{"phase":"foundation"}',
        b'{"account":"111122223333"}',
        b'{"account":"111122223333","phase":"foundation","extra":null}',
        b'{"account":"111122223333","phase":"active","runtime":{}}',
        b'{"account":"111122223333","phase":"foundation","runtime":{}}',
    ],
)
def test_invalid_bytes_and_schema(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    cdk: tuple[Mock, Mock],
    payload: bytes,
) -> None:
    path = tmp_path / (_MARKER + ".json")
    path.write_bytes(payload)
    _assert_invalid(path)
    assert hosted_app.main(["--config", str(path)]) == 1
    application, stack = cdk
    application.assert_not_called()
    stack.assert_not_called()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "stage": "configuration"}
    assert captured.err == ""
    assert _MARKER not in captured.out


@pytest.mark.parametrize(
    "payload",
    [
        '{"account":"111122223333","phase":"foundation","phase":"foundation"}',
        '{"account":"111122223333","phase":"foundation","ph\\u0061se":"active"}',
        '{"runtime":{"hostname":"example.test","hostname":"example.test"}}',
        '{"nested":[{"deep":{"HOSTILE_PRIVATE_INPUT":1,"HOSTILE_PRIVATE_INPUT":2}}]}',
    ],
)
def test_duplicate_keys_at_any_depth_precede_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    parser = Mock(return_value=parse_deployment_config(_raw()))
    monkeypatch.setattr(hosted_app, "parse_deployment_config", parser)
    path = tmp_path / (_MARKER + ".json")
    path.write_text(payload, encoding="utf-8")
    _assert_invalid(path)
    parser.assert_not_called()


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
def test_nonfinite_numbers_precede_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, number: str
) -> None:
    parser = Mock(return_value=parse_deployment_config(_raw()))
    monkeypatch.setattr(hosted_app, "parse_deployment_config", parser)
    path = tmp_path / (_MARKER + ".json")
    path.write_text('{"nested":[{"value":' + number + "}]}", encoding="utf-8")
    _assert_invalid(path)
    parser.assert_not_called()


@pytest.mark.parametrize("directory", [False, True])
def test_missing_file_and_directory(tmp_path: Path, directory: bool) -> None:
    path = tmp_path if directory else tmp_path / (_MARKER + ".json")
    _assert_invalid(path)


@pytest.mark.parametrize("target", ["read", "validation"])
def test_loader_discards_hostile_error_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    path = _write(tmp_path, _raw())

    def fail(*args: object, **kwargs: object) -> Never:
        try:
            raise RuntimeError(_MARKER)
        except RuntimeError as error:
            raise ValueError(_MARKER) from error

    if target == "read":
        monkeypatch.setattr(Path, "open", fail)
    else:
        monkeypatch.setattr(hosted_app, "parse_deployment_config", fail)
    _assert_invalid(path)


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--config"],
        ["--conf", _MARKER],
        ["--outdir", _MARKER],
        ["--config", _MARKER, "--unknown", _MARKER],
        ["--config", _MARKER, _MARKER],
        ["--config", _MARKER, "--outdir"],
    ],
)
def test_invalid_arguments_precede_file_and_cdk_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    loader = Mock(side_effect=AssertionError(_MARKER))
    monkeypatch.setattr(hosted_app, "load_deployment_config", loader)
    importer = Mock(wraps=builtins.__import__)
    monkeypatch.setattr(builtins, "__import__", importer)
    assert hosted_app.main(arguments) == 1
    loader.assert_not_called()
    assert not any(
        call.args[0] in ("aws_cdk", "hosted_stack") for call in importer.call_args_list
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "stage": "arguments"}
    assert captured.err == ""
    assert _MARKER not in captured.out


@pytest.mark.parametrize("arguments", [["--help"], ["--config", _MARKER, "--help"]])
def test_help_precedes_file_and_cdk_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    loader = Mock(side_effect=AssertionError(_MARKER))
    monkeypatch.setattr(hosted_app, "load_deployment_config", loader)
    importer = Mock(wraps=builtins.__import__)
    monkeypatch.setattr(builtins, "__import__", importer)
    assert hosted_app.main(arguments) == 0
    loader.assert_not_called()
    assert not any(
        call.args[0] in ("aws_cdk", "hosted_stack") for call in importer.call_args_list
    )
    captured = capsys.readouterr()
    assert "python hosted_app.py" in captured.out
    assert "--config" in captured.out
    assert "--outdir" in captured.out
    assert captured.err == ""
    assert _MARKER not in captured.out


@pytest.mark.parametrize("phase", ["foundation", "bootstrap", "active"])
@pytest.mark.parametrize("explicit_outdir", [False, True])
def test_valid_main_constructs_exact_stack_and_synthesizes_once(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    cdk: tuple[Mock, Mock],
    phase: str,
    explicit_outdir: bool,
) -> None:
    path = _write(tmp_path, _raw(phase))
    arguments = ["--config", str(path)]
    outdir = tmp_path / (_MARKER + "-assembly")
    if explicit_outdir:
        arguments.extend(["--outdir", str(outdir)])
    assert hosted_app.main(arguments) == 0
    application, stack = cdk
    if explicit_outdir:
        application.assert_called_once_with(outdir=str(outdir))
    else:
        application.assert_called_once_with()
    stack.assert_called_once_with(
        application.return_value, _STACK, config=parse_deployment_config(_raw(phase))
    )
    application.return_value.synth.assert_called_once_with()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "status": "synthesized",
        "phase": phase,
        "stack": _STACK,
    }
    assert captured.err == ""
    assert _MARKER not in captured.out
    assert _ACCOUNT not in captured.out
    assert "arn:" not in captured.out


@pytest.mark.parametrize("raw", [{}, [], {"account": _ACCOUNT, "phase": _MARKER}])
def test_malformed_config_precedes_cdk_construction(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    cdk: tuple[Mock, Mock],
    raw: object,
) -> None:
    path = _write(tmp_path, raw)
    assert hosted_app.main(["--config", str(path)]) == 1
    application, stack = cdk
    application.assert_not_called()
    stack.assert_not_called()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "failed", "stage": "configuration"}
    assert captured.err == ""
    assert _MARKER not in captured.out


@pytest.mark.parametrize(
    "target", ["arguments", "configuration", "app", "stack", "synth"]
)
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_failures_and_interrupts_emit_static_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    cdk: tuple[Mock, Mock],
    target: str,
    error_type: type[BaseException],
) -> None:
    path = _write(tmp_path, _raw())
    error = error_type(_MARKER)
    interrupt = error_type is KeyboardInterrupt
    application, stack = cdk
    if target == "arguments":
        monkeypatch.setattr(hosted_app._Parser, "parse_args", Mock(side_effect=error))
    elif target == "configuration":
        monkeypatch.setattr(
            hosted_app, "load_deployment_config", Mock(side_effect=error)
        )
    elif target == "app":
        application.side_effect = error
    elif target == "stack":
        stack.side_effect = error
    else:
        application.return_value.synth.side_effect = error
    assert hosted_app.main(["--config", str(path)]) == (130 if interrupt else 1)
    stage = target if target in ("arguments", "configuration") else "synthesis"
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "status": "interrupted" if interrupt else "failed",
        "stage": stage,
    }
    assert captured.err == ""
    assert _MARKER not in captured.out
    assert _ACCOUNT not in captured.out
    if stage != "synthesis":
        application.assert_not_called()
        stack.assert_not_called()


@pytest.mark.parametrize("phase", ["foundation", "bootstrap", "active"])
def test_real_offline_cli_synthesis(tmp_path: Path, phase: str) -> None:
    config = _write(tmp_path, _raw(phase))
    outdir = tmp_path / "assembly"
    context = {
        f"availability-zones:account={_ACCOUNT}:region=us-east-1": [
            "us-east-1a",
            "us-east-1b",
        ]
    }
    result = subprocess.run(
        [sys.executable, str(Path(hosted_app.__file__)), "--config", str(config)],
        cwd=tmp_path,
        env={
            "PATH": os.environ.get("PATH", os.defpath),
            "HOME": str(tmp_path),
            "CDK_OUTDIR": str(outdir),
            "CDK_CONTEXT_JSON": json.dumps(context),
            "AWS_EC2_METADATA_DISABLED": "true",
        },
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert json.loads(result.stdout) == {
        "status": "synthesized",
        "phase": phase,
        "stack": _STACK,
    }
    assert _MARKER not in result.stdout + result.stderr
    assert _ACCOUNT not in result.stdout
    manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
    template_file = manifest["artifacts"][_STACK]["properties"]["templateFile"]
    template = json.loads((outdir / template_file).read_text(encoding="utf-8"))
    assert template["Outputs"]["DeploymentPhase"]["Value"] == phase
