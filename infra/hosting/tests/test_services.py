from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from aws_cdk import App, CfnResource, Environment, Stack, Tags
from aws_cdk import aws_ecs as ecs
from aws_cdk.assertions import Template
from constructs import IConstruct

from app_task import HostingAppTask
from assets import HostingAssets
from database import HostingDatabase
from execution_roles import HostingExecutionRoles
from network import HostingNetwork
from services import HostingServices
from stack import HostingResources, HostingStack
from task_roles import HostingTaskRoles
from worker_tasks import HostingWorkerTasks

_ACCOUNT = "111122223333"
_REGION = "us-east-1"
_DIGEST = "sha256:" + "0123456789abcdef" * 4
_Json = dict[str, Any]


@dataclass
class _Case:
    stack: Stack
    network: HostingNetwork
    app_task: HostingAppTask
    worker_tasks: HostingWorkerTasks
    execution_roles: HostingExecutionRoles
    task_roles: HostingTaskRoles


@pytest.fixture(params=[False, True], ids=["tokens", "concrete"])
def service_case(request: pytest.FixtureRequest, tmp_path: Path) -> _Case:
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
        "ServicesTest",
        env=Environment(account=_ACCOUNT, region=_REGION) if concrete else None,
    )
    network = HostingNetwork(stack, "Network")
    assets = HostingAssets(stack, "Assets")
    database = HostingDatabase(stack, "Database", network=network)
    resources = HostingResources(stack, "Resources")
    execution_roles = HostingExecutionRoles(
        stack, "ExecutionRoles", assets=assets, database=database
    )
    task_roles = HostingTaskRoles(stack, "TaskRoles", resources=resources)
    app_task = HostingAppTask(
        stack,
        "AppTask",
        assets=assets,
        database=database,
        resources=resources,
        execution_roles=execution_roles,
        task_roles=task_roles,
        backend_digest=_DIGEST,
        frontend_digest=_DIGEST,
    )
    worker_tasks = HostingWorkerTasks(
        stack,
        "WorkerTasks",
        assets=assets,
        database=database,
        resources=resources,
        execution_roles=execution_roles,
        task_roles=task_roles,
        backend_digest=_DIGEST,
    )
    Tags.of(app_task.task_definition).add("Component", "app")
    Tags.of(worker_tasks.agent_task).add("Component", "agent")
    return _Case(stack, network, app_task, worker_tasks, execution_roles, task_roles)


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _properties(template: Template, resource: IConstruct, kind: str) -> _Json:
    return cast(
        _Json, template.find_resources(kind)[_logical_id(resource)]["Properties"]
    )


def _services(case: _Case, enabled: bool | None = None) -> HostingServices:
    if enabled is None:
        return HostingServices(
            case.stack,
            "Services",
            network=case.network,
            app_task=case.app_task,
            worker_tasks=case.worker_tasks,
        )
    return HostingServices(
        case.stack,
        "Services",
        network=case.network,
        app_task=case.app_task,
        worker_tasks=case.worker_tasks,
        services_enabled=enabled,
    )


@pytest.mark.parametrize("enabled", [None, False, True], ids=["default", "off", "on"])
def test_services_have_exact_private_deployment_settings(
    service_case: _Case, enabled: bool | None
) -> None:
    case = service_case
    services = _services(case, enabled)
    template = Template.from_stack(case.stack)
    assert isinstance(services.cluster, ecs.Cluster)
    assert isinstance(services.app_service, ecs.FargateService)
    assert isinstance(services.agent_service, ecs.FargateService)
    assert services.cluster.vpc.node.path == case.network.vpc.node.path
    template.resource_count_is("AWS::ECS::Cluster", 1)
    template.resource_count_is("AWS::ECS::Service", 2)
    cluster = _properties(template, services.cluster, "AWS::ECS::Cluster")
    assert cluster["ClusterSettings"] == [
        {"Name": "containerInsights", "Value": "disabled"},
    ]
    assert not cluster.get("CapacityProviders")
    assert not cluster.get("DefaultCapacityProviderStrategy")
    selected = case.network.vpc.select_subnets(subnet_group_name="Application")
    assert {subnet.node.path for subnet in selected.subnets} == {
        subnet.node.path for subnet in case.network.vpc.private_subnets
    }
    for service, task, execution, runtime, component in (
        (
            services.app_service,
            case.app_task.task_definition,
            case.execution_roles.app_execution_role,
            case.task_roles.api_role,
            "app",
        ),
        (
            services.agent_service,
            case.worker_tasks.agent_task,
            case.execution_roles.agent_execution_role,
            case.task_roles.agent_role,
            "agent",
        ),
    ):
        props = _properties(template, service, "AWS::ECS::Service")
        expected: _Json = {
            "Cluster": {"Ref": _logical_id(services.cluster)},
            "TaskDefinition": {"Ref": _logical_id(task)},
            "DesiredCount": 1 if enabled else 0,
            "LaunchType": "FARGATE",
            "PlatformVersion": "1.4.0",
            "EnableExecuteCommand": False,
            "DeploymentController": {"Type": "ECS"},
            "NetworkConfiguration": {
                "AwsvpcConfiguration": {
                    "AssignPublicIp": "DISABLED",
                    "SecurityGroups": [
                        case.stack.resolve(
                            case.network.app_security_group.security_group_id
                        ),
                    ],
                    "Subnets": [
                        case.stack.resolve(subnet.subnet_id)
                        for subnet in selected.subnets
                    ],
                }
            },
            "PropagateTags": "TASK_DEFINITION",
            "EnableECSManagedTags": True,
        }
        if component == "app":
            expected["HealthCheckGracePeriodSeconds"] = 60
        else:
            assert "HealthCheckGracePeriodSeconds" not in props
        for key, value in expected.items():
            assert props[key] == value
        deployment = props["DeploymentConfiguration"]
        assert deployment["DeploymentCircuitBreaker"] == {
            "Enable": True,
            "Rollback": True,
        }
        assert deployment["MinimumHealthyPercent"] == 100
        assert deployment["MaximumPercent"] == 200
        task_props = _properties(template, task, "AWS::ECS::TaskDefinition")
        assert task_props["ExecutionRoleArn"] == case.stack.resolve(execution.role_arn)
        assert task_props["TaskRoleArn"] == case.stack.resolve(runtime.role_arn)
        assert task_props["Tags"] == [{"Key": "Component", "Value": component}]
        if component == "agent":
            assert all(
                "HealthCheck" not in container
                for container in task_props["ContainerDefinitions"]
            )


