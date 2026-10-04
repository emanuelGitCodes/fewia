import builtins
import os
import socket
import subprocess
import traceback
from collections import UserDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Never, cast

import pytest

from deployment_config import DeploymentConfig, RuntimeConfig
from preflight_checks import PreflightError
from preflight_runner import run_preflight

_ACCOUNT = "111122223333"
_NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
_UUID = "12345678-1234-abcd-1234-123456789abc"
_CERTIFICATE = f"arn:aws:acm:us-east-1:{_ACCOUNT}:certificate/{_UUID}"
_STACK = f"arn:aws:cloudformation:us-east-1:{_ACCOUNT}:stack/FewiaHostedDemoDev/{_UUID}"
_CLUSTER = f"arn:aws:ecs:us-east-1:{_ACCOUNT}:cluster/fewia-dev"
_DEFINITION = f"arn:aws:ecs:us-east-1:{_ACCOUNT}:task-definition/bootstrap:1"
_TASK = f"arn:aws:ecs:us-east-1:{_ACCOUNT}:task/fewia-dev/" + "a" * 32
_BACKEND_DIGEST = "sha256:" + "b" * 64
_FRONTEND_DIGEST = "sha256:" + "c" * 64
_ERROR = "preflight metadata is invalid"
_MARKER = "SYNTHETIC_PRIVATE_INPUT"
_CHECKS = ["caller_account", "certificate", "stack", "backend_image", "frontend_image"]


class _DictSubclass(dict[str, object]):
    pass


class _ListSubclass(list[object]):
    pass


class _StringSubclass(str):
    pass


class _Unreadable:
    def __str__(self) -> str:
        raise AssertionError("unknown metadata was read")

    def __repr__(self) -> str:
        raise AssertionError("unknown metadata was read")


def _config(
    phase: Literal["foundation", "bootstrap", "active"] = "bootstrap",
) -> DeploymentConfig:
    runtime = RuntimeConfig(
        "app.example.test",
        "fewia-dev",
        _CERTIFICATE,
        _BACKEND_DIGEST,
        _FRONTEND_DIGEST,
    )
    return DeploymentConfig(_ACCOUNT, phase, None if phase == "foundation" else runtime)


def _outputs() -> list[dict[str, object]]:
    return [
        {"OutputKey": key, "OutputValue": value}
        for key, value in {
            "DeploymentPhase": "bootstrap",
            "BackendRepositoryName": "fewia/backend",
            "FrontendRepositoryName": "fewia/frontend",
            "ClusterArn": _CLUSTER,
            "BootstrapTaskDefinitionArn": _DEFINITION,
            "ExtraOutput": "retained",
        }.items()
    ]


def _stack() -> dict[str, object]:
    return {
        "StackName": "FewiaHostedDemoDev",
        "StackId": _STACK,
        "StackStatus": "CREATE_COMPLETE",
        "Outputs": _outputs(),
    }


def _task() -> dict[str, object]:
    return {
        "taskArn": _TASK,
        "taskDefinitionArn": _DEFINITION,
        "clusterArn": _CLUSTER,
        "launchType": "FARGATE",
        "lastStatus": "STOPPED",
        "stopCode": "EssentialContainerExited",
        "startedAt": "2026-10-03T10:00:00Z",
        "stoppedAt": "2026-10-03T11:00:00Z",
        "containers": [
            {
                "name": "bootstrap",
                "lastStatus": "STOPPED",
                "imageDigest": _BACKEND_DIGEST,
                "exitCode": 0,
            }
        ],
    }


def _responses() -> list[object]:
    return [
        {"Account": _ACCOUNT},
        {
            "Certificate": {
                "CertificateArn": _CERTIFICATE,
                "Status": "ISSUED",
                "Type": "AMAZON_ISSUED",
                "SubjectAlternativeNames": ["app.example.test"],
                "NotBefore": "2026-10-03T11:00:00Z",
                "NotAfter": "2026-10-03T13:00:00Z",
            }
        },
        {"Stacks": [_stack()]},
        {
            "imageDetails": [
                {
                    "imageDigest": _BACKEND_DIGEST,
                    "repositoryName": "fewia/backend",
                    "registryId": _ACCOUNT,
                }
            ]
        },
        {
            "imageDetails": [
                {
                    "imageDigest": _FRONTEND_DIGEST,
                    "repositoryName": "fewia/frontend",
                    "registryId": _ACCOUNT,
                }
            ]
        },
        {"tasks": [_task()], "failures": []},
    ]


