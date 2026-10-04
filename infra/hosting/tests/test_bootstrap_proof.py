import builtins
import os
import socket
import subprocess
import traceback
from collections import UserDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never, cast

import pytest

from bootstrap_proof import check_bootstrap_task
from deployment_config import DeploymentConfig, RuntimeConfig
from preflight_checks import PreflightError

_ACCOUNT = "111122223333"
_PREFIX = f"arn:aws:ecs:us-east-1:{_ACCOUNT}:"
_CLUSTER = _PREFIX + "cluster/Fewia_dev-1"
_TASK = _PREFIX + "task/Fewia_dev-1/" + "0123456789abcdef" * 2
_DEFINITION = _PREFIX + "task-definition/Fewia_bootstrap-1:12"
_DIGEST = "sha256:" + "0123456789abcdef" * 4
_NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)
_ERROR = "bootstrap task metadata is invalid"
_MARKER = "SYNTHETIC_PRIVATE_INPUT"
_CONFIG = DeploymentConfig(
    _ACCOUNT,
    "active",
    RuntimeConfig("example.test", "fewia-dev", "unused", _DIGEST, _DIGEST),
)
_EXPECTED = {
    "taskArn": _TASK,
    "taskDefinitionArn": _DEFINITION,
    "clusterArn": _CLUSTER,
}


class _DictSubclass(dict[str, object]):
    pass


class _ListSubclass(list[object]):
    pass


class _StringSubclass(str):
    pass


class _IntSubclass(int):
    pass


def _response() -> dict[str, object]:
    return {
        "tasks": [
            {
                **_EXPECTED,
                "launchType": "FARGATE",
                "lastStatus": "STOPPED",
                "stopCode": "EssentialContainerExited",
                "startedAt": "2026-10-03T10:00:00Z",
                "stoppedAt": "2026-10-03T11:00:00Z",
                "containers": [
                    {
                        "name": "bootstrap",
                        "lastStatus": "STOPPED",
                        "imageDigest": _DIGEST,
                        "exitCode": 0,
                    }
                ],
            }
        ],
        "failures": [],
    }


def _task(response: dict[str, object]) -> dict[str, object]:
    return cast(list[dict[str, object]], response["tasks"])[0]


def _container(response: dict[str, object]) -> dict[str, object]:
    return cast(list[dict[str, object]], _task(response)["containers"])[0]


def _check(
    response: object,
    *,
    config: DeploymentConfig = _CONFIG,
    now: object = _NOW,
    expected: dict[str, object] | None = None,
) -> object:
    identities: dict[str, object] = {**_EXPECTED, **(expected or {})}
    checker: Callable[..., object] = check_bootstrap_task
    return checker(
        config,
        response,
        task_arn=cast(str, identities["taskArn"]),
        task_definition_arn=cast(str, identities["taskDefinitionArn"]),
        cluster_arn=cast(str, identities["clusterArn"]),
        now=cast(datetime, now),
    )


def _assert_invalid(
    response: object,
    *,
    config: DeploymentConfig = _CONFIG,
    now: object = _NOW,
    expected: dict[str, object] | None = None,
) -> None:
    with pytest.raises(PreflightError) as error:
        _check(response, config=config, now=now, expected=expected)
    assert type(error.value) is PreflightError
    assert error.value.args == (_ERROR,)
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert _MARKER not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("failures_present", [False, True])
def test_exact_success_returns_none_without_mutation(failures_present: bool) -> None:
    response = _response()
    if not failures_present:
        del response["failures"]
    before = deepcopy(response)
    assert _check(response) is None
    assert response == before
    assert _CONFIG.runtime is not None
    assert _CONFIG.runtime.backend_digest == _DIGEST


def test_unknown_metadata_is_permitted_without_inspection() -> None:
    response = _response()
    response["ResponseMetadata"] = {"private": _MARKER}
    _task(response)["stoppedReason"] = _MARKER
    _container(response)["reason"] = {"private": _MARKER}
    assert _check(response) is None


@pytest.mark.parametrize(
    ("started", "stopped", "now"),
    [
        ("2026-10-03T12:00:00+02:00", "2026-10-03T06:00:00-05:00", _NOW),
        ("2026-10-02T11:00:00Z", "2026-10-02T12:00:00Z", _NOW),
        ("2026-10-03T12:00:00Z", "2026-10-03T12:00:00Z", _NOW),
        (
            "2026-10-03T10:00:00.123456Z",
            "2026-10-03T11:00:00.654321Z",
            datetime.fromisoformat("2026-10-03T15:00:00+03:00"),
        ),
    ],
)
def test_offsets_and_inclusive_time_boundaries(
    started: str, stopped: str, now: datetime
) -> None:
    response = _response()
    _task(response).update(startedAt=started, stoppedAt=stopped)
    assert _check(response, now=now) is None


