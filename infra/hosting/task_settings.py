import re
from urllib.parse import quote

from aws_cdk import Stack
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs

from database import HostingDatabase
from identity import SIGNED_OUT_PATH, HostingIdentity
from stack import HostingResources


def image_from_digest(repository: ecr.IRepository, digest: str) -> ecs.ContainerImage:
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
    ):
        raise ValueError(
            "image digest MUST be sha256: followed by 64 lowercase hex digits"
        )
    return ecs.ContainerImage.from_ecr_repository(repository, digest)


def application_environment(
    database: HostingDatabase, resources: HostingResources
) -> dict[str, str]:
    return {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": database.instance.db_instance_endpoint_address,
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_app",
        "FEWIA_TRANSPORT_MODE": "aws",
        "AWS_REGION": Stack.of(resources).region,
        "FEWIA_AWS_AGENT_QUEUE_URL": resources.agent_queue.queue_url,
        "FEWIA_AWS_SYNC_QUEUE_URL": resources.sync_queue.queue_url,
        "FEWIA_SPENDING_SOURCE": "manual",
        "FEWIA_BEDROCK_REGION": "us-east-1",
        "FEWIA_BEDROCK_MODEL_ID": "us.amazon.nova-2-lite-v1:0",
    }


def application_secrets(database: HostingDatabase) -> dict[str, ecs.Secret]:
    return {
        "FEWIA_DATABASE_PASSWORD": ecs.Secret.from_secrets_manager(
            database.application_secret, "password"
        ),
    }


def browser_auth_environment(
    identity: HostingIdentity, *, signer_arn: str
) -> dict[str, str]:
    origin = f"https://{identity.hostname}"
    client_id = identity.client.user_pool_client_id
    logout_uri = quote(f"{origin}{SIGNED_OUT_PATH}", safe="")
    return {
        "FEWIA_AUTH_MODE": "alb",
        "FEWIA_PUBLIC_ORIGIN": origin,
        "FEWIA_ALB_SIGNER_ARN": signer_arn,
        "FEWIA_AUTH_CLIENT_ID": client_id,
        "FEWIA_AUTH_ISSUER": identity.user_pool.user_pool_provider_url,
        "FEWIA_AUTH_LOGOUT_URL": (
            f"{identity.domain.base_url()}/logout?client_id={client_id}"
            f"&logout_uri={logout_uri}"
        ),
    }


def bootstrap_environment(database: HostingDatabase) -> dict[str, str]:
    return {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": database.instance.db_instance_endpoint_address,
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_admin",
    }


def bootstrap_secrets(database: HostingDatabase) -> dict[str, ecs.Secret]:
    return {
        "FEWIA_DATABASE_PASSWORD": ecs.Secret.from_secrets_manager(
            database.admin_secret, "password"
        ),
        "FEWIA_APPLICATION_DATABASE_PASSWORD": ecs.Secret.from_secrets_manager(
            database.application_secret, "password"
        ),
    }
