from aws_cdk import ArnFormat, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


def new_task_role(scope: Construct, construct_id: str) -> iam.Role:
    stack = Stack.of(scope)
    return iam.Role(
        scope,
        construct_id,
        assumed_by=iam.ServicePrincipal(
            "ecs-tasks.amazonaws.com",
            conditions={
                "StringEquals": {"aws:SourceAccount": stack.account},
                "ArnLike": {
                    "aws:SourceArn": stack.format_arn(
                        service="ecs",
                        resource="*",
                        arn_format=ArnFormat.NO_RESOURCE_NAME,
                    )
                },
            },
        ),
    )
