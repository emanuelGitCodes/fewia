import json
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, CfnResource, Environment, Fn, Stack
from aws_cdk import aws_iam as iam
from aws_cdk.assertions import Template
from constructs import IConstruct

from stack import HostingResources, HostingStack
from task_roles import HostingTaskRoles
from task_trust import new_task_role

_ACCOUNT = "111122223333"
_REGION = "us-east-1"
_Case = tuple[Stack, HostingResources, HostingTaskRoles, Template]


@pytest.fixture(params=[False, True], ids=["tokens", "concrete"])
def roles_case(request: pytest.FixtureRequest, tmp_path: Path) -> _Case:
    concrete: bool = request.param
    app = App(outdir=str(tmp_path / "assembly"), context={})
    stack = Stack(
        app,
        "RolesTest",
        env=Environment(account=_ACCOUNT, region=_REGION) if concrete else None,
    )
    resources = HostingResources(stack, "Resources")
    roles = HostingTaskRoles(stack, "TaskRoles", resources=resources)
    return stack, resources, roles, Template.from_stack(stack)


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def _roles(exports: HostingTaskRoles) -> tuple[iam.Role, ...]:
    return (
        exports.api_role,
        exports.agent_role,
        exports.sync_role,
        exports.bootstrap_role,
    )


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
    if not policies:
        return []
    assert len(policies) == 1
    properties = policies[0]
    assert set(properties) == {"PolicyDocument", "PolicyName", "Roles"}
    document = properties["PolicyDocument"]
    assert set(document) == {"Version", "Statement"}
    assert document["Version"] == "2012-10-17"
    statements: list[dict[str, Any]] = document["Statement"]
    return statements


def _canonical_statement(statement: dict[str, Any]) -> str:
    normalized = dict(statement)
    for key in ("Action", "Resource"):
        value = normalized[key]
        values = value if isinstance(value, list) else [value]
        normalized[key] = sorted(json.dumps(item, sort_keys=True) for item in values)
    return json.dumps(normalized, sort_keys=True)


def test_exports_are_distinct_roles_with_exact_trust(roles_case: _Case) -> None:
    stack, _, exports, template = roles_case
    roles = _roles(exports)
    assert all(isinstance(role, iam.Role) for role in roles)
    ids = {_logical_id(role) for role in roles}
    assert len(ids) == 4
    resources = template.find_resources("AWS::IAM::Role")
    assert set(resources) == ids
    for resource in resources.values():
        assert resource["Properties"] == {"AssumeRolePolicyDocument": _trust(stack)}


def test_exact_runtime_permissions_for_all_roles(roles_case: _Case) -> None:
    stack, resources, exports, template = roles_case
    agent_queue = {"Fn::GetAtt": [_logical_id(resources.agent_queue), "Arn"]}
    sync_queue = {"Fn::GetAtt": [_logical_id(resources.sync_queue), "Arn"]}
    profile = stack.resolve(
        Fn.join(
            "",
            [
                "arn:",
                stack.partition,
                ":bedrock:us-east-1:",
                stack.account,
                ":inference-profile/us.amazon.nova-2-lite-v1:0",
            ],
        )
    )
    foundation_models = [
        stack.resolve(
            Fn.join(
                "",
                [
                    "arn:",
                    stack.partition,
                    f":bedrock:{region}::foundation-model/amazon.nova-2-lite-v1:0",
                ],
            )
        )
        for region in ("us-east-1", "us-east-2", "us-west-2")
    ]
    template.resource_count_is("AWS::IAM::Policy", 2)
    for role, queue in (
        (exports.agent_role, agent_queue),
        (exports.sync_role, sync_queue),
    ):
        expected: list[dict[str, Any]] = [
            {
                "Effect": "Allow",
                "Action": "sqs:SendMessage",
                "Resource": [agent_queue, sync_queue],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:ChangeMessageVisibility",
                ],
                "Resource": queue,
            },
        ]
        if role is exports.agent_role:
            expected.extend(
                [
                    {
                        "Sid": "InvokeSelectedNova2LiteProfile",
                        "Effect": "Allow",
                        "Action": "bedrock:InvokeModel",
                        "Resource": profile,
                    },
                    {
                        "Sid": "InvokeSelectedNova2LiteFoundationModels",
                        "Effect": "Allow",
                        "Action": "bedrock:InvokeModel",
                        "Resource": foundation_models,
                        "Condition": {
                            "StringEquals": {"bedrock:InferenceProfileArn": profile}
                        },
                    },
                ]
            )
        actual = _statements(template, role)
        assert len(actual) == len(expected)
        assert {_canonical_statement(item) for item in actual} == {
            _canonical_statement(item) for item in expected
        }
    assert _statements(template, exports.api_role) == []
    assert _statements(template, exports.bootstrap_role) == []
    policies = template.find_resources("AWS::IAM::Policy")
    assert {json.dumps(item["Properties"]["Roles"]) for item in policies.values()} == {
        json.dumps([{"Ref": _logical_id(exports.agent_role)}]),
        json.dumps([{"Ref": _logical_id(exports.sync_role)}]),
    }


def test_construct_adds_no_other_resources_or_outputs(roles_case: _Case) -> None:
    _, _, _, template = roles_case
    expected = {
        "AWS::IAM::Role": 4,
        "AWS::IAM::Policy": 2,
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
    assert not template.to_json().get("Outputs")


def test_trust_helper_has_no_runtime_permissions(tmp_path: Path) -> None:
    stack = Stack(
        App(outdir=str(tmp_path / "helper")),
        "Helper",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    role = new_task_role(stack, "TaskRole")
    assert isinstance(role, iam.Role)
    template = Template.from_stack(stack)
    assert template.find_resources("AWS::IAM::Role") == {
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


def test_synthesis_is_offline_with_synthetic_environment(
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
    stack = Stack(app, "Offline", env=Environment(account=_ACCOUNT, region=_REGION))
    resources = HostingResources(stack, "Resources")
    HostingTaskRoles(stack, "TaskRoles", resources=resources)
    assembly = app.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing")
    Template.from_stack(stack).resource_count_is("AWS::IAM::Role", 4)


def test_hosting_stack_keeps_task_roles_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    assert not any(isinstance(child, HostingTaskRoles) for child in stack.node.children)
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
