from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk import aws_ecs as ecs
from aws_cdk.assertions import Template
from constructs import IConstruct

from app_task import HostingAppTask
from assets import HostingAssets
from database import HostingDatabase
from execution_roles import HostingExecutionRoles
from network import HostingNetwork
from stack import HostingResources, HostingStack
from task_roles import HostingTaskRoles
from task_settings import application_environment, application_secrets

_ACCOUNT = "111122223333"
_REGION = "us-east-1"
_BACKEND_DIGEST = "sha256:" + "a" * 64
_FRONTEND_DIGEST = "sha256:" + "b" * 64


@dataclass
class _Inputs:
    stack: Stack
    assets: HostingAssets
    database: HostingDatabase
    resources: HostingResources
    execution_roles: HostingExecutionRoles
    task_roles: HostingTaskRoles

    def build(
        self,
        backend_digest: str = _BACKEND_DIGEST,
        frontend_digest: str = _FRONTEND_DIGEST,
    ) -> HostingAppTask:
        return HostingAppTask(
            self.stack,
            "AppTask",
            assets=self.assets,
            database=self.database,
            resources=self.resources,
            execution_roles=self.execution_roles,
            task_roles=self.task_roles,
            backend_digest=backend_digest,
            frontend_digest=frontend_digest,
        )


@pytest.fixture(params=[False, True], ids=["tokens", "concrete"])
def inputs(request: pytest.FixtureRequest, tmp_path: Path) -> _Inputs:
    concrete: bool = request.param
    app = App(
        outdir=str(tmp_path / "assembly"),
        context={
            f"availability-zones:account={_ACCOUNT}:region={_REGION}": [
                "us-east-1a",
                "us-east-1b",
            ]
        },
    )
    stack = Stack(
        app,
        "AppTaskTest",
        env=Environment(account=_ACCOUNT, region=_REGION) if concrete else None,
    )
    assets = HostingAssets(stack, "Assets")
    database = HostingDatabase(
        stack, "Database", network=HostingNetwork(stack, "Network")
    )
    resources = HostingResources(stack, "Resources")
    return _Inputs(
        stack,
        assets,
        database,
        resources,
        HostingExecutionRoles(
            stack, "ExecutionRoles", assets=assets, database=database
        ),
        HostingTaskRoles(stack, "TaskRoles", resources=resources),
    )


@pytest.fixture
def task_case(inputs: _Inputs) -> tuple[_Inputs, HostingAppTask, Template]:
    task = inputs.build()
    return inputs, task, Template.from_stack(inputs.stack)


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _properties(template: Template) -> dict[str, Any]:
    tasks = template.find_resources("AWS::ECS::TaskDefinition")
    assert len(tasks) == 1
    return cast(dict[str, Any], next(iter(tasks.values()))["Properties"])


def _containers(template: Template) -> dict[str, dict[str, Any]]:
    return {
        item["Name"]: item for item in _properties(template)["ContainerDefinitions"]
    }


def test_task_sizing_platform_roles_and_resource_limits(
    task_case: tuple[_Inputs, HostingAppTask, Template],
) -> None:
    inputs, task, template = task_case
    props = _properties(template)
    assert isinstance(task.task_definition, ecs.FargateTaskDefinition)
    assert isinstance(task.api_container, ecs.ContainerDefinition)
    assert isinstance(task.web_container, ecs.ContainerDefinition)
    assert props["Cpu"] == "512"
    assert props["Memory"] == "1024"
    assert props["RuntimePlatform"] == {
        "CpuArchitecture": "X86_64",
        "OperatingSystemFamily": "LINUX",
    }
    assert props["NetworkMode"] == "awsvpc"
    assert props["RequiresCompatibilities"] == ["FARGATE"]
    assert props["ExecutionRoleArn"] == inputs.stack.resolve(
        inputs.execution_roles.app_execution_role.role_arn
    )
    assert props["TaskRoleArn"] == inputs.stack.resolve(
        inputs.task_roles.api_role.role_arn
    )
    assert set(props) == {
        "ContainerDefinitions",
        "Cpu",
        "ExecutionRoleArn",
        "Family",
        "Memory",
        "NetworkMode",
        "RequiresCompatibilities",
        "RuntimePlatform",
        "TaskRoleArn",
        "Volumes",
    }
    template.resource_count_is("AWS::IAM::Role", 8)
    for resource_type in (
        "AWS::ECS::Service",
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        "AWS::SSM::Document",
    ):
        template.resource_count_is(resource_type, 0)
    assert not template.to_json().get("Outputs")