def _commands() -> list[list[str]]:
    operations = [
        ["sts", "get-caller-identity"],
        ["acm", "describe-certificate", f"--certificate-arn={_CERTIFICATE}"],
        ["cloudformation", "describe-stacks", "--stack-name=FewiaHostedDemoDev"],
        [
            "ecr",
            "describe-images",
            f"--registry-id={_ACCOUNT}",
            "--repository-name=fewia/backend",
            f"--image-ids=imageDigest={_BACKEND_DIGEST}",
        ],
        [
            "ecr",
            "describe-images",
            f"--registry-id={_ACCOUNT}",
            "--repository-name=fewia/frontend",
            f"--image-ids=imageDigest={_FRONTEND_DIGEST}",
        ],
        ["ecs", "describe-tasks", f"--cluster={_CLUSTER}", f"--tasks={_TASK}"],
    ]
    return [
        [
            "aws",
            *operation[:2],
            "--region=us-east-1",
            "--output=json",
            "--no-cli-pager",
            *operation[2:],
        ]
        for operation in operations
    ]


class _Invoke:
    def __init__(self, responses: list[object] | None = None) -> None:
        self.responses = _responses() if responses is None else responses
        self.commands = _commands()
        self.calls: list[list[str]] = []

    def __call__(self, arguments: list[str]) -> object:
        index = len(self.calls)
        self.calls.append(arguments.copy())
        assert arguments == self.commands[index]
        response = self.responses[index]
        if isinstance(response, BaseException):
            raise response
        return response


def _assert_invalid(call: Callable[[], object]) -> None:
    with pytest.raises(PreflightError) as error:
        call()
    assert type(error.value) is PreflightError
    assert error.value.args == (_ERROR,)
    assert error.value.__context__ is None
    assert error.value.__cause__ is None
    rendered = "".join(traceback.format_exception(error.value))
    assert _MARKER not in rendered
    assert _TASK not in rendered
    assert _CLUSTER not in rendered
    assert _CERTIFICATE not in rendered


def _runtime_run(invoke: _Invoke, *, active: bool = False) -> list[str]:
    return run_preflight(
        _config("active" if active else "bootstrap"),
        invoke,
        bootstrap_task_arn=_TASK if active else None,
        now=_NOW,
    )


@pytest.mark.parametrize(
    ("phase", "expected", "count"),
    [
        ("foundation", ["caller_account"], 1),
        ("bootstrap", _CHECKS, 5),
        ("active", [*_CHECKS, "bootstrap_task"], 6),
    ],
)
def test_phase_results_and_exact_read_only_call_sequence(
    phase: Literal["foundation", "bootstrap", "active"],
    expected: list[str],
    count: int,
) -> None:
    invoke = _Invoke()
    config = _config(phase)
    snapshot = deepcopy((config, invoke.responses))
    result = run_preflight(
        config,
        invoke,
        bootstrap_task_arn=_TASK if phase == "active" else None,
        now=_NOW,
    )
    assert result == expected
    assert invoke.calls == _commands()[:count]
    assert (config, invoke.responses) == snapshot


@pytest.mark.parametrize("phase", ["foundation", "bootstrap"])
@pytest.mark.parametrize("task", ["", _TASK, "--help"])
def test_non_active_phases_reject_supplied_task_before_calls(
    phase: Literal["foundation", "bootstrap"], task: str
) -> None:
    invoke = _Invoke()
    _assert_invalid(
        lambda: run_preflight(_config(phase), invoke, bootstrap_task_arn=task, now=_NOW)
    )
    assert invoke.calls == []


@pytest.mark.parametrize(
    "task",
    [
        None,
        True,
        123,
        "",
        "--help",
        "a" * 32,
        _TASK.replace(_ACCOUNT, "999900001111"),
        _TASK.replace("us-east-1", "us-west-2"),
        _TASK.replace("arn:aws:", "arn:aws-cn:"),
        _TASK.replace("task/fewia-dev/", "task/"),
        _TASK[:-1],
        _TASK + "a",
        _TASK + "\n",
        _StringSubclass(_TASK),
    ],
)
def test_active_requires_concrete_long_task_arn_before_calls(task: object) -> None:
    invoke = _Invoke()
    _assert_invalid(
        lambda: run_preflight(
            _config("active"),
            invoke,
            bootstrap_task_arn=cast(str | None, task),
            now=_NOW,
        )
    )
    assert invoke.calls == []


@pytest.mark.parametrize("now", [None, True, 123, _NOW.replace(tzinfo=None)])
@pytest.mark.parametrize("phase", ["foundation", "bootstrap", "active"])
def test_now_requires_aware_datetime_before_calls(
    now: object, phase: Literal["foundation", "bootstrap", "active"]
) -> None:
    invoke = _Invoke()
    _assert_invalid(
        lambda: run_preflight(
            _config(phase),
            invoke,
            bootstrap_task_arn=_TASK if phase == "active" else None,
            now=cast(datetime, now),
        )
    )
    assert invoke.calls == []