@pytest.mark.parametrize("name", ["a", "A_0-" + "a" * 251])
@pytest.mark.parametrize("revision", ["1", "123456789"])
def test_valid_arn_name_lengths_and_revisions(name: str, revision: str) -> None:
    expected: dict[str, object] = {
        "taskArn": _PREFIX + f"task/{name}/" + "a" * 32,
        "taskDefinitionArn": _PREFIX + f"task-definition/{name}:{revision}",
        "clusterArn": _PREFIX + f"cluster/{name}",
    }
    response = _response()
    _task(response).update(expected)
    assert _check(response, expected=expected) is None


@pytest.mark.parametrize("field", list(_EXPECTED))
@pytest.mark.parametrize(
    "attack",
    [
        "partition",
        "region",
        "account",
        "service",
        "token",
        "wildcard",
        "url",
        "option",
        "space",
        "newline",
        "suffix",
    ],
)
def test_expected_arn_attacks_fail_even_with_matching_metadata(
    field: str, attack: str
) -> None:
    original = _EXPECTED[field]
    variants = {
        "partition": original.replace("arn:aws:", "arn:aws-cn:"),
        "region": original.replace("us-east-1", "us-west-2"),
        "account": original.replace(_ACCOUNT, "999900001111"),
        "service": original.replace(":ecs:", ":iam:"),
        "token": "${Token[Arn.1]}",
        "wildcard": original.replace(_ACCOUNT, "*"),
        "url": "https://example.test/" + original,
        "option": "--cluster " + original,
        "space": " " + original,
        "newline": original + "\n",
        "suffix": original + "/extra",
    }
    response = _response()
    _task(response)[field] = variants[attack]
    _assert_invalid(response, expected={field: variants[attack]})


@pytest.mark.parametrize(
    ("field", "resource"),
    [
        ("clusterArn", "cluster/"),
        ("clusterArn", "cluster/" + "a" * 256),
        ("clusterArn", "cluster/féwia"),
        ("clusterArn", "cluster/fewia.dev"),
        ("clusterArn", "cluster/fewia/extra"),
        ("taskArn", "task/" + "a" * 32),
        ("taskArn", "task/other/" + "a" * 32),
        ("taskArn", "task/Fewia_dev-1/" + "A" * 32),
        ("taskArn", "task/Fewia_dev-1/" + "g" * 32),
        ("taskArn", "task/Fewia_dev-1/" + "a" * 31),
        ("taskArn", "task/Fewia_dev-1/" + "a" * 33),
        ("taskDefinitionArn", "task-definition/:1"),
        ("taskDefinitionArn", "task-definition/" + "a" * 256 + ":1"),
        ("taskDefinitionArn", "task-definition/féwia:1"),
        ("taskDefinitionArn", "task-definition/fewia.dev:1"),
        ("taskDefinitionArn", "task-definition/fewia:0"),
        ("taskDefinitionArn", "task-definition/fewia:01"),
        ("taskDefinitionArn", "task-definition/fewia:-1"),
        ("taskDefinitionArn", "task-definition/fewia:+1"),
        ("taskDefinitionArn", "task-definition/fewia:１"),
        ("taskDefinitionArn", "task-definition/fewia:1.0"),
        ("taskDefinitionArn", "task-definition/fewia"),
    ],
)
def test_arn_resource_grammar(field: str, resource: str) -> None:
    response = _response()
    value = _PREFIX + resource
    _task(response)[field] = value
    _assert_invalid(response, expected={field: value})


@pytest.mark.parametrize("field", list(_EXPECTED))
@pytest.mark.parametrize(
    "value", [None, True, 1, b"arn", [], {}, _StringSubclass(_TASK)]
)
def test_expected_arns_require_exact_strings(field: str, value: object) -> None:
    _assert_invalid(_response(), expected={field: value})


def test_expected_arns_are_checked_before_response_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(raw: object) -> Never:
        raise AssertionError("metadata read before ARN validation")

    monkeypatch.setattr("bootstrap_proof._object", forbidden)
    for field in _EXPECTED:
        _assert_invalid(_response(), expected={field: _MARKER})


