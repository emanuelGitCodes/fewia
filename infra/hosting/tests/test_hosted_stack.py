import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast
from unittest.mock import patch

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk.assertions import Template
from constructs import IConstruct

from app_task import HostingAppTask
from assets import HostingAssets
from database import HostingDatabase
from deployment_config import REGION, DeploymentConfig, RuntimeConfig
from edge import HostingEdge
from execution_roles import HostingExecutionRoles
from hosted_stack import HostedDemoStack
from identity import HostingIdentity
from network import HostingNetwork
from services import HostingServices
from stack import HostingResources, HostingStack
from task_roles import HostingTaskRoles
from worker_tasks import HostingWorkerTasks

_ACCOUNT = "111122223333"
_BACKEND = "sha256:" + "a" * 64
_FRONTEND = "sha256:" + "b" * 64
_CERTIFICATE = (
    f"arn:aws:acm:{REGION}:{_ACCOUNT}:certificate/12345678-1234-abcd-1234-123456789abc"
)
_RUNTIME = RuntimeConfig(
    hostname="demo.example.test",
    domain_prefix="fewia-demo",
    certificate_arn=_CERTIFICATE,
    backend_digest=_BACKEND,
    frontend_digest=_FRONTEND,
)
_Phase = Literal["foundation", "bootstrap", "active"]
_Json = dict[str, Any]
_FOUNDATION_OUTPUTS = {
    "DeploymentPhase",
    "BackendRepositoryName",
    "BackendRepositoryUri",
    "FrontendRepositoryName",
    "FrontendRepositoryUri",
    "DatabaseInstanceIdentifier",
    "ApplicationSubnetIds",
    "ApplicationSecurityGroupId",
}


def _app(tmp_path: Path) -> App:
    return App(
        outdir=str(tmp_path / "assembly"),
        context={
            f"availability-zones:account={_ACCOUNT}:region={REGION}": [
                "us-east-1a",
                "us-east-1b",
            ],
        },
    )


def _config(phase: _Phase) -> DeploymentConfig:
    return DeploymentConfig(
        account=_ACCOUNT,
        phase=phase,
        runtime=None if phase == "foundation" else _RUNTIME,
    )


def _build(tmp_path: Path, phase: _Phase) -> HostedDemoStack:
    return HostedDemoStack(_app(tmp_path), "HostedDemo", config=_config(phase))


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _properties(template: Template, resource: IConstruct) -> _Json:
    return cast(
        _Json, template.to_json()["Resources"][_logical_id(resource)]["Properties"]
    )


@pytest.fixture(params=["foundation", "bootstrap", "active"])
def phase(request: pytest.FixtureRequest) -> _Phase:
    return cast(_Phase, request.param)


@pytest.fixture
def demo(tmp_path: Path, phase: _Phase) -> HostedDemoStack:
    return _build(tmp_path, phase)


def test_construct_exports_and_stable_ids(demo: HostedDemoStack, phase: _Phase) -> None:
    assert demo.account == _ACCOUNT
    assert demo.region == REGION
    assert demo.termination_protection is True
    for name, construct, kind in (
        ("Network", demo.network, HostingNetwork),
        ("Resources", demo.resources, HostingResources),
        ("Database", demo.database, HostingDatabase),
        ("Assets", demo.assets, HostingAssets),
        ("ExecutionRoles", demo.execution_roles, HostingExecutionRoles),
        ("TaskRoles", demo.task_roles, HostingTaskRoles),
    ):
        assert isinstance(construct, kind)
        assert demo.node.find_child(name) is construct
    for runtime_name, runtime_construct, runtime_kind in (
        ("Identity", demo.identity, HostingIdentity),
        ("AppTask", demo.app_task, HostingAppTask),
        ("WorkerTasks", demo.worker_tasks, HostingWorkerTasks),
        ("Services", demo.services, HostingServices),
        ("Edge", demo.edge, HostingEdge),
    ):
        if phase == "foundation":
            assert runtime_construct is None
            assert demo.node.try_find_child(runtime_name) is None
        else:
            assert isinstance(runtime_construct, runtime_kind)
            assert demo.node.find_child(runtime_name) is runtime_construct