@pytest.mark.parametrize(
    "config",
    [
        replace(_config(), account="--help"),
        replace(_config(), phase=cast(Literal["bootstrap"], "unknown")),
        replace(_config(), runtime=None),
        replace(_config("foundation"), runtime=_config().runtime),
        DeploymentConfig(
            _ACCOUNT,
            "bootstrap",
            RuntimeConfig(
                "app.example.test",
                "fewia-dev",
                "--help",
                _BACKEND_DIGEST,
                _FRONTEND_DIGEST,
            ),
        ),
        DeploymentConfig(
            _ACCOUNT,
            "bootstrap",
            RuntimeConfig(
                "app.example.test",
                "fewia-dev",
                _CERTIFICATE,
                "--help",
                _FRONTEND_DIGEST,
            ),
        ),
    ],
)
def test_config_is_reparsed_before_calls(config: DeploymentConfig) -> None:
    invoke = _Invoke()
    expected = deepcopy(config)
    _assert_invalid(lambda: run_preflight(config, invoke, now=_NOW))
    assert invoke.calls == []
    assert config == expected


@pytest.mark.parametrize("index", range(6))
@pytest.mark.parametrize(
    "response",
    [None, True, _MARKER, [], {}, RuntimeError(_MARKER), PreflightError(_MARKER)],
)
def test_failed_subcheck_or_invoke_halts_later_calls(
    index: int, response: object
) -> None:
    invoke = _Invoke()
    invoke.responses[index] = response
    snapshot = deepcopy(invoke.responses)
    _assert_invalid(lambda: _runtime_run(invoke, active=True))
    assert invoke.calls == _commands()[: index + 1]
    if not isinstance(response, Exception):
        assert invoke.responses == snapshot


@pytest.mark.parametrize("index", range(6))
def test_keyboard_interrupt_propagates(index: int) -> None:
    invoke = _Invoke()
    invoke.responses[index] = KeyboardInterrupt(_MARKER)
    with pytest.raises(KeyboardInterrupt):
        _runtime_run(invoke, active=True)
    assert invoke.calls == _commands()[: index + 1]


@pytest.mark.parametrize(
    "stacks",
    [
        None,
        (),
        {},
        [],
        [_stack(), _stack()],
        [None],
        [_DictSubclass(_stack())],
        _ListSubclass([_stack()]),
        UserDict(),
    ],
)
def test_stack_requires_one_exact_object(stacks: object) -> None:
    invoke = _Invoke()
    invoke.responses[2] = {"Stacks": stacks}
    _assert_invalid(lambda: _runtime_run(invoke))
    assert invoke.calls == _commands()[:3]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("StackName", "OtherStack"),
        ("StackName", None),
        ("StackId", _STACK.replace(_ACCOUNT, "999900001111")),
        ("StackId", _STACK.replace("us-east-1", "us-west-2")),
        ("StackId", _STACK.replace("FewiaHostedDemoDev", "OtherStack")),
        ("StackId", _STACK.replace(_UUID, "not-a-uuid")),
        ("StackId", _STACK + "/extra"),
        ("StackId", None),
        ("StackStatus", "CREATE_IN_PROGRESS"),
        ("StackStatus", "DELETE_COMPLETE"),
        ("StackStatus", "ROLLBACK_COMPLETE"),
        ("StackStatus", "UPDATE_ROLLBACK_FAILED"),
        ("StackStatus", True),
    ],
)
def test_stack_rejects_identity_and_status_mismatch(field: str, value: object) -> None:
    invoke = _Invoke()
    stack = _stack()
    stack[field] = value
    invoke.responses[2] = {"Stacks": [stack]}
    _assert_invalid(lambda: _runtime_run(invoke))
    assert invoke.calls == _commands()[:3]


@pytest.mark.parametrize("field", ["StackName", "StackId", "StackStatus", "Outputs"])
def test_stack_requires_metadata_fields(field: str) -> None:
    invoke = _Invoke()
    stack = _stack()
    del stack[field]
    invoke.responses[2] = {"Stacks": [stack]}
    _assert_invalid(lambda: _runtime_run(invoke))
    assert invoke.calls == _commands()[:3]


