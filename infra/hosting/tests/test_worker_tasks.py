from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk.assertions import Template
from constructs import IConstruct

from assets import HostingAssets
from database import HostingDatabase
from execution_roles import HostingExecutionRoles
from network import HostingNetwork
from stack import HostingResources, HostingStack
from task_roles import HostingTaskRoles
from task_settings import image_from_digest
from worker_tasks import HostingWorkerTasks

_ACCOUNT = "111122223333"
_REGION = "us-east-1"
_DIGEST = "sha256:" + "0123456789abcdef" * 4
_Json = dict[str, Any]


@dataclass
class _Case:
    stack: Stack
    assets: HostingAssets
    database: HostingDatabase
    resources: HostingResources
    execution_roles: HostingExecutionRoles
    task_roles: HostingTaskRoles

    def workers(self, digest: str = _DIGEST) -> HostingWorkerTasks:
        return HostingWorkerTasks(
            self.stack,
            "Workers",
            assets=self.assets,
            database=self.database,
            resources=self.resources,
            execution_roles=self.execution_roles,
            task_roles=self.task_roles,
            backend_digest=digest,
        )


@pytest.fixture(params=[False, True], ids=["tokens", "concrete"])
def worker_case(request: pytest.FixtureRequest, tmp_path: Path) -> _Case:
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
        "WorkersTest",
        env=Environment(account=_ACCOUNT, region=_REGION) if concrete else None,
    )
    assets = HostingAssets(stack, "Assets")
    database = HostingDatabase(
        stack, "Database", network=HostingNetwork(stack, "Network")
    )
    resources = HostingResources(stack, "Resources")
    return _Case(
        stack,
        assets,
        database,
        resources,
        HostingExecutionRoles(
            stack, "ExecutionRoles", assets=assets, database=database
        ),
        HostingTaskRoles(stack, "TaskRoles", resources=resources),
    )


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _secret_reference(secret: IConstruct) -> _Json:
    return {
        "Fn::Join": ["", [{"Ref": _logical_id(secret)}, ":password::"]],
    }


def _runtime_policies(case: _Case) -> dict[str, object]:
    policies: dict[str, object] = {}
    for role in (
        case.task_roles.api_role,
        case.task_roles.agent_role,
        case.task_roles.sync_role,
        case.task_roles.bootstrap_role,
    ):
        policy = role.node.try_find_child("DefaultPolicy")
        assert policy is None or isinstance(policy, iam.Policy)
        resource = role.node.default_child
        assert isinstance(resource, iam.CfnRole)
        policies[role.node.path] = {
            "ManagedPolicyArns": case.stack.resolve(resource.managed_policy_arns),
            "Policies": case.stack.resolve(resource.policies),
            "DefaultPolicy": (
                case.stack.resolve(policy.document.to_json())
                if policy is not None
                else None
            ),
        }
    return policies


def _properties(template: Template, resource: IConstruct, kind: str) -> _Json:
    return cast(
        _Json, template.find_resources(kind)[_logical_id(resource)]["Properties"]
    )


