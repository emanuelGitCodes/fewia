from aws_cdk import aws_iam as iam
from constructs import Construct

from assets import HostingAssets
from database import HostingDatabase
from task_trust import new_task_role


class HostingExecutionRoles(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assets: HostingAssets,
        database: HostingDatabase,
    ) -> None:
        super().__init__(scope, construct_id)
        backend_arn = assets.backend_repository.repository_arn
        application_arn = database.application_secret.secret_arn
        self.app_execution_role: iam.Role = self._execution_role(
            "AppExecutionRole",
            [backend_arn, assets.frontend_repository.repository_arn],
            [assets.api_logs.log_group_arn, assets.web_logs.log_group_arn],
            [application_arn],
        )
        self.agent_execution_role: iam.Role = self._execution_role(
            "AgentExecutionRole",
            [backend_arn],
            [assets.agent_logs.log_group_arn],
            [application_arn],
        )
        self.sync_execution_role: iam.Role = self._execution_role(
            "SyncExecutionRole",
            [backend_arn],
            [assets.sync_logs.log_group_arn],
            [application_arn],
        )
        self.bootstrap_execution_role: iam.Role = self._execution_role(
            "BootstrapExecutionRole",
            [backend_arn],
            [assets.bootstrap_logs.log_group_arn],
            [database.admin_secret.secret_arn, application_arn],
        )

    def _execution_role(
        self,
        construct_id: str,
        repository_arns: list[str],
        log_arns: list[str],
        secret_arns: list[str],
    ) -> iam.Role:
        role = new_task_role(self, construct_id)
        role.add_to_policy(
            iam.PolicyStatement(actions=["ecr:GetAuthorizationToken"], resources=["*"])
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=repository_arns,
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=log_arns,
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"], resources=secret_arns
            )
        )
        return role
