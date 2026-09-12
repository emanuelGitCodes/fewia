import json
import re
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, DefaultStackSynthesizer, Environment
from aws_cdk.assertions import Template

from deployment_app import deployment_environment
from deployment_stack import BedrockRuntimeDeploymentStack
from workload_app import main
from workload_stack import BedrockRuntimeStack

_ACCOUNT = "111122223333"
_OTHER_ACCOUNT = "999999999999"
_SYNTHETIC_ACCOUNTS = frozenset({_ACCOUNT, _OTHER_ACCOUNT})
_ACCOUNT_DIGITS = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")
_REGION = "us-east-1"
_ROLE_NAME = "fewia-bedrock-runtime-deployment"
_USER_ARN = f"arn:aws:iam::{_ACCOUNT}:user/fewia/fewia-bedrock-runtime"
_UNPATHED_USER_ARN = f"arn:aws:iam::{_ACCOUNT}:user/fewia-bedrock-runtime"
_EXECUTION_ROLE_ARN = f"arn:aws:iam::{_ACCOUNT}:role/{_ROLE_NAME}"
_LOOKUP_ACTIONS = {
    "iam:GetUser",
    "iam:GetUserPolicy",
}
_ALLOWED_ACTIONS = {
    "iam:CreateUser",
    "iam:DeleteUser",
    "iam:GetUser",
    "iam:UpdateUser",
    "iam:TagUser",
    "iam:UntagUser",
    "iam:ListUserTags",
    "iam:PutUserPolicy",
    "iam:GetUserPolicy",
    "iam:DeleteUserPolicy",
    "iam:ListUserPolicies",
    "iam:ListGroupsForUser",
    "iam:ListAttachedUserPolicies",
    "iam:GetLoginProfile",
}
_MUTATION_ACTIONS = _ALLOWED_ACTIONS - _LOOKUP_ACTIONS
_ROOT = Path(__file__).resolve().parent
_REQUIRED_TAGS = {
    "Project": "FEWIA",
    "Environment": "development",
    "Component": "bedrock-deployment",
    "ManagedBy": "AWS-CDK",
    "Model": "amazon.nova-2-lite-v1:0",
    "ReasoningEffort": "low",
    "CostCenter": "FEWIA",
}
_RUNTIME_TAGS = {
    "Project": "FEWIA",
    "Environment": "development",
    "Component": "bedrock-chat",
    "ManagedBy": "AWS-CDK",
    "Model": "amazon.nova-2-lite-v1:0",
    "ReasoningEffort": "low",
    "CostCenter": "FEWIA",
}
_FORBIDDEN_ACTIONS = {
    "*",
    "iam:*",
    "iam:CreateAccessKey",
    "iam:DeleteAccessKey",
    "iam:UpdateAccessKey",
    "iam:ListAccessKeys",
    "iam:CreateLoginProfile",
    "iam:UpdateLoginProfile",
    "iam:DeleteLoginProfile",
    "iam:AddUserToGroup",
    "iam:RemoveUserFromGroup",
    "iam:AttachUserPolicy",
    "iam:DetachUserPolicy",
    "iam:AttachGroupPolicy",
    "iam:CreateGroup",
    "iam:PutGroupPolicy",
    "iam:CreatePolicy",
    "iam:AttachRolePolicy",
    "iam:PutRolePolicy",
    "bedrock:*",
    "bedrock:InvokeModel",
    "s3:*",
    "s3:GetObject",
    "sts:*",
    "sts:AssumeRole",
    "sts:GetSessionToken",
}
_FORBIDDEN_FRAGMENTS = (
    "AmazonBedrockFullAccess",
    "AdministratorAccess",
    "CreateAccessKey",
    "CreateLoginProfile",
    "UpdateLoginProfile",
    "DeleteLoginProfile",
    "AddUserToGroup",
    "RemoveUserFromGroup",
    "AttachUserPolicy",
    "DetachUserPolicy",
    "AWS::IAM::User",
    "AWS::IAM::AccessKey",
    "AWS::IAM::Group",
    "foundation-model/*",
    "inference-profile/*",
)