def test_tasks_have_exact_container_and_platform_settings(worker_case: _Case) -> None:
    case = worker_case
    workers = case.workers()
    template = Template.from_stack(case.stack)
    agent_environment: dict[str, object] = {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": {
            "Fn::GetAtt": [_logical_id(case.database.instance), "Endpoint.Address"]
        },
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_app",
        "FEWIA_TRANSPORT_MODE": "aws",
        "AWS_REGION": case.stack.resolve(case.stack.region),
        "FEWIA_AWS_AGENT_QUEUE_URL": {"Ref": _logical_id(case.resources.agent_queue)},
        "FEWIA_AWS_SYNC_QUEUE_URL": {"Ref": _logical_id(case.resources.sync_queue)},
        "FEWIA_SPENDING_SOURCE": "manual",
        "FEWIA_BEDROCK_REGION": "us-east-1",
        "FEWIA_BEDROCK_MODEL_ID": "us.amazon.nova-2-lite-v1:0",
    }
    bootstrap_environment = {
        key: value
        for key, value in agent_environment.items()
        if key in {"FEWIA_DATABASE_MODE", "FEWIA_DATABASE_HOST", "FEWIA_DATABASE_NAME"}
    } | {"FEWIA_DATABASE_USER": "fewia_admin"}
    application_secret = _secret_reference(case.database.application_secret)
    admin_secret = _secret_reference(case.database.admin_secret)
    assert application_secret != admin_secret
    cases = (
        (
            workers.agent_task,
            workers.agent_container,
            "agent",
            case.execution_roles.agent_execution_role,
            case.task_roles.agent_role,
            ["python", "-m", "app.worker", "--transport", "aws", "--kind", "agent"],
            agent_environment,
            {"FEWIA_DATABASE_PASSWORD": application_secret},
            case.assets.agent_logs,
            120,
        ),
        (
            workers.bootstrap_task,
            workers.bootstrap_container,
            "bootstrap",
            case.execution_roles.bootstrap_execution_role,
            case.task_roles.bootstrap_role,
            ["python", "-m", "app.bootstrap_hosting", "--run"],
            bootstrap_environment,
            {
                "FEWIA_DATABASE_PASSWORD": admin_secret,
                "FEWIA_APPLICATION_DATABASE_PASSWORD": application_secret,
            },
            case.assets.bootstrap_logs,
            30,
        ),
    )
    for (
        task,
        container,
        name,
        execution,
        runtime,
        command,
        env,
        secrets,
        logs,
        stop,
    ) in cases:
        assert isinstance(task, ecs.FargateTaskDefinition)
        assert isinstance(container, ecs.ContainerDefinition)
        assert container.node.scope is task
        props = _properties(template, task, "AWS::ECS::TaskDefinition")
        assert len(props["ContainerDefinitions"]) == 1
        definition = props["ContainerDefinitions"][0]
        for field in ("Environment", "Secrets"):
            definition[field] = sorted(definition[field], key=lambda item: item["Name"])
        assert props == {
            "Cpu": "512",
            "Memory": "1024",
            "NetworkMode": "awsvpc",
            "RequiresCompatibilities": ["FARGATE"],
            "RuntimePlatform": {
                "CpuArchitecture": "X86_64",
                "OperatingSystemFamily": "LINUX",
            },
            "ExecutionRoleArn": case.stack.resolve(execution.role_arn),
            "TaskRoleArn": case.stack.resolve(runtime.role_arn),
            "Family": task.family,
            "ContainerDefinitions": [
                {
                    "Name": name,
                    "Image": case.stack.resolve(
                        case.assets.backend_repository.repository_uri + "@" + _DIGEST
                    ),
                    "Command": command,
                    "Essential": True,
                    "ReadonlyRootFilesystem": True,
                    "User": "1000:1000",
                    "StopTimeout": stop,
                    "Environment": [
                        {"Name": key, "Value": env[key]} for key in sorted(env)
                    ],
                    "Secrets": [
                        {"Name": key, "ValueFrom": secrets[key]}
                        for key in sorted(secrets)
                    ],
                    "LogConfiguration": {
                        "LogDriver": "awslogs",
                        "Options": {
                            "awslogs-group": {"Ref": _logical_id(logs)},
                            "awslogs-stream-prefix": name,
                            "awslogs-region": case.stack.resolve(case.stack.region),
                        },
                    },
                }
            ],
        }
    template.resource_count_is("AWS::ECS::TaskDefinition", 2)


def test_execution_permissions_stay_scoped_after_bindings(worker_case: _Case) -> None:
    case = worker_case
    case.workers()
    template = Template.from_stack(case.stack)
    for role, secrets, logs in (
        (
            case.execution_roles.agent_execution_role,
            [case.database.application_secret],
            case.assets.agent_logs,
        ),
        (
            case.execution_roles.bootstrap_execution_role,
            [case.database.admin_secret, case.database.application_secret],
            case.assets.bootstrap_logs,
        ),
    ):
        role_properties = _properties(template, role, "AWS::IAM::Role")
        assert not role_properties.get("ManagedPolicyArns")
        assert not role_properties.get("Policies")
        permissions: dict[str, set[str]] = {}
        for resource in template.find_resources("AWS::IAM::Policy").values():
            props = resource["Properties"]
            if {"Ref": _logical_id(role)} not in props["Roles"]:
                continue
            for statement in props["PolicyDocument"]["Statement"]:
                assert statement["Effect"] == "Allow"
                assert set(statement) <= {"Action", "Effect", "Resource", "Sid"}
                actions = statement["Action"]
                if isinstance(actions, str):
                    actions = [actions]
                resources = statement["Resource"]
                if not isinstance(resources, list):
                    resources = [resources]
                for action in actions:
                    permissions.setdefault(action, set()).update(map(repr, resources))
        backend = {
            repr(case.stack.resolve(case.assets.backend_repository.repository_arn))
        }
        secret_arns = {
            repr(case.stack.resolve(secret.secret_arn)) for secret in secrets
        }
        log_arns = {repr(case.stack.resolve(logs.log_group_arn))}
        assert permissions == {
            "ecr:GetAuthorizationToken": {repr("*")},
            "ecr:BatchCheckLayerAvailability": backend,
            "ecr:GetDownloadUrlForLayer": backend,
            "ecr:BatchGetImage": backend,
            "logs:CreateLogStream": log_arns,
            "logs:PutLogEvents": log_arns,
            "secretsmanager:GetSecretValue": secret_arns,
            "secretsmanager:DescribeSecret": secret_arns,
        }


