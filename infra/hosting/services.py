from aws_cdk import Duration
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from constructs import Construct

from app_task import HostingAppTask
from network import HostingNetwork
from worker_tasks import HostingWorkerTasks


class HostingServices(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        network: HostingNetwork,
        app_task: HostingAppTask,
        worker_tasks: HostingWorkerTasks,
        services_enabled: bool = False,
    ) -> None:
        if not isinstance(services_enabled, bool):
            raise ValueError("services_enabled MUST be a bool")
        super().__init__(scope, construct_id)
        self.cluster: ecs.Cluster = ecs.Cluster(
            self, "Cluster", vpc=network.vpc, container_insights=False
        )
        desired_count = 1 if services_enabled else 0
        self.app_service: ecs.FargateService = self._service(
            "AppService",
            network,
            app_task.task_definition,
            desired_count,
            Duration.seconds(60),
        )
        self.agent_service: ecs.FargateService = self._service(
            "AgentService", network, worker_tasks.agent_task, desired_count
        )

    def _service(
        self,
        construct_id: str,
        network: HostingNetwork,
        task_definition: ecs.FargateTaskDefinition,
        desired_count: int,
        health_check_grace_period: Duration | None = None,
    ) -> ecs.FargateService:
        return ecs.FargateService(
            self,
            construct_id,
            cluster=self.cluster,
            task_definition=task_definition,
            desired_count=desired_count,
            platform_version=ecs.FargatePlatformVersion.VERSION1_4,
            vpc_subnets=ec2.SubnetSelection(subnet_group_name="Application"),
            assign_public_ip=False,
            security_groups=[network.app_security_group],
            enable_execute_command=False,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            min_healthy_percent=100,
            max_healthy_percent=200,
            health_check_grace_period=health_check_grace_period,
            propagate_tags=ecs.PropagatedTagSource.TASK_DEFINITION,
            enable_ecs_managed_tags=True,
        )