def _stack(
    account: str = _ACCOUNT,
    region: str = _REGION,
) -> BedrockRuntimeDeploymentStack:
    app = App()
    return BedrockRuntimeDeploymentStack(
        app,
        "Test",
        env=Environment(account=account, region=region),
    )


def _statements_from(document: object) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    raw = document.get("Statement")
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return [value]


def _tag_mapping(raw: object) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    if not isinstance(raw, list):
        return {}
    mapping: dict[str, str] = {}
    for item in raw:
        if isinstance(item, dict) and "Key" in item and "Value" in item:
            mapping[str(item["Key"])] = str(item["Value"])
    return mapping


def _roles(template: Template) -> list[dict[str, Any]]:
    return [
        item
        for item in template.to_json()["Resources"].values()
        if item["Type"] == "AWS::IAM::Role"
    ]


def _role(template: Template) -> dict[str, Any]:
    roles = _roles(template)
    assert len(roles) == 1
    return roles[0]


def _role_tags(template: Template) -> dict[str, str]:
    return _tag_mapping(_role(template).get("Properties", {}).get("Tags", []))


def _users(template: Template) -> list[dict[str, Any]]:
    return [
        item
        for item in template.to_json()["Resources"].values()
        if item["Type"] == "AWS::IAM::User"
    ]


def _user(template: Template) -> dict[str, Any]:
    users = _users(template)
    assert len(users) == 1
    return users[0]


def _user_tags(template: Template) -> dict[str, str]:
    return _tag_mapping(_user(template).get("Properties", {}).get("Tags", []))


def _identity_statements(template: Template) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for resource in template.to_json()["Resources"].values():
        props = resource.get("Properties", {})
        rtype = resource["Type"]
        if rtype == "AWS::IAM::Role":
            for policy in props.get("Policies") or []:
                statements.extend(_statements_from(policy.get("PolicyDocument")))
        if rtype in {"AWS::IAM::Policy", "AWS::IAM::ManagedPolicy"}:
            statements.extend(_statements_from(props.get("PolicyDocument")))
    return statements


def _assume_statements(template: Template) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for resource in template.to_json()["Resources"].values():
        if resource["Type"] == "AWS::IAM::Role":
            props = resource.get("Properties", {})
            statements.extend(_statements_from(props.get("AssumeRolePolicyDocument")))
    return statements


def _resource_types(template: Template) -> set[str]:
    return {item["Type"] for item in template.to_json()["Resources"].values()}


def _user_identity_statements(template: Template) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for resource in template.to_json()["Resources"].values():
        props = resource.get("Properties", {})
        rtype = resource["Type"]
        if rtype == "AWS::IAM::User":
            for policy in props.get("Policies") or []:
                statements.extend(_statements_from(policy.get("PolicyDocument")))
        if rtype in {"AWS::IAM::Policy", "AWS::IAM::ManagedPolicy"}:
            statements.extend(_statements_from(props.get("PolicyDocument")))
    return statements


def _runtime_synthesizer() -> DefaultStackSynthesizer:
    return DefaultStackSynthesizer(
        deploy_role_arn="",
        cloud_formation_execution_role=_EXECUTION_ROLE_ARN,
    )


