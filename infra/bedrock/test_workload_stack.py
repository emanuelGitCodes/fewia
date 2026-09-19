import re
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stack import BedrockChatStack
from workload_app import runtime_environment
from workload_stack import BedrockRuntimeStack

_ACCOUNT = "111122223333"
_OTHER_ACCOUNT = "999999999999"
_SYNTHETIC_ACCOUNTS = frozenset({_ACCOUNT, _OTHER_ACCOUNT})
_ACCOUNT_DIGITS = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")
_REGION = "us-east-1"
_TRUST = f"arn:aws:iam::{_ACCOUNT}:user/dev-caller"
_USER_NAME = "fewia-bedrock-runtime"
_USER_PATH = "/fewia/"
_PROFILE = (
    f"arn:aws:bedrock:us-east-1:{_ACCOUNT}:inference-profile/us.amazon.nova-2-lite-v1:0"
)
_MODELS = {
    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-lite-v1:0",
    "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-2-lite-v1:0",
    "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-2-lite-v1:0",
}
_ROOT = Path(__file__).resolve().parent
_REQUIRED_TAGS = {
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
    "bedrock:*",
    "bedrock:InvokeModel*",
    "bedrock:InvokeModelWithResponseStream",
    "bedrock:CreateInferenceProfile",
    "iam:*",
    "iam:CreateAccessKey",
    "iam:CreateUser",
    "sts:*",
    "sts:AssumeRole",
    "s3:*",
    "s3:GetObject",
    "ce:*",
    "aws-portal:*",
    "budgets:*",
    "organizations:*",
}
_FORBIDDEN_FRAGMENTS = (
    "AmazonBedrockFullAccess",
    "AdministratorAccess",
    "global.openai",
    "in.openai",
    "openai.gpt-5.6-luna",
    "us.openai.gpt-5.6-luna",
    "application-inference-profile",
    "foundation-model/*",
    "inference-profile/*",
    "project/*",
    "project/default",
)


