import json
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, CfnResource, Environment, Fn, Stack, Token
from aws_cdk import aws_iam as iam
from aws_cdk.assertions import Template
from constructs import IConstruct

from assets import HostingAssets
from database import HostingDatabase
from execution_roles import HostingExecutionRoles
from network import HostingNetwork
from stack import HostingStack
from task_trust import new_task_role

_ACCOUNT = "111122223333"
_REGION = "us-east-1"
_Case = tuple[Stack, HostingAssets, HostingDatabase, HostingExecutionRoles, Template]


@pytest.fixture(params=[False, True], ids=["tokens", "concrete"])
def roles_case(request: pytest.FixtureRequest, tmp_path: Path) -> _Case:
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
        "RolesTest",
        env=Environment(account=_ACCOUNT, region=_REGION) if concrete else None,
    )
    assets = HostingAssets(stack, "Assets")
    database = HostingDatabase(
        stack, "Database", network=HostingNetwork(stack, "Network")
    )
    roles = HostingExecutionRoles(stack, "Execution", assets=assets, database=database)
    return stack, assets, database, roles, Template.from_stack(stack)


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _roles(roles: HostingExecutionRoles) -> tuple[iam.Role, ...]:
    return (
        roles.app_execution_role,
        roles.agent_execution_role,
        roles.sync_execution_role,
        roles.bootstrap_execution_role,
    )


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else [value]


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _trust(stack: Stack) -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": "sts:AssumeRole",
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": stack.resolve(stack.account)},
                    "ArnLike": {
                        "aws:SourceArn": stack.resolve(
                            Fn.join(
                                "",
                                [
                                    "arn:",
                                    stack.partition,
                                    ":ecs:",
                                    stack.region,
                                    ":",
                                    stack.account,
                                    ":*",
                                ],
                            )
                        )
                    },
                },
            }
        ],
    }


def _statements(template: Template, role: iam.Role) -> list[dict[str, Any]]:
    policies = [
        resource["Properties"]
        for resource in template.find_resources("AWS::IAM::Policy").values()
        if resource["Properties"].get("Roles") == [{"Ref": _logical_id(role)}]
    ]
    assert len(policies) == 1
    props = policies[0]
    assert set(props) == {"PolicyDocument", "PolicyName", "Roles"}
    document = props["PolicyDocument"]
    assert set(document) == {"Version", "Statement"}
    assert document["Version"] == "2012-10-17"
    statements: list[dict[str, Any]] = document["Statement"]
    assert len(statements) == 4
    for statement in statements:
        assert set(statement) == {"Action", "Effect", "Resource"}
        assert statement["Effect"] == "Allow"
    return statements


def test_helper_adds_only_one_role_with_ecs_trust(tmp_path: Path) -> None:
    stack = Stack(App(outdir=str(tmp_path / "helper")), "Helper")
    role = new_task_role(stack, "TaskRole")
    assert isinstance(role, iam.Role)
    template = Template.from_stack(stack)
    resources = template.find_resources("AWS::IAM::Role")
    assert resources == {
        _logical_id(role): {
            "Type": "AWS::IAM::Role",
            "Properties": {"AssumeRolePolicyDocument": _trust(stack)},
        }
    }
    assert {item["Type"] for item in template.to_json()["Resources"].values()} <= {
        "AWS::IAM::Role",
        "AWS::CDK::Metadata",
    }
    assert not template.to_json().get("Outputs")


def test_exports_are_distinct_roles_with_exact_trust(roles_case: _Case) -> None:
    stack, _, _, exports, template = roles_case
    roles = _roles(exports)
    assert all(isinstance(role, iam.Role) for role in roles)
    ids = {_logical_id(role) for role in roles}
    assert len(ids) == 4
    resources = template.find_resources("AWS::IAM::Role")
    assert set(resources) == ids
    for resource in resources.values():
        assert resource["Properties"] == {"AssumeRolePolicyDocument": _trust(stack)}


