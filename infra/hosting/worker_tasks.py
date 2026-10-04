from aws_cdk import Duration
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from constructs import Construct

from assets import HostingAssets
from database import HostingDatabase
from execution_roles import HostingExecutionRoles
from stack import HostingResources
from task_roles import HostingTaskRoles
from task_settings import (
    application_environment,
    application_secrets,
    bootstrap_environment,
    bootstrap_secrets,
    image_from_digest,
)


class HostingWorkerTasks(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assets: HostingAssets,
        database: HostingDatabase,
        resources: HostingResources,
        execution_roles: HostingExecutionRoles,
        task_roles: HostingTaskRoles,
        backend_digest: str,
    ) -> None:
        super().__init__(scope, construct_id)
        image = image_from_digest(assets.backend_repository, backend_digest)
        self.agent_task: ecs.FargateTaskDefinition = self._task(
            "AgentTask", execution_roles.agent_execution_role, task_roles.agent_role
        )
        self.agent_container: ecs.ContainerDefinition = self.agent_task.add_container(
            "agent",
            container_name="agent",
            image=image,
            command=[
                "python",
                "-m",
                "app.worker",
                "--transport",
                "aws",
                "--kind",
                "agent",
            ],
            environment=application_environment(database, resources),
            secrets=application_secrets(database),
            logging=ecs.LogDrivers.aws_logs(
                log_group=assets.agent_logs, stream_prefix="agent"
            ),
            essential=True,
            readonly_root_filesystem=True,
            user="1000:1000",
            stop_timeout=Duration.seconds(120),
        )
        self.bootstrap_task: ecs.FargateTaskDefinition = self._task(
            "BootstrapTask",
            execution_roles.bootstrap_execution_role,
            task_roles.bootstrap_role,
        )
        self.bootstrap_container: ecs.ContainerDefinition = (
            self.bootstrap_task.add_container(
                "bootstrap",
                container_name="bootstrap",
                image=image,
                command=["python", "-m", "app.bootstrap_hosting", "--run"],
                environment=bootstrap_environment(database),
                secrets=bootstrap_secrets(database),
                logging=ecs.LogDrivers.aws_logs(
                    log_group=assets.bootstrap_logs, stream_prefix="bootstrap"
                ),
                essential=True,
                readonly_root_filesystem=True,
                user="1000:1000",
                stop_timeout=Duration.seconds(30),
            )
        )

    def _task(
        self, name: str, execution_role: iam.IRole, task_role: iam.IRole
    ) -> ecs.FargateTaskDefinition:
        return ecs.FargateTaskDefinition(
            self,
            name,
            cpu=512,
            memory_limit_mib=1024,
            execution_role=execution_role,
            task_role=task_role,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=ecs.CpuArchitecture.X86_64,
            ),
        )