@pytest.mark.parametrize(
    "outputs",
    [
        None,
        (),
        {},
        [],
        _ListSubclass(_outputs()),
        [None],
        [*_outputs(), _outputs()[0]],
        [*_outputs(), {"OutputKey": "Extra", "OutputValue": None}],
        [*_outputs(), {"OutputKey": None, "OutputValue": "value"}],
        [*_outputs(), {"OutputKey": "Extra"}],
        [*_outputs(), {"OutputValue": "value"}],
        [*_outputs(), {"OutputKey": _StringSubclass("Extra"), "OutputValue": "value"}],
        [*_outputs(), {"OutputKey": "Extra", "OutputValue": _StringSubclass("value")}],
        [*_outputs(), _DictSubclass(OutputKey="Extra", OutputValue="value")],
    ],
)
def test_stack_rejects_malformed_or_duplicate_outputs(outputs: object) -> None:
    invoke = _Invoke()
    stack = _stack()
    stack["Outputs"] = outputs
    invoke.responses[2] = {"Stacks": [stack]}
    _assert_invalid(lambda: _runtime_run(invoke))
    assert invoke.calls == _commands()[:3]


@pytest.mark.parametrize(
    "key",
    [
        "DeploymentPhase",
        "BackendRepositoryName",
        "FrontendRepositoryName",
        "ClusterArn",
        "BootstrapTaskDefinitionArn",
    ],
)
def test_active_requires_all_stack_outputs(key: str) -> None:
    invoke = _Invoke()
    stack = _stack()
    stack["Outputs"] = [item for item in _outputs() if item["OutputKey"] != key]
    invoke.responses[2] = {"Stacks": [stack]}
    _assert_invalid(lambda: _runtime_run(invoke, active=True))
    assert invoke.calls == _commands()[:3]


@pytest.mark.parametrize("key", ["BackendRepositoryName", "FrontendRepositoryName"])
@pytest.mark.parametrize(
    "value",
    [
        "--help",
        "-backend",
        "backend --profile private",
        "backend;private-command",
        "$(private-command)",
        "`private-command`",
        "a",
        "a" * 257,
        "Backend",
        "backend\n",
        "fewia//backend",
        None,
        True,
    ],
)
def test_both_repository_names_are_validated_before_ecr(
    key: str, value: object
) -> None:
    invoke = _Invoke()
    stack = _stack()
    outputs = _outputs()
    for item in outputs:
        if item["OutputKey"] == key:
            item["OutputValue"] = value
    stack["Outputs"] = outputs
    invoke.responses[2] = {"Stacks": [stack]}
    _assert_invalid(lambda: _runtime_run(invoke))
    assert invoke.calls == _commands()[:3]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ClusterArn", _CLUSTER.replace(_ACCOUNT, "999900001111")),
        ("ClusterArn", _CLUSTER.replace("us-east-1", "us-west-2")),
        ("ClusterArn", _CLUSTER + "/extra"),
        ("ClusterArn", _CLUSTER.replace("fewia-dev", "other-cluster")),
        ("ClusterArn", "--help"),
        ("BootstrapTaskDefinitionArn", _DEFINITION.replace(_ACCOUNT, "999900001111")),
        ("BootstrapTaskDefinitionArn", _DEFINITION.replace("us-east-1", "us-west-2")),
        ("BootstrapTaskDefinitionArn", _DEFINITION.replace(":1", ":0")),
        ("BootstrapTaskDefinitionArn", _DEFINITION.replace(":1", ":01")),
        ("BootstrapTaskDefinitionArn", _DEFINITION + "/extra"),
        ("BootstrapTaskDefinitionArn", "--help"),
    ],
)
def test_active_stack_proof_identities_are_validated_before_ecr(
    key: str, value: str
) -> None:
    invoke = _Invoke()
    stack = _stack()
    outputs = _outputs()
    for item in outputs:
        if item["OutputKey"] == key:
            item["OutputValue"] = value
    stack["Outputs"] = outputs
    invoke.responses[2] = {"Stacks": [stack]}
    _assert_invalid(lambda: _runtime_run(invoke, active=True))
    assert invoke.calls == _commands()[:3]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("taskArn", _TASK[:-1] + "b"),
        ("clusterArn", _CLUSTER + "other"),
        ("taskDefinitionArn", _DEFINITION.replace(":1", ":2")),
        ("lastStatus", "RUNNING"),
        ("stoppedAt", "2026-10-02T10:00:00Z"),
        ("stoppedAt", "2026-10-03T12:00:01Z"),
    ],
)
def test_active_binds_all_proof_identities_and_now(field: str, value: str) -> None:
    invoke = _Invoke()
    task = _task()
    task[field] = value
    invoke.responses[5] = {"tasks": [task]}
    _assert_invalid(lambda: _runtime_run(invoke, active=True))
    assert invoke.calls == _commands()


