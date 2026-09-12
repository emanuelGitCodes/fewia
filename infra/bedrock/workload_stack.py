"""Unattended Bedrock runtime IAM user."""

import re

from aws_cdk import CfnOutput, Environment, RemovalPolicy, Stack, Tags
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
_USER_NAME = "fewia-bedrock-runtime"
_USER_PATH = "/fewia/"
_TAGS = {
    "Project": "FEWIA",
    "Environment": "development",
    "Component": "bedrock-chat",
    "ManagedBy": "AWS-CDK",
    "Model": "amazon.nova-2-lite-v1:0",
    "ReasoningEffort": "low",
    "CostCenter": "FEWIA",
}


class BedrockRuntimeStack(Stack):
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
        profile = (
            f"arn:aws:bedrock:{_ORIGIN_REGION}:{self.account}"
            f":inference-profile/{_PROFILE_ID}"
        )
        user = iam.CfnUser(
            self,
            "RuntimeUser",
            user_name=_USER_NAME,
            path=_USER_PATH,
            policies=[
                iam.CfnUser.PolicyProperty(
                    policy_name="InvokeSelectedNova2Lite",
                    policy_document=iam.PolicyDocument(
                        statements=[
                            iam.PolicyStatement(
                                sid="InvokeSelectedNova2LiteProfile",
                                actions=["bedrock:InvokeModel"],
                                resources=[profile],
                            ),
                            iam.PolicyStatement(
                                sid="InvokeSelectedNova2LiteFoundationModels",
                                actions=["bedrock:InvokeModel"],
                                resources=list(_MODEL_ARNS),
                                conditions={
                                    "StringEquals": {
                                        "bedrock:InferenceProfileArn": profile,
                                    },
                                },
                            ),
                        ]
                    ).to_json(),
                )
            ],
        )
        user.apply_removal_policy(RemovalPolicy.RETAIN)
        for key, value in _TAGS.items():
            Tags.of(user).add(key, value)
        CfnOutput(self, "UserArn", value=user.attr_arn)
        CfnOutput(self, "UserName", value=_USER_NAME)
