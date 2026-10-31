import copy
import re
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stack import BedrockChatStack, guardrail_topics, policy_digest

_ACCOUNT = "111122223333"
_OTHER_ACCOUNT = "999999999999"
_SYNTHETIC_ACCOUNTS = frozenset({_ACCOUNT, _OTHER_ACCOUNT})
_ACCOUNT_DIGITS = re.compile(r"(?<![0-9])[0-9]{12}(?![0-9])")
_REGION = "us-east-1"
_TRUST = f"arn:aws:iam::{_ACCOUNT}:user/dev-caller"
_PROFILE = (
    f"arn:aws:bedrock:us-east-1:{_ACCOUNT}:inference-profile/us.amazon.nova-2-lite-v1:0"
)
_MODELS = {
    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-lite-v1:0",
    "arn:aws:bedrock:us-east-2::foundation-model/amazon.nova-2-lite-v1:0",
    "arn:aws:bedrock:us-west-2::foundation-model/amazon.nova-2-lite-v1:0",
}
_GUARDRAIL_SID = "ApplyFewiaGuardrail"
_BLOCKED = (
    "I can help with meals, grocery lists, nutrition facts, and your food budget. "
    "I cannot help with that request."
)
_TOPIC_FLAGS = {
    "MedicalAdvice": (False, True),
    "AllergySafety": (True, True),
    "FinancialTransactions": (True, True),
    "NonFoodTasks": (True, True),
}
_FILTER_STRENGTHS = {
    "HATE": ("MEDIUM", "MEDIUM"),
    "INSULTS": ("MEDIUM", "MEDIUM"),
    "SEXUAL": ("MEDIUM", "MEDIUM"),
    "VIOLENCE": ("MEDIUM", "MEDIUM"),
    "MISCONDUCT": ("MEDIUM", "MEDIUM"),
    "PROMPT_ATTACK": ("HIGH", "NONE"),
}
_ROOT = Path(__file__).resolve().parent
_REQUIRED_TAGS = {
    "Project": "FEWIA",
    "Environment": "development",
    "ManagedBy": "AWS-CDK",
    "Component": "bedrock-chat",
    "Model": "amazon.nova-2-lite-v1:0",
    "ReasoningEffort": "low",
}
_FORBIDDEN_ACTIONS = {
    "*",
    "bedrock:*",
    "bedrock:InvokeModel*",
    "bedrock:InvokeModelWithResponseStream",
    "bedrock:CreateInferenceProfile",
    "iam:*",
    "sts:*",
}
_FORBIDDEN_FRAGMENTS = (
    "AmazonBedrockFullAccess",
    "AdministratorAccess",
    "global.openai",
    "in.openai",
    "openai.gpt-6-luna",
    "us.openai.gpt-6-luna",
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
    omit: frozenset[str] | None = None,
) -> BedrockChatStack:
    values: dict[str, object] = {"trustPrincipalArn": _TRUST}
    if context is not None:
        values.update(context)
    if omit is not None:
        for key in omit:
            values.pop(key, None)
    app = App(context=values)
    return BedrockChatStack(
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
        if rtype == "AWS::IAM::Role":
            for policy in props.get("Policies") or []:
                statements.extend(_statements_from(policy.get("PolicyDocument")))
        if rtype in {"AWS::IAM::Policy", "AWS::IAM::ManagedPolicy"}:
            statements.extend(_statements_from(props.get("PolicyDocument")))
    return statements


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return [value]


def _assume_statements(template: Template) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for resource in template.to_json()["Resources"].values():
        if resource["Type"] == "AWS::IAM::Role":
            props = resource.get("Properties", {})
            document = props.get("AssumeRolePolicyDocument")
            statements.extend(_statements_from(document))
    return statements


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


def _role_tags(template: Template) -> dict[str, str]:
    for resource in template.to_json()["Resources"].values():
        if resource["Type"] == "AWS::IAM::Role":
            return _tag_mapping(resource.get("Properties", {}).get("Tags", []))
    raise AssertionError("template MUST include one IAM role")


def _invoke_statements(statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in statements if item.get("Sid") != _GUARDRAIL_SID]


def _guardrail_props(template: Template) -> dict[str, Any]:
    found = template.find_resources("AWS::Bedrock::Guardrail")
    assert len(found) == 1
    return dict(next(iter(found.values()))["Properties"])


def _split_identity(
    statements: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    statements = _invoke_statements(statements)
    assert len(statements) == 2
    with_condition = [item for item in statements if "Condition" in item]
    without_condition = [item for item in statements if "Condition" not in item]
    assert len(with_condition) == 1
    assert len(without_condition) == 1
    return without_condition[0], with_condition[0]


def test_trusts_exact_same_account_principal() -> None:
    template = Template.from_stack(_stack())
    template.has_resource_properties(
        "AWS::IAM::Role",
        {
            "MaxSessionDuration": 3600,
            "AssumeRolePolicyDocument": {
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "sts:AssumeRole",
                        "Principal": {"AWS": _TRUST},
                        "Condition": {
                            "Bool": {"aws:MultiFactorAuthPresent": "true"},
                        },
                    }
                ]
            },
        },
    )


