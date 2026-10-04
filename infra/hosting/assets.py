from aws_cdk import RemovalPolicy
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_logs as logs
from constructs import Construct


class HostingAssets(Construct):
    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)
        self.backend_repository: ecr.Repository = self._repository("BackendRepository")
        self.frontend_repository: ecr.Repository = self._repository(
            "FrontendRepository"
        )
        self.api_logs: logs.LogGroup = self._logs("ApiLogs")
        self.web_logs: logs.LogGroup = self._logs("WebLogs")
        self.agent_logs: logs.LogGroup = self._logs("AgentLogs")
        self.sync_logs: logs.LogGroup = self._logs("SyncLogs")
        self.bootstrap_logs: logs.LogGroup = self._logs("BootstrapLogs")

    def _repository(self, construct_id: str) -> ecr.Repository:
        return ecr.Repository(
            self,
            construct_id,
            encryption=ecr.RepositoryEncryption.AES_256,
            image_tag_mutability=ecr.TagMutability.IMMUTABLE,
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.RETAIN,
            empty_on_delete=False,
        )

    def _logs(self, construct_id: str) -> logs.LogGroup:
        return logs.LogGroup(
            self,
            construct_id,
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.RETAIN,
        )