@pytest.mark.parametrize(
    "response",
    [None, True, 1, "{}", [], (), _DictSubclass(_response()), UserDict(_response())],
)
def test_response_requires_an_exact_dictionary(response: object) -> None:
    _assert_invalid(response)


def test_tasks_cannot_be_missing() -> None:
    response = _response()
    del response["tasks"]
    _assert_invalid(response)


@pytest.mark.parametrize("field", ["tasks", "containers"])
@pytest.mark.parametrize(
    "value", [None, True, 1, {}, (), [], [None], [{}], _ListSubclass([{}])]
)
def test_task_and_container_require_exact_single_object_lists(
    field: str, value: object
) -> None:
    response = _response()
    parent = response if field == "tasks" else _task(response)
    parent[field] = value
    _assert_invalid(response)


@pytest.mark.parametrize("field", ["tasks", "containers"])
def test_extra_objects_and_nonexact_objects_fail(field: str) -> None:
    response = _response()
    parent = response if field == "tasks" else _task(response)
    value = cast(list[object], parent[field])[0]
    parent[field] = [value, deepcopy(value)]
    _assert_invalid(response)
    parent[field] = _ListSubclass([value])
    _assert_invalid(response)
    parent[field] = (value,)
    _assert_invalid(response)
    parent[field] = [_DictSubclass(cast(dict[str, object], value))]
    _assert_invalid(response)
    parent[field] = [UserDict(cast(dict[str, object], value))]
    _assert_invalid(response)


@pytest.mark.parametrize(
    "field",
    [
        *_EXPECTED,
        "launchType",
        "lastStatus",
        "stopCode",
        "startedAt",
        "stoppedAt",
        "containers",
    ],
)
def test_each_task_field_is_required(field: str) -> None:
    response = _response()
    del _task(response)[field]
    _assert_invalid(response)


@pytest.mark.parametrize("field", [*_EXPECTED, "launchType", "lastStatus", "stopCode"])
@pytest.mark.parametrize(
    "value", [None, True, 1, [], {}, "wrong", _StringSubclass("STOPPED")]
)
def test_task_identity_state_and_types_fail_closed(field: str, value: object) -> None:
    response = _response()
    _task(response)[field] = value
    _assert_invalid(response)


@pytest.mark.parametrize("field", [*_EXPECTED, "launchType", "lastStatus", "stopCode"])
def test_task_strings_cannot_be_subclasses(field: str) -> None:
    response = _response()
    _task(response)[field] = _StringSubclass(cast(str, _task(response)[field]))
    _assert_invalid(response)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("taskArn", _TASK[:-1] + "0"),
        ("taskDefinitionArn", _DEFINITION[:-2] + "13"),
        ("clusterArn", _PREFIX + "cluster/other"),
        ("launchType", "EC2"),
        ("lastStatus", "RUNNING"),
        ("stopCode", "TaskFailedToStart"),
        ("stopCode", "UserInitiated"),
    ],
)
def test_mismatched_identity_and_partial_state(field: str, value: str) -> None:
    response = _response()
    _task(response)[field] = value
    _assert_invalid(response)


@pytest.mark.parametrize("field", ["name", "lastStatus", "imageDigest", "exitCode"])
def test_each_container_field_is_required(field: str) -> None:
    response = _response()
    del _container(response)[field]
    _assert_invalid(response)


@pytest.mark.parametrize("field", ["name", "lastStatus", "imageDigest"])
@pytest.mark.parametrize(
    "value", [None, True, 1, [], {}, "wrong", _StringSubclass("bootstrap")]
)
def test_container_identity_state_digest_and_types(field: str, value: object) -> None:
    response = _response()
    _container(response)[field] = value
    _assert_invalid(response)


@pytest.mark.parametrize("field", ["name", "lastStatus", "imageDigest"])
def test_container_strings_cannot_be_subclasses(field: str) -> None:
    response = _response()
    _container(response)[field] = _StringSubclass(
        cast(str, _container(response)[field])
    )
    _assert_invalid(response)


@pytest.mark.parametrize(
    "value", [None, True, False, -1, 1, 137, 0.0, "0", [], {}, _IntSubclass(0)]
)
def test_exit_code_requires_exact_integer_zero(value: object) -> None:
    response = _response()
    _container(response)["exitCode"] = value
    _assert_invalid(response)