def test_complete_templates_have_exact_phase_resources(
    demo: HostedDemoStack, phase: _Phase
) -> None:
    template = Template.from_stack(demo)
    runtime = phase != "foundation"
    for kind, count in (
        ("AWS::ECS::TaskDefinition", 3),
        ("AWS::ECS::Service", 2),
        ("AWS::ECS::Cluster", 1),
        ("AWS::Cognito::UserPool", 1),
        ("AWS::Cognito::UserPoolClient", 1),
        ("AWS::Cognito::UserPoolDomain", 1),
        ("AWS::ElasticLoadBalancingV2::LoadBalancer", 1),
        ("AWS::ElasticLoadBalancingV2::Listener", 1),
        ("AWS::ElasticLoadBalancingV2::ListenerRule", 1),
        ("AWS::ElasticLoadBalancingV2::TargetGroup", 1),
    ):
        template.resource_count_is(kind, count if runtime else 0)
    for kind in (
        "AWS::Route53::RecordSet",
        "AWS::CertificateManager::Certificate",
        "AWS::IAM::User",
        "AWS::IAM::AccessKey",
        "AWS::Cognito::UserPoolUser",
        "AWS::Events::Rule",
        "AWS::Scheduler::Schedule",
        "AWS::ApplicationAutoScaling::ScalableTarget",
    ):
        template.resource_count_is(kind, 0)
    if not runtime:
        assert not any(
            resource["Type"].startswith(
                ("AWS::ECS::", "AWS::Cognito::", "AWS::ElasticLoadBalancingV2::")
            )
            for resource in template.to_json()["Resources"].values()
        )
        return
    assert demo.services is not None
    assert demo.app_task is not None
    assert demo.worker_tasks is not None
    for service, task in (
        (demo.services.app_service, demo.app_task.task_definition),
        (demo.services.agent_service, demo.worker_tasks.agent_task),
    ):
        props = _properties(template, service)
        assert props["DesiredCount"] == (1 if phase == "active" else 0)
        assert props["TaskDefinition"] == {"Ref": _logical_id(task)}
        assert props["Cluster"] == {"Ref": _logical_id(demo.services.cluster)}
    for task, execution, runtime_role in (
        (
            demo.app_task.task_definition,
            demo.execution_roles.app_execution_role,
            demo.task_roles.api_role,
        ),
        (
            demo.worker_tasks.agent_task,
            demo.execution_roles.agent_execution_role,
            demo.task_roles.agent_role,
        ),
        (
            demo.worker_tasks.bootstrap_task,
            demo.execution_roles.bootstrap_execution_role,
            demo.task_roles.bootstrap_role,
        ),
    ):
        props = _properties(template, task)
        assert props["ExecutionRoleArn"] == demo.resolve(execution.role_arn)
        assert props["TaskRoleArn"] == demo.resolve(runtime_role.role_arn)
    task_images = {
        container["Name"]: container["Image"]
        for task in template.find_resources("AWS::ECS::TaskDefinition").values()
        for container in task["Properties"]["ContainerDefinitions"]
    }
    assert set(task_images) == {"api", "web", "agent", "bootstrap"}
    for name, image in task_images.items():
        repository = (
            demo.assets.frontend_repository
            if name == "web"
            else demo.assets.backend_repository
        )
        digest = _FRONTEND if name == "web" else _BACKEND
        assert image == demo.resolve(f"{repository.repository_uri}@{digest}")


