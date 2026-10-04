import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import cast

import preflight_checks as checks
from bootstrap_proof import check_bootstrap_task
from deployment_config import REGION, DeploymentConfig, parse_deployment_config
from preflight_checks import PreflightError

_ERROR = "preflight metadata is invalid"
_STACK = "FewiaHostedDemoDev"
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_NAME = r"[A-Za-z0-9_-]{1,255}"
_STABLE = ("CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE")


def _matches(pattern: str, value: object) -> bool:
    return re.fullmatch(pattern, checks._string(value)) is not None


def _stack_outputs(
    config: DeploymentConfig, response: object, task_arn: str | None
) -> dict[str, str]:
    stacks = checks._object(response).get("Stacks")
    if type(stacks) is not list or len(stacks) != 1:
        raise PreflightError(_ERROR)
    stack = checks._object(cast(list[object], stacks)[0])
    prefix = f"arn:aws:cloudformation:{REGION}:{config.account}:stack/"
    if (
        checks._string(stack.get("StackName")) != _STACK
        or not _matches(prefix + rf"{_STACK}/{_UUID}", stack.get("StackId"))
        or checks._string(stack.get("StackStatus")) not in _STABLE
    ):
        raise PreflightError(_ERROR)
    raw_outputs = stack.get("Outputs")
    if type(raw_outputs) is not list:
        raise PreflightError(_ERROR)
    outputs: dict[str, str] = {}
    for raw in cast(list[object], raw_outputs):
        output = checks._object(raw)
        key = checks._string(output.get("OutputKey"))
        if key in outputs:
            raise PreflightError(_ERROR)
        outputs[key] = checks._string(output.get("OutputValue"))
    phase = outputs["DeploymentPhase"]
    if phase not in ("foundation", "bootstrap", "active") or (
        config.phase == "active" and phase == "foundation"
    ):
        raise PreflightError(_ERROR)
    for key in ("BackendRepositoryName", "FrontendRepositoryName"):
        name = outputs[key]
        if not 2 <= len(name) <= 256 or not _matches(checks._REPOSITORY, name):
            raise PreflightError(_ERROR)
    if config.phase == "active":
        prefix = f"arn:aws:ecs:{REGION}:{config.account}:"
        cluster = re.fullmatch(prefix + rf"cluster/({_NAME})", outputs["ClusterArn"])
        if (
            cluster is None
            or checks._string(task_arn).split("/")[-2] != cluster[1]
            or not _matches(
                prefix + rf"task-definition/{_NAME}:[1-9][0-9]*",
                outputs["BootstrapTaskDefinitionArn"],
            )
        ):
            raise PreflightError(_ERROR)
    return outputs


def _run(
    config: DeploymentConfig,
    invoke: Callable[[list[str]], object],
    task_arn: str | None,
    now: datetime,
) -> list[str]:
    def request(service: str, operation: str, *arguments: str) -> object:
        base = ["aws", service, operation, f"--region={REGION}", "--output=json"]
        return invoke([*base, "--no-cli-pager", *arguments])

    checks.check_caller(config, request("sts", "get-caller-identity"))
    if config.phase == "foundation":
        return ["caller_account"]
    runtime = config.runtime
    assert runtime is not None
    certificate = request(
        "acm", "describe-certificate", f"--certificate-arn={runtime.certificate_arn}"
    )
    checks.check_certificate(config, certificate, now=now)
    stack = request("cloudformation", "describe-stacks", f"--stack-name={_STACK}")
    outputs = _stack_outputs(config, stack, task_arn)
    for label, digest in (
        ("Backend", runtime.backend_digest),
        ("Frontend", runtime.frontend_digest),
    ):
        name = outputs[f"{label}RepositoryName"]
        image = request(
            "ecr",
            "describe-images",
            f"--registry-id={config.account}",
            f"--repository-name={name}",
            f"--image-ids=imageDigest={digest}",
        )
        checks.check_image(config, image, repository_name=name, digest=digest)
    done = ["caller_account", "certificate", "stack", "backend_image", "frontend_image"]
    if config.phase == "active":
        assert task_arn is not None
        task = request(
            "ecs",
            "describe-tasks",
            f"--cluster={outputs['ClusterArn']}",
            f"--tasks={task_arn}",
        )
        check_bootstrap_task(
            config,
            task,
            task_arn=task_arn,
            task_definition_arn=outputs["BootstrapTaskDefinitionArn"],
            cluster_arn=outputs["ClusterArn"],
            now=now,
        )
        done.append("bootstrap_task")
    return done


def run_preflight(
    config: DeploymentConfig,
    invoke: Callable[[list[str]], object],
    *,
    bootstrap_task_arn: str | None = None,
    now: datetime,
) -> list[str]:
    try:
        config = parse_deployment_config(asdict(config))
        if type(now) is not datetime or now.utcoffset() is None:
            raise PreflightError(_ERROR)
        if config.phase == "active":
            if not _matches(
                rf"arn:aws:ecs:{REGION}:{config.account}:task/{_NAME}/[0-9a-f]{{32}}",
                bootstrap_task_arn,
            ):
                raise PreflightError(_ERROR)
        elif bootstrap_task_arn is not None:
            raise PreflightError(_ERROR)
        return _run(config, invoke, bootstrap_task_arn, now)
    except Exception:
        pass
    raise PreflightError(_ERROR)