def test_role_name_trust_and_resource() -> None:
    template = Template.from_stack(_stack())
    props = _role(template).get("Properties", {})
    assert props.get("RoleName") == _ROLE_NAME
    statements = _assume_statements(template)
    assert len(statements) == 1
    assert _as_list(statements[0]["Action"]) == ["sts:AssumeRole"]
    assert _as_list(statements[0]["Principal"]["Service"]) == [
        "cloudformation.amazonaws.com"
    ]
    identity = _identity_statements(template)
    assert len(identity) == 2
    actions = set(_as_list(identity[0]["Action"]))
    assert len(_ALLOWED_ACTIONS) == 14
    assert actions == _ALLOWED_ACTIONS
    assert "iam:ListGroupsForUser" in actions
    assert "iam:ListAttachedUserPolicies" in actions
    assert "iam:GetLoginProfile" in actions
    assert _as_list(identity[0]["Resource"]) == [_USER_ARN]
    lookup = identity[1]
    assert lookup.get("Sid") == "ReadRuntimeUserBeforeCreation"
    lookup_actions = set(_as_list(lookup["Action"]))
    assert lookup_actions == _LOOKUP_ACTIONS
    assert _as_list(lookup["Resource"]) == [_UNPATHED_USER_ARN]
    assert lookup_actions.isdisjoint(_MUTATION_ACTIONS)
    assert "iam:CreateUser" not in lookup_actions
    assert "iam:UpdateUser" not in lookup_actions
    assert "iam:DeleteUser" not in lookup_actions


def test_role_removal_policy_is_retain() -> None:
    resource = _role(Template.from_stack(_stack()))
    assert resource.get("DeletionPolicy") == "Retain"
    assert resource.get("UpdateReplacePolicy") == "Retain"


def test_requires_all_seven_tags() -> None:
    tags = _role_tags(Template.from_stack(_stack()))
    assert tags == _REQUIRED_TAGS
    assert len(tags) == 7


def test_rejects_access_keys_users_and_data_permissions() -> None:
    template = Template.from_stack(_stack())
    types = _resource_types(template)
    iam_types = {item for item in types if item.startswith("AWS::IAM::")}
    assert iam_types == {"AWS::IAM::Role"}
    assert "AWS::IAM::AccessKey" not in types
    assert "AWS::IAM::User" not in types
    assert "AWS::IAM::Group" not in types
    assert "AWS::IAM::ManagedPolicy" not in types
    rendered = str(template.to_json())
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in rendered
    for statement in _identity_statements(template):
        assert "*" not in str(statement["Action"])
        assert "*" not in str(statement["Resource"])
        resources = _as_list(statement["Resource"])
        assert set(resources) <= {_USER_ARN, _UNPATHED_USER_ARN}
        actions = set(_as_list(statement["Action"]))
        if resources == [_UNPATHED_USER_ARN]:
            assert actions == _LOOKUP_ACTIONS
            assert actions.isdisjoint(_MUTATION_ACTIONS)
        for action in actions:
            assert action not in _FORBIDDEN_ACTIONS
            assert action in _ALLOWED_ACTIONS
            assert action not in {
                "iam:CreateLoginProfile",
                "iam:UpdateLoginProfile",
                "iam:DeleteLoginProfile",
                "iam:AddUserToGroup",
                "iam:RemoveUserFromGroup",
                "iam:AttachUserPolicy",
                "iam:DetachUserPolicy",
            }


def test_output_is_deployment_role_arn_only() -> None:
    outputs = Template.from_stack(_stack()).to_json().get("Outputs", {})
    assert set(outputs) == {"DeploymentRoleArn"}
    assert "Value" in outputs["DeploymentRoleArn"]
    rendered = str(outputs)
    assert "AccessKey" not in rendered
    assert "Secret" not in rendered
    assert "UserArn" not in rendered
    assert "UserName" not in rendered


def test_invalid_account_and_region_fail() -> None:
    with pytest.raises(ValueError, match="12-digit"):
        _stack(account="123")
    with pytest.raises(ValueError, match="12-digit"):
        _stack(account="12345678901a")
    with pytest.raises(ValueError, match="12-digit"):
        _stack(account="1234567890123")
    with pytest.raises(ValueError, match="us-east-1"):
        _stack(region="us-west-2")
    with pytest.raises(ValueError, match="us-east-1"):
        _stack(region="us-east-2")