@pytest.mark.parametrize("enabled", [None, False, True])
def test_services_add_only_cluster_and_two_services(
    service_case: _Case, enabled: bool | None
) -> None:
    case = service_case
    paths_before = {node.node.path for node in case.stack.node.find_all()}
    resources_before = {
        node.node.path: node.cfn_resource_type
        for node in case.stack.node.find_all()
        if isinstance(node, CfnResource)
    }
    _services(case, enabled)
    template = Template.from_stack(case.stack)
    paths_after = {node.node.path for node in case.stack.node.find_all()}
    assert paths_before <= paths_after
    resources_after = {
        node.node.path: node.cfn_resource_type
        for node in case.stack.node.find_all()
        if isinstance(node, CfnResource)
    }
    for path, kind in resources_before.items():
        assert resources_after[path] == kind
    added_resources = [
        kind for path, kind in resources_after.items() if path not in resources_before
    ]
    assert sorted(added_resources) == [
        "AWS::ECS::Cluster",
        "AWS::ECS::Service",
        "AWS::ECS::Service",
    ]
    resources = template.to_json()["Resources"]
    assert len(resources) == len(resources_before) + 3
    assert not template.to_json().get("Outputs")
    for kind in (
        "AWS::Events::Rule",
        "AWS::Scheduler::Schedule",
        "AWS::ApplicationAutoScaling::ScalableTarget",
        "AWS::ApplicationAutoScaling::ScalingPolicy",
        "AWS::ECS::CapacityProvider",
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::ElasticLoadBalancingV2::Listener",
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        "AWS::ServiceDiscovery::Service",
        "AWS::Route53::RecordSet",
        "AWS::CertificateManager::Certificate",
        "AWS::IAM::User",
        "AWS::IAM::AccessKey",
    ):
        template.resource_count_is(kind, 0)


@pytest.mark.parametrize(
    "enabled", [None, 0, 1, -1, "false", "true", [], {}, 0.0, b"1"]
)
def test_invalid_activation_creates_no_resources(
    service_case: _Case, enabled: object
) -> None:
    case = service_case
    baseline = Template.from_stack(case.stack).to_json()
    paths_before = {node.node.path for node in case.stack.node.find_all()}
    with (
        patch.object(ecs, "Cluster") as cluster_constructor,
        patch.object(ecs, "FargateService") as service_constructor,
        pytest.raises(ValueError, match="services_enabled MUST be a bool"),
    ):
        HostingServices(
            case.stack,
            "InvalidServices",
            network=case.network,
            app_task=case.app_task,
            worker_tasks=case.worker_tasks,
            services_enabled=cast(bool, enabled),
        )
    cluster_constructor.assert_not_called()
    service_constructor.assert_not_called()
    assert {node.node.path for node in case.stack.node.find_all()} == paths_before
    assert Template.from_stack(case.stack).to_json() == baseline


def test_hosting_stack_keeps_services_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    template = Template.from_stack(stack)
    for kind in ("AWS::ECS::Cluster", "AWS::ECS::Service", "AWS::ECS::TaskDefinition"):
        template.resource_count_is(kind, 0)
