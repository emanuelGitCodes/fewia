import re
from datetime import datetime, timedelta
from typing import cast

from deployment_config import DeploymentConfig
from preflight_checks import PreflightError

_ERROR = "bootstrap task metadata is invalid"
_NAME = r"[A-Za-z0-9_-]{1,255}"
_TIMESTAMP = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def _object(raw: object) -> dict[str, object]:
    if type(raw) is not dict:
        raise PreflightError(_ERROR)
    values = cast(dict[object, object], raw)
    if any(type(key) is not str for key in values):
        raise PreflightError(_ERROR)
    return cast(dict[str, object], values)


def _string(raw: object) -> str:
    if type(raw) is not str:
        raise PreflightError(_ERROR)
    return raw


def _single(raw: object) -> dict[str, object]:
    if type(raw) is not list or len(raw) != 1:
        raise PreflightError(_ERROR)
    return _object(cast(list[object], raw)[0])


def _overrides(raw: object) -> None:
    values = _object(raw)
    if values.keys() - {"containerOverrides", "inferenceAcceleratorOverrides"}:
        raise PreflightError(_ERROR)
    accelerators = values.get("inferenceAcceleratorOverrides", [])
    if type(accelerators) is not list or accelerators:
        raise PreflightError(_ERROR)
    containers = values.get("containerOverrides", [])
    if type(containers) is not list:
        raise PreflightError(_ERROR)
    if containers:
        container = _single(containers)
        if set(container) != {"name"} or _string(container.get("name")) != "bootstrap":
            raise PreflightError(_ERROR)


def _timestamp(raw: object) -> datetime:
    value = _string(raw)
    if re.fullmatch(_TIMESTAMP, value) is None:
        raise PreflightError(_ERROR)
    result = None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        pass
    if result is None or result.utcoffset() is None:
        raise PreflightError(_ERROR)
    return result


def check_bootstrap_task(
    config: DeploymentConfig,
    response: object,
    *,
    task_arn: str,
    task_definition_arn: str,
    cluster_arn: str,
    now: datetime,
) -> None:
    """Check recent completion metadata.

    Database contents and secret rotation need live checks.
    """
    runtime = config.runtime
    if config.phase != "active" or runtime is None or type(now) is not datetime:
        raise PreflightError(_ERROR)
    account = _string(config.account)
    digest = _string(runtime.backend_digest)
    if (
        re.fullmatch(r"[0-9]{12}", account) is None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        raise PreflightError(_ERROR)
    prefix = f"arn:aws:ecs:us-east-1:{account}:"
    cluster = re.fullmatch(prefix + rf"cluster/({_NAME})", _string(cluster_arn))
    if cluster is None:
        raise PreflightError(_ERROR)
    if (
        re.fullmatch(
            prefix + rf"task/{re.escape(cluster[1])}/[0-9a-f]{{32}}",
            _string(task_arn),
        )
        is None
        or re.fullmatch(
            prefix + rf"task-definition/{_NAME}:[1-9][0-9]*",
            _string(task_definition_arn),
        )
        is None
    ):
        raise PreflightError(_ERROR)
    metadata = _object(response)
    failures = metadata.get("failures", [])
    if type(failures) is not list or failures:
        raise PreflightError(_ERROR)
    task = _single(metadata.get("tasks"))
    _overrides(task.get("overrides", {}))
    for key, expected in (
        ("taskArn", task_arn),
        ("taskDefinitionArn", task_definition_arn),
        ("clusterArn", cluster_arn),
        ("launchType", "FARGATE"),
        ("lastStatus", "STOPPED"),
        ("stopCode", "EssentialContainerExited"),
    ):
        if _string(task.get(key)) != expected:
            raise PreflightError(_ERROR)
    started = _timestamp(task.get("startedAt"))
    stopped = _timestamp(task.get("stoppedAt"))
    recent = False
    try:
        recent = (
            now.utcoffset() is not None
            and started <= stopped <= now
            and now - stopped <= timedelta(hours=24)
        )
    except (OverflowError, TypeError, ValueError):
        pass
    if not recent:
        raise PreflightError(_ERROR)
    container = _single(task.get("containers"))
    if (
        _string(container.get("name")) != "bootstrap"
        or _string(container.get("lastStatus")) != "STOPPED"
        or _string(container.get("imageDigest")) != digest
        or type(container.get("exitCode")) is not int
        or container["exitCode"] != 0
    ):
        raise PreflightError(_ERROR)
