from aws_cdk import Duration
from aws_cdk import aws_ecs as ecs
from constructs import Construct

from assets import HostingAssets
from database import HostingDatabase
from execution_roles import HostingExecutionRoles
from stack import HostingResources
from task_roles import HostingTaskRoles
from task_settings import (
    application_environment,
    application_secrets,
    image_from_digest,
)


class HostingAppTask(Construct):
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
        frontend_digest: str,
    ) -> None:
        backend_image = image_from_digest(assets.backend_repository, backend_digest)
        frontend_image = image_from_digest(assets.frontend_repository, frontend_digest)
        super().__init__(scope, construct_id)
        self.task_definition: ecs.FargateTaskDefinition = ecs.FargateTaskDefinition(
            self,
            "TaskDefinition",
            cpu=512,
            memory_limit_mib=1024,
            runtime_platform=ecs.RuntimePlatform(
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
                cpu_architecture=ecs.CpuArchitecture.X86_64,
            ),
            execution_role=execution_roles.app_execution_role,
            task_role=task_roles.api_role,
        )
        self.api_container: ecs.ContainerDefinition
        self.api_container = self.task_definition.add_container(
            "Api",
            container_name="api",
            image=backend_image,
            environment=application_environment(database, resources),
            secrets=application_secrets(database),
            essential=True,
            readonly_root_filesystem=True,
            user="1000:1000",
            privileged=False,
            stop_timeout=Duration.seconds(30),
            port_mappings=[
                ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
            ],
            logging=ecs.LogDrivers.aws_logs(
                log_group=assets.api_logs, stream_prefix="api"
            ),
            health_check=ecs.HealthCheck(
                command=[
                    "CMD",
                    "python",
                    "-c",
                    "import urllib.request; urllib.request.urlopen("
                    "'http://127.0.0.1:8000/healthz', timeout=5).close()",
                ],
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30),
                retries=3,
                start_period=Duration.seconds(30),
            ),
        )
        self.web_container: ecs.ContainerDefinition
        self.web_container = self.task_definition.add_container(
            "Web",
            container_name="web",
            image=frontend_image,
            environment={"FEWIA_API_UPSTREAM": "127.0.0.1:8000"},
            essential=True,
            readonly_root_filesystem=True,
            user="101:101",
            privileged=False,
            stop_timeout=Duration.seconds(30),
            port_mappings=[
                ecs.PortMapping(container_port=8080, protocol=ecs.Protocol.TCP)
            ],
            logging=ecs.LogDrivers.aws_logs(
                log_group=assets.web_logs, stream_prefix="web"
            ),
        )
        for name, path in (
            ("nginx-tmp", "/tmp"),
            ("nginx-conf", "/etc/nginx/conf.d"),
        ):
            self.task_definition.add_volume(name=name)
            self.web_container.add_mount_points(
                ecs.MountPoint(source_volume=name, container_path=path, read_only=False)
            )
        self.web_container.add_container_dependencies(
            ecs.ContainerDependency(
                container=self.api_container,
                condition=ecs.ContainerDependencyCondition.HEALTHY,
            )
        )