def test_app_context_requires_exact_account_and_region() -> None:
    with pytest.raises(ValueError, match="12-digit"):
        deployment_environment(App(context={"account": "123", "region": _REGION}))
    with pytest.raises(ValueError, match="12-digit"):
        deployment_environment(App(context={"region": _REGION}))
    with pytest.raises(ValueError, match="12-digit"):
        deployment_environment(App(context={"account": "  ", "region": _REGION}))
    with pytest.raises(ValueError, match="us-east-1"):
        deployment_environment(
            App(context={"account": _ACCOUNT, "region": "us-west-2"})
        )
    with pytest.raises(ValueError, match="us-east-1"):
        deployment_environment(App(context={"account": _ACCOUNT}))
    env = deployment_environment(
        App(context={"account": f" {_ACCOUNT} ", "region": " us-east-1 "})
    )
    assert env.account == _ACCOUNT
    assert env.region == _REGION


def test_deployment_app_does_not_instantiate_runtime_user() -> None:
    text = (_ROOT / "deployment_app.py").read_text(encoding="utf-8")
    assert "BedrockRuntimeStack" not in text
    assert "FewiaBedrockRuntimeDeployment" in text
    assert "from workload_stack" not in text
    assert "DefaultStackSynthesizer" not in text
    assert "--role-arn" not in text