def test_images_environment_and_secret_isolation(
    task_case: tuple[_Inputs, HostingAppTask, Template],
) -> None:
    inputs, _, template = task_case
    containers = _containers(template)
    assert set(containers) == {"api", "web"}
    api, web = containers["api"], containers["web"]
    assert api["Image"] == inputs.stack.resolve(
        inputs.assets.backend_repository.repository_uri + "@" + _BACKEND_DIGEST
    )
    assert web["Image"] == inputs.stack.resolve(
        inputs.assets.frontend_repository.repository_uri + "@" + _FRONTEND_DIGEST
    )
    assert {entry["Name"]: entry["Value"] for entry in api["Environment"]} == (
        inputs.stack.resolve(application_environment(inputs.database, inputs.resources))
    )
    assert api["Secrets"] == [
        {
            "Name": "FEWIA_DATABASE_PASSWORD",
            "ValueFrom": inputs.stack.resolve(
                application_secrets(inputs.database)["FEWIA_DATABASE_PASSWORD"].arn
            ),
        }
    ]
    assert _logical_id(inputs.database.admin_secret) not in str(api)
    assert web["Environment"] == [
        {"Name": "FEWIA_API_UPSTREAM", "Value": "127.0.0.1:8000"}
    ]
    assert "Secrets" not in web


def test_container_security_ports_health_dependency_and_logs(
    task_case: tuple[_Inputs, HostingAppTask, Template],
) -> None:
    inputs, _, template = task_case
    containers = _containers(template)
    for name, port, log_group in (
        ("api", 8000, inputs.assets.api_logs),
        ("web", 8080, inputs.assets.web_logs),
    ):
        container = containers[name]
        assert container["Essential"] is True
        assert container["ReadonlyRootFilesystem"] is True
        assert container["Privileged"] is False
        assert container["StopTimeout"] == 30
        assert container["PortMappings"] == [{"ContainerPort": port, "Protocol": "tcp"}]
        assert container["LogConfiguration"] == {
            "LogDriver": "awslogs",
            "Options": {
                "awslogs-group": inputs.stack.resolve(log_group.log_group_name),
                "awslogs-region": inputs.stack.resolve(inputs.stack.region),
                "awslogs-stream-prefix": name,
            },
        }
        assert not set(container).intersection(
            {
                "Links",
                "Command",
                "EntryPoint",
                "LinuxParameters",
                "VolumesFrom",
                "ExtraHosts",
                "CredentialSpecs",
                "SystemControls",
            }
        )
    api, web = containers["api"], containers["web"]
    assert api["User"] == "1000:1000"
    assert web["User"] == "101:101"
    assert "HealthCheck" not in web
    assert "DependsOn" not in api
    assert api["HealthCheck"] == {
        "Command": [
            "CMD",
            "python",
            "-c",
            "import urllib.request; urllib.request.urlopen("
            "'http://127.0.0.1:8000/healthz', timeout=5).close()",
        ],
        "Timeout": 5,
        "Interval": 30,
        "Retries": 3,
        "StartPeriod": 30,
    }
    assert web["DependsOn"] == [{"ContainerName": "api", "Condition": "HEALTHY"}]


def test_every_app_container_has_non_root_user(
    task_case: tuple[_Inputs, HostingAppTask, Template],
) -> None:
    _, _, template = task_case
    for container in _containers(template).values():
        assert "User" in container
        uid = str(container["User"]).split(":", 1)[0]
        assert uid != ""
        assert uid not in {"root", "0"}
        assert uid.isdigit()