def test_persistent_resources_keep_ids_and_definitions_across_phases(
    tmp_path: Path,
) -> None:
    templates = {
        phase: Template.from_stack(_build(tmp_path / phase, phase)).to_json()
        for phase in ("foundation", "bootstrap", "active")
    }
    foundation = templates["foundation"]["Resources"]
    stable_types = {
        "AWS::EC2::VPC",
        "AWS::EC2::Subnet",
        "AWS::EC2::SecurityGroup",
        "AWS::RDS::DBInstance",
        "AWS::RDS::DBSubnetGroup",
        "AWS::RDS::DBParameterGroup",
        "AWS::SecretsManager::Secret",
        "AWS::SecretsManager::SecretTargetAttachment",
        "AWS::S3::Bucket",
        "AWS::S3::BucketPolicy",
        "AWS::SQS::Queue",
        "AWS::SQS::QueuePolicy",
        "AWS::ECR::Repository",
        "AWS::Logs::LogGroup",
        "AWS::IAM::Role",
    }
    persistent = {
        key: value for key, value in foundation.items() if value["Type"] in stable_types
    }
    assert persistent
    for phase in ("bootstrap", "active"):
        resources = templates[phase]["Resources"]
        assert {
            key: value
            for key, value in resources.items()
            if value["Type"] in stable_types
        } == persistent


def test_activation_changes_only_two_counts_and_phase_output(tmp_path: Path) -> None:
    bootstrap = Template.from_stack(
        _build(tmp_path / "bootstrap", "bootstrap")
    ).to_json()
    active = Template.from_stack(_build(tmp_path / "active", "active")).to_json()
    normalized = deepcopy(active)
    changed: list[str] = []
    for key, resource in normalized["Resources"].items():
        if resource["Type"] == "AWS::ECS::Service":
            assert resource["Properties"]["DesiredCount"] == 1
            assert bootstrap["Resources"][key]["Properties"]["DesiredCount"] == 0
            resource["Properties"]["DesiredCount"] = 0
            changed.append(key)
    assert len(changed) == 2
    assert normalized["Outputs"]["DeploymentPhase"] == {"Value": "active"}
    normalized["Outputs"]["DeploymentPhase"]["Value"] = "bootstrap"
    assert normalized == bootstrap


def test_all_outputs_reference_owned_objects_without_secret_values(
    demo: HostedDemoStack, phase: _Phase
) -> None:
    expected = {
        "DeploymentPhase": phase,
        "BackendRepositoryName": demo.assets.backend_repository.repository_name,
        "BackendRepositoryUri": demo.assets.backend_repository.repository_uri,
        "FrontendRepositoryName": demo.assets.frontend_repository.repository_name,
        "FrontendRepositoryUri": demo.assets.frontend_repository.repository_uri,
        "DatabaseInstanceIdentifier": demo.database.instance.instance_identifier,
        "ApplicationSubnetIds": ",".join(
            subnet.subnet_id for subnet in demo.network.vpc.private_subnets
        ),
        "ApplicationSecurityGroupId": (
            demo.network.app_security_group.security_group_id
        ),
    }
    if phase != "foundation":
        assert demo.services is not None
        assert demo.worker_tasks is not None
        assert demo.edge is not None
        assert demo.identity is not None
        expected.update(
            {
                "ClusterName": demo.services.cluster.cluster_name,
                "ClusterArn": demo.services.cluster.cluster_arn,
                "AppServiceName": demo.services.app_service.service_name,
                "AgentServiceName": demo.services.agent_service.service_name,
                "BootstrapTaskDefinitionArn": (
                    demo.worker_tasks.bootstrap_task.task_definition_arn
                ),
                "LoadBalancerDnsName": demo.edge.load_balancer.load_balancer_dns_name,
                "LoadBalancerHostedZoneId": (
                    demo.edge.load_balancer.load_balancer_canonical_hosted_zone_id
                ),
                "UserPoolId": demo.identity.user_pool.user_pool_id,
                "UserPoolClientId": demo.identity.client.user_pool_client_id,
                "DemoUrl": f"https://{_RUNTIME.hostname}/",
            }
        )
    else:
        assert set(expected) == _FOUNDATION_OUTPUTS
    outputs = Template.from_stack(demo).to_json()["Outputs"]
    assert outputs == {
        key: {"Value": demo.resolve(value)} for key, value in expected.items()
    }
    serialized = json.dumps(outputs).lower()
    for forbidden in ("password", "secret", "dynamic", "resolve:", "getsecretvalue"):
        assert forbidden not in serialized