def test_user_stack_permissions_unchanged_with_custom_synthesizer() -> None:
    default_stack = BedrockRuntimeStack(
        App(),
        "Default",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    custom_stack = BedrockRuntimeStack(
        App(),
        "Custom",
        env=Environment(account=_ACCOUNT, region=_REGION),
        synthesizer=_runtime_synthesizer(),
    )
    default_template = Template.from_stack(default_stack)
    custom_template = Template.from_stack(custom_stack)
    assert _user_identity_statements(custom_template) == _user_identity_statements(
        default_template
    )
    default_types = _resource_types(default_template)
    custom_types = _resource_types(custom_template)
    default_iam = {item for item in default_types if item.startswith("AWS::IAM::")}
    custom_iam = {item for item in custom_types if item.startswith("AWS::IAM::")}
    assert default_iam == {"AWS::IAM::User"}
    assert custom_iam == {"AWS::IAM::User"}
    for statement in _user_identity_statements(custom_template):
        for action in _as_list(statement["Action"]):
            assert action == "bedrock:InvokeModel"


def test_assembly_manifest_uses_dedicated_execution_role(tmp_path: Path) -> None:
    app = App(
        outdir=str(tmp_path),
        context={"account": _ACCOUNT, "region": _REGION},
    )
    BedrockRuntimeStack(
        app,
        "FewiaBedrockRuntime",
        env=Environment(account=_ACCOUNT, region=_REGION),
        synthesizer=_runtime_synthesizer(),
    )
    app.synth()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    stacks = [
        item["properties"]
        for item in manifest["artifacts"].values()
        if item.get("type") == "aws:cloudformation:stack"
    ]
    assert len(stacks) == 1
    props = stacks[0]
    assert props["cloudFormationExecutionRoleArn"] == _EXECUTION_ROLE_ARN
    assume = props.get("assumeRoleArn")
    assert assume in (None, "")


def test_workload_app_main_omits_bootstrap_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def configured_app() -> App:
        return App(
            outdir=str(tmp_path),
            context={"account": _ACCOUNT, "region": _REGION},
        )

    monkeypatch.setattr("workload_app.App", configured_app)
    main()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    stacks = [
        item["properties"]
        for item in manifest["artifacts"].values()
        if item.get("type") == "aws:cloudformation:stack"
    ]
    assert len(stacks) == 1
    template = json.loads(
        (tmp_path / stacks[0]["templateFile"]).read_text(encoding="utf-8")
    )
    parameters = template.get("Parameters") or {}
    assert "BootstrapVersion" not in parameters
    for param in parameters.values():
        assert not str(param.get("Type", "")).startswith("AWS::SSM::Parameter::Value")
    rules = template.get("Rules") or {}
    assert "CheckBootstrapVersion" not in rules
    rendered = json.dumps(template)
    assert "BootstrapVersion" not in rendered
    assert "{{resolve:ssm" not in rendered


def test_assembly_records_seven_stack_and_role_tags(tmp_path: Path) -> None:
    app = App(
        outdir=str(tmp_path),
        context={"account": _ACCOUNT, "region": _REGION},
    )
    stack = BedrockRuntimeDeploymentStack(
        app,
        "FewiaBedrockRuntimeDeployment",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    assembly = app.synth()
    recorded = dict(assembly.get_stack_by_name("FewiaBedrockRuntimeDeployment").tags)
    assert recorded == _REQUIRED_TAGS
    assert len(recorded) == 7
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    file_tags = _tag_mapping(
        manifest["artifacts"]["FewiaBedrockRuntimeDeployment"]["properties"]["tags"]
    )
    assert file_tags == _REQUIRED_TAGS
    role_tags = _role_tags(Template.from_stack(stack))
    assert role_tags == _REQUIRED_TAGS
    assert len(role_tags) == 7


def test_assembly_records_seven_stack_and_user_tags(tmp_path: Path) -> None:
    app = App(
        outdir=str(tmp_path),
        context={"account": _ACCOUNT, "region": _REGION},
    )
    stack = BedrockRuntimeStack(
        app,
        "FewiaBedrockRuntime",
        env=Environment(account=_ACCOUNT, region=_REGION),
    )
    assembly = app.synth()
    recorded = dict(assembly.get_stack_by_name("FewiaBedrockRuntime").tags)
    assert recorded == _RUNTIME_TAGS
    assert len(recorded) == 7
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    file_tags = _tag_mapping(
        manifest["artifacts"]["FewiaBedrockRuntime"]["properties"]["tags"]
    )
    assert file_tags == _RUNTIME_TAGS
    user_tags = _user_tags(Template.from_stack(stack))
    assert user_tags == _RUNTIME_TAGS
    assert len(user_tags) == 7


def test_source_uses_synthetic_account_only() -> None:
    names = (
        "deployment_app.py",
        "deployment_stack.py",
        "test_deployment_stack.py",
        "workload_app.py",
        "workload_stack.py",
    )
    for name in names:
        text = (_ROOT / name).read_text(encoding="utf-8")
        found = frozenset(_ACCOUNT_DIGITS.findall(text))
        assert found <= _SYNTHETIC_ACCOUNTS
        assert "AccessKey" not in text or name == "test_deployment_stack.py"
    stack = (_ROOT / "deployment_stack.py").read_text(encoding="utf-8")
    assert _ROLE_NAME in stack
    assert "cloudformation.amazonaws.com" in stack
    assert "RemovalPolicy.RETAIN" in stack
    assert '"Component": "bedrock-deployment"' in stack
    assert "inline_policies" in stack
    assert "iam:CreateAccessKey" not in stack
    assert "iam:*" not in stack
    assert "iam:ListGroupsForUser" in stack
    assert "iam:ListAttachedUserPolicies" in stack
    assert "iam:GetLoginProfile" in stack
    assert "iam:CreateLoginProfile" not in stack
    assert "iam:UpdateLoginProfile" not in stack
    assert "iam:DeleteLoginProfile" not in stack
    assert "iam:AddUserToGroup" not in stack
    assert "iam:RemoveUserFromGroup" not in stack
    assert "iam:AttachUserPolicy" not in stack
    assert "iam:DetachUserPolicy" not in stack
    assert "ReadRuntimeUserBeforeCreation" in stack
    assert ":user/fewia/fewia-bedrock-runtime" in stack
    assert ":user/fewia-bedrock-runtime" in stack
    app = (_ROOT / "workload_app.py").read_text(encoding="utf-8")
    assert "DefaultStackSynthesizer" in app
    assert 'deploy_role_arn=""' in app
    assert "cloud_formation_execution_role" in app
    assert "FewiaBedrockRuntime" in app
    assert "--role-arn" not in app