def test_trust_requires_mfa() -> None:
    statements = _assume_statements(Template.from_stack(_stack()))
    assert len(statements) == 1
    present = statements[0]["Condition"]["Bool"]["aws:MultiFactorAuthPresent"]
    assert present in {True, "true"}


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
            assert action in {"bedrock:InvokeModel", "bedrock:ApplyGuardrail"}


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


def test_rejects_extra_permissions_and_managed_policies() -> None:
    template = Template.from_stack(_stack())
    resources = template.to_json()["Resources"]
    types = {item["Type"] for item in resources.values()}
    assert "AWS::IAM::ManagedPolicy" not in types
    assert "AWS::IAM::AccessKey" not in types
    assert "AWS::IAM::User" not in types
    rendered = str(template.to_json())
    assert "AmazonBedrockFullAccess" not in rendered
    assert len(_identity_statements(template)) == 3
    assert len(_assume_statements(template)) == 1


def test_requires_project_tags() -> None:
    template = Template.from_stack(_stack())
    assert _role_tags(template) == _REQUIRED_TAGS


def test_role_model_and_reasoning_effort_tags_are_exact() -> None:
    tags = _role_tags(Template.from_stack(_stack()))
    assert tags["Model"] == "amazon.nova-2-lite-v1:0"
    assert tags["ReasoningEffort"] == "low"
    assert _REQUIRED_TAGS["Model"] == "amazon.nova-2-lite-v1:0"
    assert _REQUIRED_TAGS["ReasoningEffort"] == "low"


def test_outputs_are_role_arn_and_guardrail_only() -> None:
    outputs = Template.from_stack(_stack()).to_json().get("Outputs", {})
    assert set(outputs) == {"RoleArn", "GuardrailId", "GuardrailVersion"}
    for output in outputs.values():
        assert "Value" in output
    assert "AccessKey" not in str(outputs)
    assert "Secret" not in str(outputs)


def test_guardrail_topics_and_flags() -> None:
    props = _guardrail_props(Template.from_stack(_stack()))
    topics = props["TopicPolicyConfig"]["TopicsConfig"]
    assert {item["Name"] for item in topics} == set(_TOPIC_FLAGS)
    assert len(topics) == len(_TOPIC_FLAGS)
    for item in topics:
        assert item["Type"] == "DENY"
        assert len(item["Definition"]) < 200
        assert 1 <= len(item["Examples"]) <= 5
        flags = (item["InputEnabled"], item["OutputEnabled"])
        assert flags == _TOPIC_FLAGS[item["Name"]]


def test_guardrail_content_filters() -> None:
    props = _guardrail_props(Template.from_stack(_stack()))
    filters = props["ContentPolicyConfig"]["FiltersConfig"]
    found = {
        item["Type"]: (item["InputStrength"], item["OutputStrength"])
        for item in filters
    }
    assert len(filters) == len(_FILTER_STRENGTHS)
    assert found == _FILTER_STRENGTHS


def test_guardrail_blocked_messages() -> None:
    props = _guardrail_props(Template.from_stack(_stack()))
    assert props["BlockedInputMessaging"] == _BLOCKED
    assert props["BlockedOutputsMessaging"] == _BLOCKED


def test_one_guardrail_version_of_the_guardrail() -> None:
    template = Template.from_stack(_stack())
    template.resource_count_is("AWS::Bedrock::Guardrail", 1)
    template.resource_count_is("AWS::Bedrock::GuardrailVersion", 1)
    guardrail_id = next(iter(template.find_resources("AWS::Bedrock::Guardrail")))
    versions = template.find_resources("AWS::Bedrock::GuardrailVersion")
    props = next(iter(versions.values()))["Properties"]
    assert props["GuardrailIdentifier"] == {"Fn::GetAtt": [guardrail_id, "GuardrailId"]}


def test_guardrail_version_description_carries_policy_digest() -> None:
    template = Template.from_stack(_stack())
    versions = template.find_resources("AWS::Bedrock::GuardrailVersion")
    assert len(versions) == 1
    props = next(iter(versions.values()))["Properties"]
    assert props["Description"] == f"policy {policy_digest()}"


def test_policy_digest_changes_with_topic_definition() -> None:
    digest = policy_digest()
    assert re.fullmatch(r"[0-9a-f]{12}", digest)
    changed = copy.deepcopy(guardrail_topics())
    changed[0]["definition"] = f"{changed[0]['definition']} Changed."
    other = policy_digest(topics=changed)
    assert re.fullmatch(r"[0-9a-f]{12}", other)
    assert other != digest
    assert policy_digest() == digest