def test_only_web_mounts_two_private_empty_volumes(
    task_case: tuple[_Inputs, HostingAppTask, Template],
) -> None:
    _, _, template = task_case
    mounts = {
        "nginx-tmp": "/tmp",
        "nginx-conf": "/etc/nginx/conf.d",
    }
    assert _properties(template)["Volumes"] == [{"Name": name} for name in mounts]
    containers = _containers(template)
    assert "MountPoints" not in containers["api"]
    assert containers["web"]["MountPoints"] == [
        {"SourceVolume": name, "ContainerPath": path, "ReadOnly": False}
        for name, path in mounts.items()
    ]


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else [value]


def test_effective_execution_grants_stay_scoped_and_api_has_no_grants(
    task_case: tuple[_Inputs, HostingAppTask, Template],
) -> None:
    inputs, _, template = task_case
    stack = inputs.stack
    app_role = _logical_id(inputs.execution_roles.app_execution_role)
    api_role = _logical_id(inputs.task_roles.api_role)
    repositories = [
        stack.resolve(repository.repository_arn)
        for repository in (
            inputs.assets.backend_repository,
            inputs.assets.frontend_repository,
        )
    ]
    logs = [
        stack.resolve(arn)
        for group in (inputs.assets.api_logs, inputs.assets.web_logs)
        for arn in (group.log_group_arn, group.log_group_arn + ":*")
    ]
    allowed = {
        "ecr:GetAuthorizationToken": ["*"],
        "ecr:BatchCheckLayerAvailability": repositories,
        "ecr:GetDownloadUrlForLayer": repositories,
        "ecr:BatchGetImage": repositories,
        "logs:CreateLogStream": logs,
        "logs:PutLogEvents": logs,
        "secretsmanager:GetSecretValue": [
            stack.resolve(inputs.database.application_secret.secret_arn)
        ],
        "secretsmanager:DescribeSecret": [
            stack.resolve(inputs.database.application_secret.secret_arn)
        ],
    }
    seen: set[str] = set()
    for resource in template.find_resources("AWS::IAM::Policy").values():
        props = resource["Properties"]
        assert {"Ref": api_role} not in props.get("Roles", [])
        if {"Ref": app_role} not in props.get("Roles", []):
            continue
        for statement in props["PolicyDocument"]["Statement"]:
            assert statement["Effect"] == "Allow"
            assert "NotAction" not in statement
            assert "NotResource" not in statement
            resources = _list(statement["Resource"])
            assert resources
            for action in _list(statement["Action"]):
                assert action in allowed
                assert all(resource in allowed[action] for resource in resources)
                seen.add(action)
        assert _logical_id(inputs.database.admin_secret) not in str(props)
    assert seen == set(allowed)
    roles = template.find_resources("AWS::IAM::Role")
    for role_id in (api_role, app_role):
        assert "Policies" not in roles[role_id]["Properties"]
        assert "ManagedPolicyArns" not in roles[role_id]["Properties"]


@pytest.mark.parametrize("slot", ["backend", "frontend"])
@pytest.mark.parametrize("invalid", [None, "latest", "sha256:" + "A" * 64, "sha256:a"])
def test_invalid_either_digest_creates_no_task_or_grants(
    inputs: _Inputs, slot: str, invalid: object
) -> None:
    before = Template.from_stack(inputs.stack).to_json()
    paths = tuple(node.node.path for node in inputs.stack.node.find_all())
    with pytest.raises(ValueError, match="image digest"):
        inputs.build(
            backend_digest=cast(str, invalid) if slot == "backend" else _BACKEND_DIGEST,
            frontend_digest=(
                cast(str, invalid) if slot == "frontend" else _FRONTEND_DIGEST
            ),
        )
    assert tuple(node.node.path for node in inputs.stack.node.find_all()) == paths
    after = Template.from_stack(inputs.stack)
    assert after.to_json() == before
    after.resource_count_is("AWS::ECS::TaskDefinition", 0)


def test_default_stack_does_not_create_app_task(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::ECS::TaskDefinition", 0)
    template.resource_count_is("AWS::ECS::Service", 0)