def test_active_binds_backend_digest_and_successful_exit() -> None:
    def assert_active_invalid(invoke: _Invoke) -> None:
        _assert_invalid(lambda: _runtime_run(invoke, active=True))

    for field, value in (("imageDigest", _FRONTEND_DIGEST), ("exitCode", 1)):
        invoke = _Invoke()
        task = _task()
        cast(list[dict[str, object]], task["containers"])[0][field] = value
        invoke.responses[5] = {"tasks": [task]}
        assert_active_invalid(invoke)
        assert invoke.calls == _commands()


def test_active_accepts_nondefault_bound_proof_identities() -> None:
    cluster = _CLUSTER.replace("fewia-dev", "other-cluster")
    task_arn = _TASK.replace("fewia-dev", "other-cluster")[:-1] + "b"
    definition = _DEFINITION.replace("bootstrap:1", "bootstrap_new:42")
    invoke = _Invoke()
    stack = _stack()
    outputs = _outputs()
    for output in outputs:
        if output["OutputKey"] == "ClusterArn":
            output["OutputValue"] = cluster
        elif output["OutputKey"] == "BootstrapTaskDefinitionArn":
            output["OutputValue"] = definition
    stack["Outputs"] = outputs
    invoke.responses[2] = {"Stacks": [stack]}
    task = _task()
    task.update(taskArn=task_arn, clusterArn=cluster, taskDefinitionArn=definition)
    invoke.responses[5] = {"tasks": [task]}
    invoke.commands[5][-2:] = [f"--cluster={cluster}", f"--tasks={task_arn}"]
    result = run_preflight(
        _config("active"), invoke, bootstrap_task_arn=task_arn, now=_NOW
    )
    assert result == [*_CHECKS, "bootstrap_task"]
    assert invoke.calls == invoke.commands


def test_bootstrap_does_not_require_active_proof_outputs() -> None:
    invoke = _Invoke()
    stack = _stack()
    stack["Outputs"] = _outputs()[:3]
    invoke.responses[2] = {"Stacks": [stack]}
    assert _runtime_run(invoke) == _CHECKS
    assert invoke.calls == _commands()[:5]


@pytest.mark.parametrize(
    "status", ["CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"]
)
@pytest.mark.parametrize("existing", ["foundation", "bootstrap", "active"])
@pytest.mark.parametrize("requested", ["bootstrap", "active"])
def test_phase_transition_and_stable_status_contract(
    status: str, existing: str, requested: Literal["bootstrap", "active"]
) -> None:
    invoke = _Invoke()
    stack = _stack()
    stack["StackStatus"] = status
    outputs = _outputs()
    outputs[0]["OutputValue"] = existing
    stack["Outputs"] = outputs
    invoke.responses[2] = {"Stacks": [stack]}
    if requested == "active" and existing == "foundation":
        _assert_invalid(lambda: _runtime_run(invoke, active=True))
        assert invoke.calls == _commands()[:3]
    else:
        assert _runtime_run(invoke, active=requested == "active") == (
            [*_CHECKS, "bootstrap_task"] if requested == "active" else _CHECKS
        )


@pytest.mark.parametrize("phase", ["unknown", "--help", "Bootstrap", "active\n"])
def test_stack_rejects_unknown_phase(phase: str) -> None:
    invoke = _Invoke()
    stack = _stack()
    outputs = _outputs()
    outputs[0]["OutputValue"] = phase
    stack["Outputs"] = outputs
    invoke.responses[2] = {"Stacks": [stack]}
    _assert_invalid(lambda: _runtime_run(invoke))
    assert invoke.calls == _commands()[:3]


def test_unknown_metadata_is_preserved_without_inspection() -> None:
    invoke = _Invoke()
    stack = _stack()
    stack["ExtraMetadata"] = _Unreadable()
    outputs = _outputs()
    outputs[0]["ExtraMetadata"] = _Unreadable()
    stack["Outputs"] = outputs
    invoke.responses[2] = {"Stacks": [stack], "ExtraMetadata": _Unreadable()}
    assert _runtime_run(invoke) == _CHECKS
    assert stack["Outputs"] is outputs


def test_runner_uses_invoke_without_other_io(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("preflight performed an external operation")

    invoke = _Invoke()
    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", forbidden)
        guarded.setattr(Path, "open", forbidden)
        guarded.setattr(os, "getenv", forbidden)
        guarded.setattr(type(os.environ), "__getitem__", forbidden)
        guarded.setattr(socket, "socket", forbidden)
        guarded.setattr(subprocess, "Popen", forbidden)
        assert _runtime_run(invoke, active=True) == [*_CHECKS, "bootstrap_task"]