def test_different_valid_image_digest_fails() -> None:
    response = _response()
    _container(response)["imageDigest"] = "sha256:" + "a" * 64
    _assert_invalid(response)


@pytest.mark.parametrize(
    "failures", [None, True, False, 0, {}, (), "", [{}], [_MARKER], _ListSubclass()]
)
def test_failures_must_be_absent_or_an_exact_empty_list(failures: object) -> None:
    response = _response()
    response["failures"] = failures
    _assert_invalid(response)


@pytest.mark.parametrize("field", ["startedAt", "stoppedAt"])
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        1,
        _NOW,
        [],
        {},
        "",
        "2026-10-03T11:00:00",
        "2026-10-03",
        "2026-10-03 11:00:00Z",
        "2026-10-03T11:00:00+0000",
        "2026-10-03T11:00:00+24:00",
        "2026-10-03T11:00:60Z",
        "2026-02-30T11:00:00Z",
        "0000-10-03T11:00:00Z",
        "2026-10-03T11:00:00Z\n",
        _StringSubclass("2026-10-03T11:00:00Z"),
        _MARKER,
    ],
)
def test_timestamps_require_valid_aware_iso_strings(field: str, value: object) -> None:
    response = _response()
    _task(response)[field] = value
    _assert_invalid(response)


@pytest.mark.parametrize(
    ("started", "stopped"),
    [
        ("2026-10-03T11:00:01Z", "2026-10-03T11:00:00Z"),
        ("2026-10-03T12:00:01Z", "2026-10-03T12:00:02Z"),
        ("2026-10-03T10:00:00Z", "2026-10-03T12:00:00.000001Z"),
        ("2026-10-02T10:00:00Z", "2026-10-02T11:59:59.999999Z"),
    ],
)
def test_reversed_future_and_expired_times(started: str, stopped: str) -> None:
    response = _response()
    _task(response).update(startedAt=started, stoppedAt=stopped)
    _assert_invalid(response)


@pytest.mark.parametrize(
    "now", [None, True, False, 1, "now", _NOW.replace(tzinfo=None)]
)
def test_now_requires_an_aware_datetime(now: object) -> None:
    _assert_invalid(_response(), now=now)


def test_supplied_now_controls_freshness() -> None:
    _assert_invalid(_response(), now=_NOW + timedelta(days=1))


@pytest.mark.parametrize(
    "config",
    [
        replace(_CONFIG, phase="foundation", runtime=None),
        replace(_CONFIG, phase="foundation"),
        replace(_CONFIG, phase="bootstrap"),
        replace(_CONFIG, runtime=None),
        replace(_CONFIG, account="${Token[Account.1]}"),
        replace(_CONFIG, account="１２３４５６７８９０１２"),
    ],
)
def test_only_active_runtime_configuration_is_accepted(
    config: DeploymentConfig,
) -> None:
    _assert_invalid(_response(), config=config)


def test_confidential_inputs_are_absent_from_errors() -> None:
    for field in ("name", "imageDigest", "exitCode"):
        response = _response()
        _container(response)[field] = {"private": _MARKER}
        _assert_invalid(response)
    response = _response()
    _task(response)["stoppedAt"] = _MARKER
    _assert_invalid(response)
    response = _response()
    response["failures"] = [{"reason": _MARKER}]
    _assert_invalid(response)
    _assert_invalid(_response(), expected={"taskArn": _MARKER})


def test_parser_context_is_absent_from_public_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Parser(datetime):
        @classmethod
        def fromisoformat(cls, date_string: str, /) -> Never:
            raise ValueError(_MARKER + date_string)

    monkeypatch.setattr("bootstrap_proof.datetime", _Parser)
    _assert_invalid(_response(), now=_Parser(2026, 10, 3, 12, tzinfo=UTC))


def test_checker_uses_only_inputs_without_external_operations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Never:
        raise AssertionError("checker performed an external operation")

    response = _response()
    with monkeypatch.context() as guarded:
        guarded.setattr(builtins, "open", forbidden)
        guarded.setattr(Path, "open", forbidden)
        guarded.setattr(os, "getenv", forbidden)
        guarded.setattr(type(os.environ), "__getitem__", forbidden)
        guarded.setattr(socket, "socket", forbidden)
        guarded.setattr(subprocess, "Popen", forbidden)
        assert _check(response) is None
        _task(response)["lastStatus"] = "RUNNING"
        with pytest.raises(PreflightError):
            _check(response)
