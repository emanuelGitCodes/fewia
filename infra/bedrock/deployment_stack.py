"""CloudFormation execution role for the unattended Bedrock runtime user."""

import re

from aws_cdk import CfnOutput, Environment, RemovalPolicy, Stack, Tags
from aws_cdk import aws_iam as iam
from constructs import Construct

_ORIGIN_REGION = "us-east-1"
_ACCOUNT = re.compile(r"^[0-9]{12}$")
_ROLE_NAME = "fewia-bedrock-runtime-deployment"
_USER_ARN = "arn:aws:iam::{account}:user/fewia/fewia-bedrock-runtime"
_USER_LOOKUP_ARN = "arn:aws:iam::{account}:user/fewia-bedrock-runtime"
_USER_ACTIONS = [
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
]
_USER_LOOKUP_ACTIONS = [
    "iam:GetUser",
    "iam:GetUserPolicy",
]
_TAGS = {
    "Project": "FEWIA",
    "Environment": "development",
    "Component": "bedrock-deployment",
    "ManagedBy": "AWS-CDK",
    "Model": "amazon.nova-2-lite-v1:0",
    "ReasoningEffort": "low",
    "CostCenter": "FEWIA",
}


class BedrockRuntimeDeploymentStack(Stack):
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
        role = iam.Role(
            self,
            "RuntimeDeployment",
            role_name=_ROLE_NAME,
            assumed_by=iam.ServicePrincipal("cloudformation.amazonaws.com"),
            inline_policies={
                "ManageRuntimeUser": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=_USER_ACTIONS,
                            resources=[_USER_ARN.format(account=self.account)],
                        ),
                        # CloudFormation GetUser uses the unpathed user ARN.
                        iam.PolicyStatement(
                            sid="ReadRuntimeUserBeforeCreation",
                            actions=_USER_LOOKUP_ACTIONS,
                            resources=[_USER_LOOKUP_ARN.format(account=self.account)],
                        ),
                    ]
                )
            },
        )
        role.apply_removal_policy(RemovalPolicy.RETAIN)
        for key, value in _TAGS.items():
            Tags.of(role).add(key, value)
            Tags.of(self).add(key, value)
        CfnOutput(self, "DeploymentRoleArn", value=role.role_arn)