def _stack(
    context: dict[str, object] | None = None,
    account: str = _ACCOUNT,
    region: str = _REGION,
) -> BedrockRuntimeStack:
    values: dict[str, object] = {}
    if context is not None:
        values.update(context)
    app = App(context=values)
    return BedrockRuntimeStack(
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


def _identity_statements(template: Template) -> list[dict[str, Any]]:
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


def _split_identity(
    statements: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    assert len(statements) == 2
    with_condition = [item for item in statements if "Condition" in item]
    without_condition = [item for item in statements if "Condition" not in item]
    assert len(with_condition) == 1
    assert len(without_condition) == 1
    return without_condition[0], with_condition[0]


def _resource_types(template: Template) -> set[str]:
    return {item["Type"] for item in template.to_json()["Resources"].values()}


def test_user_is_named_path_user_without_password() -> None:
    template = Template.from_stack(_stack())
    resource = _user(template)
    props = resource.get("Properties", {})
    assert props.get("UserName") == _USER_NAME
    assert props.get("Path") == _USER_PATH
    assert "LoginProfile" not in props
    assert "Password" not in props
    assert not props.get("Groups")
    assert not props.get("ManagedPolicyArns")


def test_user_removal_policy_is_retain() -> None:
    resource = _user(Template.from_stack(_stack()))
    assert resource.get("DeletionPolicy") == "Retain"
    assert resource.get("UpdateReplacePolicy") == "Retain"


def test_requires_all_seven_tags() -> None:
    tags = _user_tags(Template.from_stack(_stack()))
    assert tags == _REQUIRED_TAGS
    assert len(tags) == 7


def test_policy_inventory_is_selected_nova_2_lite_us_path() -> None:
    template = Template.from_stack(_stack())
    statements = _identity_statements(template)
    profile_stmt, model_stmt = _split_identity(statements)
    assert _as_list(profile_stmt["Action"]) == ["bedrock:InvokeModel"]
    assert set(_as_list(profile_stmt["Resource"])) == {_PROFILE}
    assert _as_list(model_stmt["Action"]) == ["bedrock:InvokeModel"]
    assert set(_as_list(model_stmt["Resource"])) == _MODELS
    condition = model_stmt["Condition"]["StringEquals"]
    assert _as_list(condition["bedrock:InferenceProfileArn"]) == [_PROFILE]
    assert profile_stmt.get("Sid") == "InvokeSelectedNova2LiteProfile"
    assert model_stmt.get("Sid") == "InvokeSelectedNova2LiteFoundationModels"
    rendered = str(template.to_json())
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in rendered
    for statement in statements:
        assert "*" not in str(statement["Action"])
        assert "*" not in str(statement["Resource"])
        for action in _as_list(statement["Action"]):
            assert action not in _FORBIDDEN_ACTIONS
            assert action == "bedrock:InvokeModel"


def test_origin_and_destination_regions() -> None:
    profile_stmt, model_stmt = _split_identity(
        _identity_statements(Template.from_stack(_stack()))
    )
    profile_regions = {
        str(arn).split(":")[3] for arn in _as_list(profile_stmt["Resource"])
    }
    model_regions = {str(arn).split(":")[3] for arn in _as_list(model_stmt["Resource"])}
    assert profile_regions == {"us-east-1"}
    assert model_regions == {"us-east-1", "us-east-2", "us-west-2"}


def test_rejects_extra_permissions_and_secret_resources() -> None:
    template = Template.from_stack(_stack())
    types = _resource_types(template)
    iam_types = {item for item in types if item.startswith("AWS::IAM::")}
    assert iam_types == {"AWS::IAM::User"}
    assert "AWS::IAM::AccessKey" not in types
    assert "AWS::IAM::Role" not in types
    assert "AWS::IAM::ManagedPolicy" not in types
    assert "AWS::IAM::Policy" not in types
    assert "AWS::IAM::Group" not in types
    rendered = str(template.to_json()).lower()
    assert "plaid" not in rendered
    assert "aws-portal" not in rendered
    assert len(_identity_statements(template)) == 2


def test_outputs_are_user_arn_and_name_only() -> None:
    outputs = Template.from_stack(_stack()).to_json().get("Outputs", {})
    assert set(outputs) == {"UserArn", "UserName"}
    assert "Value" in outputs["UserArn"]
    assert "Value" in outputs["UserName"]
    rendered = str(outputs)
    assert "AccessKey" not in rendered
    assert "Secret" not in rendered
    assert "Password" not in rendered


def test_extra_model_context_does_not_expand_policy() -> None:
    statements = _identity_statements(
        Template.from_stack(
            _stack(
                {
                    "allowedModelArns": [
                        "arn:aws:bedrock:us-east-1::foundation-model/other",
                    ],
                    "allowedRegions": ["us-west-2"],
                    "trustPrincipalArn": _TRUST,
                }
            )
        )
    )
    profile_stmt, model_stmt = _split_identity(statements)
    assert set(_as_list(profile_stmt["Resource"])) == {_PROFILE}
    assert set(_as_list(model_stmt["Resource"])) == _MODELS


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
        runtime_environment(App(context={"account": "123", "region": _REGION}))
    with pytest.raises(ValueError, match="12-digit"):
        runtime_environment(App(context={"region": _REGION}))
    with pytest.raises(ValueError, match="12-digit"):
        runtime_environment(App(context={"account": "  ", "region": _REGION}))
    with pytest.raises(ValueError, match="us-east-1"):
        runtime_environment(App(context={"account": _ACCOUNT, "region": "us-west-2"}))
    with pytest.raises(ValueError, match="us-east-1"):
        runtime_environment(App(context={"account": _ACCOUNT}))
    env = runtime_environment(
        App(context={"account": f" {_ACCOUNT} ", "region": " us-east-1 "})
    )
    assert env.account == _ACCOUNT
    assert env.region == _REGION


def test_runtime_app_does_not_instantiate_dev_stack() -> None:
    text = (_ROOT / "workload_app.py").read_text(encoding="utf-8")
    assert "BedrockChatStack" not in text
    assert "FewiaBedrockDev" not in text
    assert "FewiaBedrockRuntime" in text
    assert "from stack import" not in text


def test_coexistence_does_not_alter_existing_stack() -> None:
    app = App(context={"trustPrincipalArn": _TRUST})
    env = Environment(account=_ACCOUNT, region=_REGION)
    existing = BedrockChatStack(app, "FewiaBedrockDev", env=env)
    runtime = BedrockRuntimeStack(app, "FewiaBedrockRuntime", env=env)
    existing_template = Template.from_stack(existing)
    runtime_template = Template.from_stack(runtime)
    existing_types = _resource_types(existing_template)
    runtime_types = _resource_types(runtime_template)
    assert "AWS::IAM::Role" in existing_types
    assert "AWS::IAM::User" not in existing_types
    assert "AWS::IAM::AccessKey" not in existing_types
    runtime_iam = {item for item in runtime_types if item.startswith("AWS::IAM::")}
    assert runtime_iam == {"AWS::IAM::User"}
    existing_outputs = existing_template.to_json().get("Outputs", {})
    assert set(existing_outputs) == {"RoleArn"}
    existing_role_tags: dict[str, str] = {}
    for resource in existing_template.to_json()["Resources"].values():
        if resource["Type"] == "AWS::IAM::Role":
            existing_role_tags = _tag_mapping(
                resource.get("Properties", {}).get("Tags", [])
            )
    assert "CostCenter" not in existing_role_tags
    assert _user_tags(runtime_template)["CostCenter"] == "FEWIA"


def test_source_uses_synthetic_account_only() -> None:
    names = (
        "workload_app.py",
        "workload_stack.py",
        "test_workload_stack.py",
    )
    for name in names:
        text = (_ROOT / name).read_text(encoding="utf-8")
        found = frozenset(_ACCOUNT_DIGITS.findall(text))
        assert found <= _SYNTHETIC_ACCOUNTS
    stack = (_ROOT / "workload_stack.py").read_text(encoding="utf-8")
    assert "us.amazon.nova-2-lite-v1:0" in stack
    assert "amazon.nova-2-lite-v1:0" in stack
    assert '"Model": "amazon.nova-2-lite-v1:0"' in stack
    assert '"ReasoningEffort": "low"' in stack
    assert '"CostCenter": "FEWIA"' in stack
    assert "fewia-bedrock-runtime" in stack
    assert '"/fewia/"' in stack
    assert "RemovalPolicy.RETAIN" in stack
    assert "openai.gpt-5.6-luna" not in stack
    assert "project/default" not in stack
    assert "AccessKey" not in stack
    assert _ACCOUNT == "111122223333"