def test_every_action_has_only_its_assigned_resources(roles_case: _Case) -> None:
    stack, assets, database, exports, template = roles_case
    backend = assets.backend_repository.repository_arn
    application = database.application_secret.secret_arn
    assignments = (
        (
            exports.app_execution_role,
            [backend, assets.frontend_repository.repository_arn],
            [assets.api_logs, assets.web_logs],
            [application],
        ),
        (exports.agent_execution_role, [backend], [assets.agent_logs], [application]),
        (exports.sync_execution_role, [backend], [assets.sync_logs], [application]),
        (
            exports.bootstrap_execution_role,
            [backend],
            [assets.bootstrap_logs],
            [database.admin_secret.secret_arn, application],
        ),
    )
    template.resource_count_is("AWS::IAM::Policy", 4)
    for role, repositories, groups, secrets in assignments:
        expected = {("ecr:GetAuthorizationToken", _canonical("*"))}
        expected.update(
            (action, _canonical(stack.resolve(arn)))
            for action in (
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
            )
            for arn in repositories
        )
        expected.update(
            (action, _canonical({"Fn::GetAtt": [_logical_id(group), "Arn"]}))
            for action in ("logs:CreateLogStream", "logs:PutLogEvents")
            for group in groups
        )
        expected.update(
            ("secretsmanager:GetSecretValue", _canonical(stack.resolve(arn)))
            for arn in secrets
        )
        actual = {
            (action, _canonical(resource))
            for statement in _statements(template, role)
            for action in _list(statement["Action"])
            for resource in _list(statement["Resource"])
        }
        assert actual == expected


def test_no_admin_secret_leaks_or_extra_service_permissions(roles_case: _Case) -> None:
    stack, _, database, exports, template = roles_case
    admin = _canonical({"Ref": _logical_id(database.admin_secret)})
    application = _canonical({"Ref": _logical_id(database.application_secret)})
    assert _canonical(stack.resolve(database.admin_secret.secret_arn)) == admin
    assert (
        _canonical(stack.resolve(database.application_secret.secret_arn)) == application
    )
    allowed_actions = {
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "secretsmanager:GetSecretValue",
    }
    for role in _roles(exports):
        secret_resources: set[str] = set()
        for statement in _statements(template, role):
            actions = set(_list(statement["Action"]))
            assert actions <= allowed_actions
            if "ecr:GetAuthorizationToken" in actions:
                assert actions == {"ecr:GetAuthorizationToken"}
                assert _list(statement["Resource"]) == ["*"]
                continue
            assert all(
                "*" not in _canonical(resource)
                for resource in _list(statement["Resource"])
            )
            if "secretsmanager:GetSecretValue" in actions:
                secret_resources.update(map(_canonical, _list(statement["Resource"])))
        assert secret_resources == (
            {admin, application}
            if role is exports.bootstrap_execution_role
            else {application}
        )
    for resource_type in (
        "AWS::IAM::User",
        "AWS::IAM::AccessKey",
        "AWS::IAM::ManagedPolicy",
        "AWS::ECS::TaskDefinition",
        "AWS::ECS::Service",
    ):
        template.resource_count_is(resource_type, 0)
    assert not template.to_json().get("Outputs")


def test_synthesis_is_offline_with_unresolved_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "CDK_DEFAULT_ACCOUNT",
        "CDK_DEFAULT_REGION",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        monkeypatch.delenv(name, raising=False)
    app = App(outdir=str(tmp_path / "offline"), context={})
    stack = Stack(app, "Offline")
    assets = HostingAssets(stack, "Assets")
    database = HostingDatabase(
        stack, "Database", network=HostingNetwork(stack, "Network")
    )
    HostingExecutionRoles(stack, "Execution", assets=assets, database=database)
    assert Token.is_unresolved(stack.account)
    assert Token.is_unresolved(stack.region)
    Template.from_stack(stack).resource_count_is("AWS::IAM::Role", 4)
    assembly = app.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing")


def test_hosting_stack_keeps_execution_roles_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    assert not any(
        isinstance(child, HostingExecutionRoles) for child in stack.node.children
    )
    template = Template.from_stack(stack)
    expected = {
        "AWS::SQS::Queue": 4,
        "AWS::SQS::QueuePolicy": 4,
        "AWS::S3::Bucket": 1,
        "AWS::S3::BucketPolicy": 1,
    }
    for resource_type, count in expected.items():
        template.resource_count_is(resource_type, count)
    assert {item["Type"] for item in template.to_json()["Resources"].values()} <= (
        set(expected) | {"AWS::CDK::Metadata"}
    )
    assert set(template.to_json()["Outputs"]) == {
        "AgentQueueUrl",
        "AgentDlqUrl",
        "SyncQueueUrl",
        "SyncDlqUrl",
        "ArtifactBucketName",
    }
