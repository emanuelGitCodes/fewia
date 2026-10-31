"""Development IAM role for nonstreaming Bedrock Converse."""

import re

from aws_cdk import CfnOutput, Duration, Environment, Stack, Tags
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from constructs import Construct

_ORIGIN_REGION = "us-east-1"
_PROFILE_ID = "us.amazon.nova-2-lite-v1:0"
_MODEL_ID = "amazon.nova-2-lite-v1:0"
_MODEL_REGIONS = ("us-east-1", "us-east-2", "us-west-2")
_MODEL_ARNS = tuple(
    f"arn:aws:bedrock:{region}::foundation-model/{_MODEL_ID}"
    for region in _MODEL_REGIONS
)
_ACCOUNT = re.compile(r"^[0-9]{12}$")
_PRINCIPAL = re.compile(r"^arn:aws:iam::([0-9]{12}):user/[A-Za-z0-9+=,.@_/-]+$")
_MFA_CONDITION = {"Bool": {"aws:MultiFactorAuthPresent": "true"}}
_TAGS = {
    "Project": "FEWIA",
    "Environment": "development",
    "ManagedBy": "AWS-CDK",
    "Component": "bedrock-chat",
    "Model": "amazon.nova-2-lite-v1:0",
    "ReasoningEffort": "low",
}
_BLOCKED = (
    "I can help with meals, grocery lists, nutrition facts, and your food budget. "
    "I cannot help with that request."
)
# name -> (definition, examples). MedicalAdvice checks output only.
_TOPICS = {
    "MedicalAdvice": (
        "Advice that a food, meal, or plan suits, treats, or is safe for a "
        "health condition.",
        ["This meal plan will help control your blood sugar."],
    ),
    "AllergySafety": (
        "Assurance that a food is free of an allergen or safe for an allergy "
        "or celiac disease.",
        ["Is this bread safe for my peanut allergy?"],
    ),
    "FinancialTransactions": (
        "Buying, paying, transferring money, or placing an order.",
        ["Pay for my cart now.", "Place the order."],
    ),
    "NonFoodTasks": (
        "Tasks unrelated to meals, groceries, nutrition, or a food budget.",
        ["Write me a cover letter.", "Fix this Python bug."],
    ),
}
# filter -> (input strength, output strength)
_STANDARD = ("HATE", "INSULTS", "SEXUAL", "VIOLENCE", "MISCONDUCT")
_FILTERS = {kind: ("MEDIUM", "MEDIUM") for kind in _STANDARD} | {
    "PROMPT_ATTACK": ("HIGH", "NONE")
}


class BedrockChatStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env: Environment,
    ) -> None:
        super().__init__(scope, construct_id, env=env)
        if not _ACCOUNT.fullmatch(self.account):
            raise ValueError("stack account MUST be a 12-digit AWS account id")
        if self.region != _ORIGIN_REGION:
            raise ValueError("stack region MUST be us-east-1")
        trust = _context_str(self, "trustPrincipalArn")
        match = _PRINCIPAL.fullmatch(trust)
        if match is None or match.group(1) != self.account:
            raise ValueError("trustPrincipalArn MUST be a same-account IAM user ARN")
        profile = (
            f"arn:aws:bedrock:{_ORIGIN_REGION}:{self.account}"
            f":inference-profile/{_PROFILE_ID}"
        )
        guardrail = bedrock.CfnGuardrail(
            self,
            "Guardrail",
            name="fewia-food-assistant",
            description="Denies medical, allergy, payment, and non-food requests",
            blocked_input_messaging=_BLOCKED,
            blocked_outputs_messaging=_BLOCKED,
            topic_policy_config=bedrock.CfnGuardrail.TopicPolicyConfigProperty(
                topics_config=[
                    bedrock.CfnGuardrail.TopicConfigProperty(
                        name=name,
                        definition=definition,
                        examples=examples,
                        type="DENY",
                        input_enabled=name != "MedicalAdvice",
                        output_enabled=True,
                    )
                    for name, (definition, examples) in _TOPICS.items()
                ]
            ),
            content_policy_config=bedrock.CfnGuardrail.ContentPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContentFilterConfigProperty(
                        type=kind, input_strength=inp, output_strength=out
                    )
                    for kind, (inp, out) in _FILTERS.items()
                ]
            ),
        )
        version = bedrock.CfnGuardrailVersion(
            self,
            "GuardrailVersionResource",
            guardrail_identifier=guardrail.attr_guardrail_id,
        )
        role = iam.Role(
            self,
            "DevConverse",
            assumed_by=iam.ArnPrincipal(trust).with_conditions(_MFA_CONDITION),
            max_session_duration=Duration.hours(1),
            description="Temporary credentials for nonstreaming Bedrock Converse",
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeSelectedNova2LiteProfile",
                actions=["bedrock:InvokeModel"],
                resources=[profile],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeSelectedNova2LiteFoundationModels",
                actions=["bedrock:InvokeModel"],
                resources=list(_MODEL_ARNS),
                conditions={
                    "StringEquals": {"bedrock:InferenceProfileArn": profile},
                },
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="ApplyFewiaGuardrail",
                actions=["bedrock:ApplyGuardrail"],
                resources=[guardrail.attr_guardrail_arn],
            )
        )
        for key, value in _TAGS.items():
            Tags.of(self).add(key, value)
        CfnOutput(self, "RoleArn", value=role.role_arn)
        CfnOutput(self, "GuardrailId", value=guardrail.attr_guardrail_id)
        CfnOutput(self, "GuardrailVersion", value=version.attr_version)


def _context_str(stack: Stack, key: str) -> str:
    value = stack.node.try_get_context(key)
    if not isinstance(value, str) or not value.strip() or "*" in value:
        raise ValueError(f"CDK context {key} MUST be a nonblank exact value")
    return value.strip()