def test_tasks_and_database_use_only_owned_private_network(
    demo: HostedDemoStack, phase: _Phase
) -> None:
    template = Template.from_stack(demo)
    private_ids = [
        demo.resolve(subnet.subnet_id) for subnet in demo.network.vpc.private_subnets
    ]
    public_ids = [
        demo.resolve(subnet.subnet_id) for subnet in demo.network.vpc.public_subnets
    ]
    isolated_ids = [
        demo.resolve(subnet.subnet_id) for subnet in demo.network.vpc.isolated_subnets
    ]
    assert len(private_ids) == len(public_ids) == len(isolated_ids) == 2
    assert all(subnet not in public_ids + isolated_ids for subnet in private_ids)
    database = _properties(template, demo.database.instance)
    assert database["PubliclyAccessible"] is False
    assert database["VPCSecurityGroups"] == [
        demo.resolve(demo.network.database_security_group.security_group_id)
    ]
    subnet_groups = template.find_resources("AWS::RDS::DBSubnetGroup")
    assert len(subnet_groups) == 1
    assert next(iter(subnet_groups.values()))["Properties"]["SubnetIds"] == isolated_ids
    template.resource_count_is("AWS::EC2::SecurityGroup", 3)
    assert "DefaultSecurityGroup" not in json.dumps(template.to_json())
    for service in template.find_resources("AWS::ECS::Service").values():
        props = service["Properties"]
        assert props["EnableExecuteCommand"] is False
        assert props["NetworkConfiguration"]["AwsvpcConfiguration"] == {
            "AssignPublicIp": "DISABLED",
            "Subnets": private_ids,
            "SecurityGroups": [
                demo.resolve(demo.network.app_security_group.security_group_id)
            ],
        }
    if phase != "foundation":
        assert demo.edge is not None
        load_balancer = _properties(template, demo.edge.load_balancer)
        assert load_balancer["Subnets"] == public_ids
        assert load_balancer["SecurityGroups"] == [
            demo.resolve(demo.network.edge_security_group.security_group_id)
        ]


@pytest.mark.parametrize("phase", ["bootstrap", "active"])
def test_composed_edge_authenticates_owned_app_service(
    tmp_path: Path, phase: _Phase
) -> None:
    demo = _build(tmp_path, phase)
    assert demo.edge is not None
    assert demo.identity is not None
    assert demo.services is not None
    template = Template.from_stack(demo)
    listener = _properties(template, demo.edge.listener)
    assert listener["Protocol"] == "HTTPS"
    assert listener["Port"] == 443
    assert listener["Certificates"] == [{"CertificateArn": _CERTIFICATE}]
    assert listener["DefaultActions"] == [
        {
            "Type": "fixed-response",
            "FixedResponseConfig": {"ContentType": "text/plain", "StatusCode": "404"},
        }
    ]
    rule = _properties(template, demo.edge.rule)
    assert rule["Conditions"] == [
        {"Field": "host-header", "HostHeaderConfig": {"Values": [_RUNTIME.hostname]}}
    ]
    assert rule["ListenerArn"] == {"Ref": _logical_id(demo.edge.listener)}
    assert rule["Actions"] == [
        {
            "Type": "authenticate-cognito",
            "Order": 1,
            "AuthenticateCognitoConfig": {
                "UserPoolArn": demo.resolve(demo.identity.user_pool.user_pool_arn),
                "UserPoolClientId": demo.resolve(
                    demo.identity.client.user_pool_client_id
                ),
                "UserPoolDomain": demo.resolve(demo.identity.domain.domain_name),
                "Scope": "openid",
                "OnUnauthenticatedRequest": "authenticate",
                "SessionTimeout": 3600,
            },
        },
        {
            "Type": "forward",
            "Order": 2,
            "TargetGroupArn": {"Ref": _logical_id(demo.edge.target_group)},
        },
    ]
    assert _properties(template, demo.services.app_service)["LoadBalancers"] == [
        {
            "ContainerName": "web",
            "ContainerPort": 80,
            "TargetGroupArn": {"Ref": _logical_id(demo.edge.target_group)},
        }
    ]
    pool = _properties(template, demo.identity.user_pool)
    assert pool["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"] is True
    client = _properties(template, demo.identity.client)
    assert client["CallbackURLs"] == [f"https://{_RUNTIME.hostname}/oauth2/idpresponse"]
    assert client["LogoutURLs"] == [f"https://{_RUNTIME.hostname}/"]