def test_policy_digest_changes_with_topic_input_enabled() -> None:
    digest = policy_digest()
    changed = copy.deepcopy(guardrail_topics())
    medical = next(item for item in changed if item["name"] == "MedicalAdvice")
    assert medical["input_enabled"] is False
    medical["input_enabled"] = True
    assert policy_digest(topics=changed) != digest
    assert policy_digest() == digest


def test_apply_guardrail_is_scoped_to_the_guardrail() -> None:
    template = Template.from_stack(_stack())
    guardrail_id = next(iter(template.find_resources("AWS::Bedrock::Guardrail")))
    applied = [
        item
        for item in _identity_statements(template)
        if item.get("Sid") == _GUARDRAIL_SID
    ]
    assert len(applied) == 1
    assert applied[0]["Effect"] == "Allow"
    assert _as_list(applied[0]["Action"]) == ["bedrock:ApplyGuardrail"]
    assert "Condition" not in applied[0]
    assert applied[0]["Resource"] == {"Fn::GetAtt": [guardrail_id, "GuardrailArn"]}


def test_guardrail_outputs_reference_guardrail_and_version() -> None:
    template = Template.from_stack(_stack())
    guardrail_id = next(iter(template.find_resources("AWS::Bedrock::Guardrail")))
    version_id = next(iter(template.find_resources("AWS::Bedrock::GuardrailVersion")))
    outputs = template.to_json()["Outputs"]
    assert outputs["GuardrailId"]["Value"] == {
        "Fn::GetAtt": [guardrail_id, "GuardrailId"]
    }
    assert outputs["GuardrailVersion"]["Value"] == {
        "Fn::GetAtt": [version_id, "Version"]
    }


def test_missing_trust_config_fails_closed() -> None:
    with pytest.raises(ValueError, match="trustPrincipalArn"):
        _stack(omit=frozenset({"trustPrincipalArn"}))
    with pytest.raises(ValueError, match="trustPrincipalArn"):
        _stack({"trustPrincipalArn": ""})


def test_extra_model_context_does_not_expand_policy() -> None:
    statements = _identity_statements(
        Template.from_stack(
            _stack(
                {
                    "allowedModelArns": [
                        "arn:aws:bedrock:us-east-1::foundation-model/other",
                    ],
                    "allowedRegions": ["us-west-2"],
                }
            )
        )
    )
    profile_stmt, model_stmt = _split_identity(statements)
    assert set(_as_list(profile_stmt["Resource"])) == {_PROFILE}
    assert set(_as_list(model_stmt["Resource"])) == _MODELS


def test_wide_trust_fails() -> None:
    with pytest.raises(ValueError, match="trustPrincipalArn"):
        _stack({"trustPrincipalArn": f"arn:aws:iam::{_ACCOUNT}:root"})
    with pytest.raises(ValueError, match="trustPrincipalArn"):
        _stack(
            {
                "trustPrincipalArn": f"arn:aws:iam::{_OTHER_ACCOUNT}:user/dev-caller",
            }
        )


def test_unsupported_trust_principals_fail() -> None:
    unsupported = [
        f"arn:aws:iam::{_ACCOUNT}:role/dev-caller",
        f"arn:aws:iam::{_ACCOUNT}:user/*",
        f"arn:aws:sts::{_ACCOUNT}:assumed-role/dev-caller/session",
        f"arn:aws:iam::{_ACCOUNT}:federated-user/dev-caller",
        f"arn:aws:iam::{_ACCOUNT}:saml-provider/Example",
        f"arn:aws:iam::{_ACCOUNT}:oidc-provider/example.com",
    ]
    for arn in unsupported:
        with pytest.raises(ValueError, match="trustPrincipalArn"):
            _stack({"trustPrincipalArn": arn})


def test_non_origin_stack_region_fails() -> None:
    with pytest.raises(ValueError, match="us-east-1"):
        _stack(region="us-west-2")
    with pytest.raises(ValueError, match="us-east-1"):
        _stack(region="us-east-2")


def test_source_uses_synthetic_account_only() -> None:
    for name in ("app.py", "stack.py", "test_stack.py"):
        text = (_ROOT / name).read_text(encoding="utf-8")
        found = frozenset(_ACCOUNT_DIGITS.findall(text))
        assert found <= _SYNTHETIC_ACCOUNTS
    stack = (_ROOT / "stack.py").read_text(encoding="utf-8")
    assert "us.amazon.nova-2-lite-v1:0" in stack
    assert "amazon.nova-2-lite-v1:0" in stack
    assert '"Model": "amazon.nova-2-lite-v1:0"' in stack
    assert '"ReasoningEffort": "low"' in stack
    assert "openai.gpt-6-luna" not in stack
    assert "project/default" not in stack
    assert "global.openai" not in stack
    assert _ACCOUNT == "111122223333"
