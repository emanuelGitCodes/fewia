from dataclasses import asdict

from aws_cdk import CfnOutput, Environment, Stack
from constructs import Construct

from app_task import HostingAppTask
from assets import HostingAssets
from database import HostingDatabase
from deployment_config import REGION, DeploymentConfig, parse_deployment_config
from edge import HostingEdge
from execution_roles import HostingExecutionRoles
from identity import HostingIdentity
from network import HostingNetwork
from services import HostingServices
from stack import HostingResources
from task_roles import HostingTaskRoles
from worker_tasks import HostingWorkerTasks


class HostedDemoStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, config: DeploymentConfig
    ) -> None:
        config = parse_deployment_config(asdict(config))
        super().__init__(
            scope,
            construct_id,
            env=Environment(account=config.account, region=REGION),
            termination_protection=True,
        )
        self.network: HostingNetwork = HostingNetwork(self, "Network")
        self.resources: HostingResources = HostingResources(self, "Resources")
        self.database: HostingDatabase = HostingDatabase(
            self, "Database", network=self.network
        )
        self.assets: HostingAssets = HostingAssets(self, "Assets")
        self.execution_roles: HostingExecutionRoles = HostingExecutionRoles(
            self, "ExecutionRoles", assets=self.assets, database=self.database
        )
        self.task_roles: HostingTaskRoles = HostingTaskRoles(
            self, "TaskRoles", resources=self.resources
        )
        self.identity: HostingIdentity | None = None
        self.app_task: HostingAppTask | None = None
        self.worker_tasks: HostingWorkerTasks | None = None
        self.services: HostingServices | None = None
        self.edge: HostingEdge | None = None
        for key, value in {
            "DeploymentPhase": config.phase,
            "BackendRepositoryName": self.assets.backend_repository.repository_name,
            "BackendRepositoryUri": self.assets.backend_repository.repository_uri,
            "FrontendRepositoryName": self.assets.frontend_repository.repository_name,
            "FrontendRepositoryUri": self.assets.frontend_repository.repository_uri,
            "DatabaseInstanceIdentifier": self.database.instance.instance_identifier,
            "ApplicationSubnetIds": ",".join(
                subnet.subnet_id for subnet in self.network.vpc.private_subnets
            ),
            "ApplicationSecurityGroupId": (
                self.network.app_security_group.security_group_id
            ),
        }.items():
            CfnOutput(self, key, value=value)
        if config.phase == "foundation":
            return
        runtime = config.runtime
        assert runtime is not None
        self.identity = HostingIdentity(
            self,
            "Identity",
            hostname=runtime.hostname,
            domain_prefix=runtime.domain_prefix,
        )
        self.app_task = HostingAppTask(
            self,
            "AppTask",
            assets=self.assets,
            database=self.database,
            resources=self.resources,
            execution_roles=self.execution_roles,
            task_roles=self.task_roles,
            backend_digest=runtime.backend_digest,
            frontend_digest=runtime.frontend_digest,
        )
        self.worker_tasks = HostingWorkerTasks(
            self,
            "WorkerTasks",
            assets=self.assets,
            database=self.database,
            resources=self.resources,
            execution_roles=self.execution_roles,
            task_roles=self.task_roles,
            backend_digest=runtime.backend_digest,
        )
        self.services = HostingServices(
            self,
            "Services",
            network=self.network,
            app_task=self.app_task,
            worker_tasks=self.worker_tasks,
            services_enabled=config.phase == "active",
        )
        self.edge = HostingEdge(
            self,
            "Edge",
            network=self.network,
            identity=self.identity,
            service=self.services.app_service,
            certificate_arn=runtime.certificate_arn,
        )
        for key, value in {
            "ClusterName": self.services.cluster.cluster_name,
            "ClusterArn": self.services.cluster.cluster_arn,
            "AppServiceName": self.services.app_service.service_name,
            "AgentServiceName": self.services.agent_service.service_name,
            "BootstrapTaskDefinitionArn": (
                self.worker_tasks.bootstrap_task.task_definition_arn
            ),
            "LoadBalancerDnsName": self.edge.load_balancer.load_balancer_dns_name,
            "LoadBalancerHostedZoneId": (
                self.edge.load_balancer.load_balancer_canonical_hosted_zone_id
            ),
            "UserPoolId": self.identity.user_pool.user_pool_id,
            "UserPoolClientId": self.identity.client.user_pool_client_id,
            "DemoUrl": f"https://{runtime.hostname}/",
        }.items():
            CfnOutput(self, key, value=value)