def _statements_for_role(template: Template, role: IConstruct) -> list[_Json]:
    role_ref = {"Ref": _logical_id(role)}
    return [
        statement
        for policy in template.find_resources("AWS::IAM::Policy").values()
        if role_ref in policy["Properties"].get("Roles", [])
        for statement in policy["Properties"]["PolicyDocument"]["Statement"]
    ]


def _list[_T](value: _T | list[_T]) -> list[_T]:
    return value if isinstance(value, list) else [value]


def test_secret_grants_stay_scoped_after_all_cdk_bindings(
    demo: HostedDemoStack,
) -> None:
    template = Template.from_stack(demo)
    template.resource_count_is("AWS::IAM::Role", 8)
    application = demo.resolve(demo.database.application_secret.secret_arn)
    administrator = demo.resolve(demo.database.admin_secret.secret_arn)
    execution_roles = demo.execution_roles
    for role in (
        execution_roles.app_execution_role,
        execution_roles.agent_execution_role,
        execution_roles.sync_execution_role,
        execution_roles.bootstrap_execution_role,
    ):
        allowed = [application]
        if role is execution_roles.bootstrap_execution_role:
            allowed.append(administrator)
        secret_resources: list[Any] = []
        for statement in _statements_for_role(template, role):
            if statement["Effect"] != "Allow":
                continue
            actions = _list(statement["Action"])
            if any(
                action.startswith("secretsmanager:") or action == "*"
                for action in actions
            ):
                assert set(actions) <= {
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                }
                resources = _list(statement["Resource"])
                assert all(resource in allowed for resource in resources)
                secret_resources.extend(resources)
        assert all(resource in secret_resources for resource in allowed)
        role_props = _properties(template, role)
        assert not role_props.get("ManagedPolicyArns")
        assert not role_props.get("Policies")
    for role in (
        demo.task_roles.api_role,
        demo.task_roles.agent_role,
        demo.task_roles.sync_role,
        demo.task_roles.bootstrap_role,
    ):
        for statement in _statements_for_role(template, role):
            actions = _list(statement["Action"])
            assert not any(
                action.startswith("secretsmanager:") or action == "*"
                for action in actions
            )
        role_props = _properties(template, role)
        assert not role_props.get("ManagedPolicyArns")
        assert not role_props.get("Policies")
    for task in template.find_resources("AWS::ECS::TaskDefinition").values():
        for container in task["Properties"]["ContainerDefinitions"]:
            environment = json.dumps(container.get("Environment", []))
            assert "resolve:secretsmanager" not in environment
            assert _logical_id(demo.database.admin_secret) not in environment
            assert _logical_id(demo.database.application_secret) not in environment
            secrets = container.get("Secrets", [])
            if container["Name"] == "web":
                assert not secrets
                continue
            assert secrets
            serialized = json.dumps(secrets)
            allowed_secrets = [demo.database.application_secret.secret_arn]
            if container["Name"] == "bootstrap":
                allowed_secrets.append(demo.database.admin_secret.secret_arn)
            for secret in secrets:
                assert secret["ValueFrom"] in [
                    demo.resolve(f"{arn}:{field}::")
                    for arn in allowed_secrets
                    for field in ("username", "password")
                ]
            if container["Name"] != "bootstrap":
                assert _logical_id(demo.database.admin_secret) not in serialized


