from aws_cdk import ArnFormat, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

from stack import HostingResources
from task_trust import new_task_role


class HostingTaskRoles(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        resources: HostingResources,
    ) -> None:
        super().__init__(scope, construct_id)
        self.api_role: iam.Role = new_task_role(self, "ApiRole")
        self.agent_role: iam.Role = new_task_role(self, "AgentRole")
        self.sync_role: iam.Role = new_task_role(self, "SyncRole")
        self.bootstrap_role: iam.Role = new_task_role(self, "BootstrapRole")

        for role, queue in (
            (self.agent_role, resources.agent_queue),
            (self.sync_role, resources.sync_queue),
        ):
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=["sqs:SendMessage"],
                    resources=[
                        resources.agent_queue.queue_arn,
                        resources.sync_queue.queue_arn,
                    ],
                )
            )
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "sqs:ReceiveMessage",
                        "sqs:DeleteMessage",
                        "sqs:ChangeMessageVisibility",
                    ],
                    resources=[queue.queue_arn],
                )
            )

        stack = Stack.of(self)
        profile_arn = stack.format_arn(
            service="bedrock",
            region="us-east-1",
            resource="inference-profile",
            resource_name="us.amazon.nova-2-lite-v1:0",
            arn_format=ArnFormat.SLASH_RESOURCE_NAME,
        )
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeSelectedNova2LiteProfile",
                actions=["bedrock:InvokeModel"],
                resources=[profile_arn],
            )
        )
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeSelectedNova2LiteFoundationModels",
                actions=["bedrock:InvokeModel"],
                resources=[
                    stack.format_arn(
                        service="bedrock",
                        region=region,
                        account="",
                        resource="foundation-model",
                        resource_name="amazon.nova-2-lite-v1:0",
                        arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                    )
                    for region in ("us-east-1", "us-east-2", "us-west-2")
                ],
                conditions={
                    "StringEquals": {"bedrock:InferenceProfileArn": profile_arn},
                },
            )
        )