def test_workers_add_only_tasks_and_no_runtime_grants(worker_case: _Case) -> None:
    case = worker_case
    runtime_before = _runtime_policies(case)
    paths_before = {node.node.path for node in case.stack.node.find_all()}
    case.workers()
    assert _runtime_policies(case) == runtime_before
    added_resources = [
        node.cfn_resource_type
        for node in case.stack.node.find_all()
        if isinstance(node, CfnResource) and node.node.path not in paths_before
    ]
    assert added_resources == ["AWS::ECS::TaskDefinition"] * 2
    template = Template.from_stack(case.stack)
    template.resource_count_is("AWS::IAM::Role", 8)
    for kind in (
        "AWS::ECS::Service",
        "AWS::ECS::Cluster",
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::Events::Rule",
        "AWS::Scheduler::Schedule",
        "AWS::SSM::Parameter",
        "AWS::IAM::User",
        "AWS::IAM::AccessKey",
    ):
        template.resource_count_is(kind, 0)
    assert not template.to_json().get("Outputs")


@pytest.mark.parametrize(
    "digest",
    [
        None,
        True,
        256,
        b"sha256:" + b"a" * 64,
        [],
        {},
        "",
        "latest",
        "a" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "SHA256:" + "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        _DIGEST + "\n",
        " " + _DIGEST,
    ],
)
def test_invalid_digest_creates_no_task_resources(
    worker_case: _Case, digest: object
) -> None:
    case = worker_case
    policies_before = _runtime_policies(case)
    resources_before = {
        node.node.path
        for node in case.stack.node.find_all()
        if isinstance(node, CfnResource)
    }
    with (
        patch(
            "worker_tasks.image_from_digest", wraps=image_from_digest
        ) as image_builder,
        patch.object(ecs.ContainerImage, "from_ecr_repository") as image_constructor,
        patch.object(ecs, "FargateTaskDefinition") as task_constructor,
    ):
        with pytest.raises(ValueError, match="image digest"):
            case.workers(cast(str, digest))
        image_builder.assert_called_once_with(case.assets.backend_repository, digest)
        image_constructor.assert_not_called()
        task_constructor.assert_not_called()
    assert _runtime_policies(case) == policies_before
    assert {
        node.node.path
        for node in case.stack.node.find_all()
        if isinstance(node, CfnResource)
    } == resources_before
    Template.from_stack(case.stack).resource_count_is("AWS::ECS::TaskDefinition", 0)


def test_minimal_stack_keeps_worker_tasks_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    template = Template.from_stack(stack)
    expected = {
        "AWS::SQS::Queue": 4,
        "AWS::SQS::QueuePolicy": 4,
        "AWS::S3::Bucket": 1,
        "AWS::S3::BucketPolicy": 1,
    }
    resource_types = {
        resource["Type"] for resource in template.to_json()["Resources"].values()
    }
    assert resource_types <= set(expected) | {"AWS::CDK::Metadata"}
    for kind, count in expected.items():
        template.resource_count_is(kind, count)
    assert set(template.to_json()["Outputs"]) == {
        "AgentQueueUrl",
        "AgentDlqUrl",
        "SyncQueueUrl",
        "SyncDlqUrl",
        "ArtifactBucketName",
    }