@pytest.mark.parametrize(
    "config",
    [
        replace(_config("foundation"), account="123"),
        replace(_config("foundation"), account=cast(str, 111122223333)),
        replace(_config("foundation"), account=_ACCOUNT + "\n"),
        replace(_config("foundation"), phase=cast(_Phase, "unknown")),
        replace(_config("foundation"), phase=cast(_Phase, 1)),
        replace(_config("foundation"), runtime=_RUNTIME),
        replace(_config("bootstrap"), runtime=None),
        replace(_config("active"), runtime=None),
        replace(_config("bootstrap"), runtime=cast(RuntimeConfig, {})),
        *[
            replace(_config("bootstrap"), runtime=replace(_RUNTIME, **{field: value}))
            for field, value in (
                ("hostname", "https://demo.example.test"),
                ("hostname", "demo.example.test\n"),
                ("domain_prefix", "aws-demo"),
                ("certificate_arn", _CERTIFICATE.replace(_ACCOUNT, "999900001111")),
                ("certificate_arn", _CERTIFICATE.replace(REGION, "us-west-2")),
                ("certificate_arn", _CERTIFICATE + "\n"),
                ("backend_digest", "latest"),
                ("frontend_digest", "sha256:" + "g" * 64),
                ("frontend_digest", _FRONTEND + "\n"),
            )
        ],
    ],
)
def test_forged_config_fails_before_stack_initialization(
    tmp_path: Path, config: DeploymentConfig
) -> None:
    app = _app(tmp_path)
    before = tuple(child.node.path for child in app.node.find_all())
    with (
        patch.object(Stack, "__init__") as initialize,
        pytest.raises(ValueError, match="deployment configuration is invalid"),
    ):
        HostedDemoStack(app, "Invalid", config=config)
    initialize.assert_not_called()
    assert tuple(child.node.path for child in app.node.find_all()) == before
    assert app.node.try_find_child("Invalid") is None


def test_non_dataclass_config_creates_no_child_stack(tmp_path: Path) -> None:
    app = _app(tmp_path)
    before = tuple(child.node.path for child in app.node.find_all())
    with patch.object(Stack, "__init__") as initialize, pytest.raises(TypeError):
        HostedDemoStack(app, "Invalid", config=cast(DeploymentConfig, {}))
    initialize.assert_not_called()
    assert tuple(child.node.path for child in app.node.find_all()) == before


def test_full_synthesis_needs_no_environment_or_lookups(
    tmp_path: Path, phase: _Phase, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "CDK_DEFAULT_ACCOUNT",
        "CDK_DEFAULT_REGION",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.delenv(name, raising=False)
    demo = _build(tmp_path, phase)
    app = demo.node.root
    assert isinstance(app, App)
    assembly = app.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing")
    artifact = assembly.get_stack_artifact(demo.artifact_id)
    assert artifact.termination_protection is True
    assert artifact.environment.account == _ACCOUNT
    assert artifact.environment.region == REGION


def test_existing_minimal_stack_keeps_only_queues_and_artifacts(tmp_path: Path) -> None:
    stack = HostingStack(
        _app(tmp_path), "Minimal", env=Environment(account=_ACCOUNT, region=REGION)
    )
    template = Template.from_stack(stack)
    resource_types = {
        resource["Type"] for resource in template.to_json()["Resources"].values()
    }
    assert resource_types == {
        "AWS::SQS::Queue",
        "AWS::SQS::QueuePolicy",
        "AWS::S3::Bucket",
        "AWS::S3::BucketPolicy",
    }
    template.resource_count_is("AWS::SQS::Queue", 4)
    template.resource_count_is("AWS::S3::Bucket", 1)
    assert template.to_json()["Outputs"] == {
        key: {"Value": stack.resolve(value)}
        for key, value in {
            "AgentQueueUrl": stack.resources.agent_queue.queue_url,
            "AgentDlqUrl": stack.resources.agent_dlq.queue_url,
            "SyncQueueUrl": stack.resources.sync_queue.queue_url,
            "SyncDlqUrl": stack.resources.sync_dlq.queue_url,
            "ArtifactBucketName": stack.resources.artifact_bucket.bucket_name,
        }.items()
    }
