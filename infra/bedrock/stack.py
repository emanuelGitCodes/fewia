"""Development IAM role for nonstreaming Bedrock Converse."""

import re

from aws_cdk import CfnOutput, Duration, Environment, Stack, Tags
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
        for key, value in _TAGS.items():
            Tags.of(self).add(key, value)
        CfnOutput(self, "RoleArn", value=role.role_arn)


def _context_str(stack: Stack, key: str) -> str:
    value = stack.node.try_get_context(key)
    if not isinstance(value, str) or not value.strip() or "*" in value:
        raise ValueError(f"CDK context {key} MUST be a nonblank exact value")
    return value.strip()
