from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest
from aws_cdk import App, CfnResource, Environment, Stack
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk.assertions import Template
from constructs import IConstruct

from assets import HostingAssets
from database import HostingDatabase
from network import HostingNetwork
from stack import HostingResources, HostingStack
from task_settings import (
    application_environment,
    application_secrets,
    bootstrap_environment,
    bootstrap_secrets,
    image_from_digest,
)

_ACCOUNT = "111122223333"
_REGION = "us-west-2"
_DIGEST = "sha256:" + "0123456789abcdef" * 4
_Case = tuple[Stack, HostingAssets, HostingDatabase, HostingResources]


@pytest.fixture(params=[False, True], ids=["tokens", "concrete"])
def settings_case(request: pytest.FixtureRequest, tmp_path: Path) -> _Case:
    concrete: bool = request.param
    app = App(
        outdir=str(tmp_path / "assembly"),
        context={
            f"availability-zones:account={_ACCOUNT}:region={_REGION}": [
                "us-west-2a",
                "us-west-2b",
            ]
        },
    )
    stack = Stack(
        app,
        "SettingsTest",
        env=Environment(account=_ACCOUNT, region=_REGION) if concrete else None,
    )
    assets = HostingAssets(stack, "Assets")
    database = HostingDatabase(
        stack, "Database", network=HostingNetwork(stack, "Network")
    )
    resources = HostingResources(stack, "Resources")
    return stack, assets, database, resources


def _logical_id(resource: IConstruct) -> str:
    child = resource.node.default_child
    assert isinstance(child, CfnResource)
    return Stack.of(resource).get_logical_id(child)


def test_application_environment_has_exact_values(settings_case: _Case) -> None:
    stack, _, database, resources = settings_case
    environment = application_environment(database, resources)
    assert environment == {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": database.instance.db_instance_endpoint_address,
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_app",
        "FEWIA_TRANSPORT_MODE": "aws",
        "AWS_REGION": stack.region,
        "FEWIA_AWS_AGENT_QUEUE_URL": resources.agent_queue.queue_url,
        "FEWIA_AWS_SYNC_QUEUE_URL": resources.sync_queue.queue_url,
        "FEWIA_SPENDING_SOURCE": "manual",
        "FEWIA_BEDROCK_REGION": "us-east-1",
        "FEWIA_BEDROCK_MODEL_ID": "us.amazon.nova-2-lite-v1:0",
    }
    assert stack.resolve(environment) == {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": {
            "Fn::GetAtt": [_logical_id(database.instance), "Endpoint.Address"]
        },
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_app",
        "FEWIA_TRANSPORT_MODE": "aws",
        "AWS_REGION": stack.resolve(stack.region),
        "FEWIA_AWS_AGENT_QUEUE_URL": {"Ref": _logical_id(resources.agent_queue)},
        "FEWIA_AWS_SYNC_QUEUE_URL": {"Ref": _logical_id(resources.sync_queue)},
        "FEWIA_SPENDING_SOURCE": "manual",
        "FEWIA_BEDROCK_REGION": "us-east-1",
        "FEWIA_BEDROCK_MODEL_ID": "us.amazon.nova-2-lite-v1:0",
    }


def test_bootstrap_environment_has_only_admin_database_values(
    settings_case: _Case,
) -> None:
    stack, _, database, _ = settings_case
    environment = bootstrap_environment(database)
    assert environment == {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": database.instance.db_instance_endpoint_address,
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_admin",
    }
    assert stack.resolve(environment) == {
        "FEWIA_DATABASE_MODE": "aws",
        "FEWIA_DATABASE_HOST": {
            "Fn::GetAtt": [_logical_id(database.instance), "Endpoint.Address"]
        },
        "FEWIA_DATABASE_NAME": "fewia",
        "FEWIA_DATABASE_USER": "fewia_admin",
    }


def test_secrets_map_only_assigned_arns_and_password_fields(
    settings_case: _Case,
) -> None:
    stack, _, database, _ = settings_case
    application = application_secrets(database)
    bootstrap = bootstrap_secrets(database)
    application_reference = {
        "Fn::Join": [
            "",
            [{"Ref": _logical_id(database.application_secret)}, ":password::"],
        ]
    }
    admin_reference = {
        "Fn::Join": [
            "",
            [{"Ref": _logical_id(database.admin_secret)}, ":password::"],
        ]
    }
    assert all(isinstance(secret, ecs.Secret) for secret in application.values())
    assert all(isinstance(secret, ecs.Secret) for secret in bootstrap.values())
    assert {key: stack.resolve(secret.arn) for key, secret in application.items()} == {
        "FEWIA_DATABASE_PASSWORD": application_reference
    }
    assert {key: stack.resolve(secret.arn) for key, secret in bootstrap.items()} == {
        "FEWIA_DATABASE_PASSWORD": admin_reference,
        "FEWIA_APPLICATION_DATABASE_PASSWORD": application_reference,
    }
    assert admin_reference != application_reference
    assert stack.resolve(application["FEWIA_DATABASE_PASSWORD"].arn) != admin_reference


def test_each_builder_returns_a_fresh_dictionary(settings_case: _Case) -> None:
    _, _, database, resources = settings_case
    application = application_environment(database, resources)
    next_application = application_environment(database, resources)
    assert application is not next_application
    assert application == next_application
    application["FEWIA_DATABASE_USER"] = "changed"
    assert next_application == application_environment(database, resources)

    bootstrap = bootstrap_environment(database)
    next_bootstrap = bootstrap_environment(database)
    assert bootstrap is not next_bootstrap
    assert bootstrap == next_bootstrap
    bootstrap.clear()
    assert next_bootstrap == bootstrap_environment(database)

    secrets = application_secrets(database)
    next_secrets = application_secrets(database)
    assert secrets is not next_secrets
    secrets.clear()
    assert set(next_secrets) == {"FEWIA_DATABASE_PASSWORD"}

    admin_secrets = bootstrap_secrets(database)
    next_admin_secrets = bootstrap_secrets(database)
    assert admin_secrets is not next_admin_secrets
    admin_secrets.clear()
    assert set(next_admin_secrets) == {
        "FEWIA_DATABASE_PASSWORD",
        "FEWIA_APPLICATION_DATABASE_PASSWORD",
    }


def test_image_uses_repository_digest(settings_case: _Case) -> None:
    stack, assets, _, _ = settings_case
    for repository in (assets.backend_repository, assets.frontend_repository):
        with patch.object(
            ecs.ContainerImage,
            "from_ecr_repository",
            wraps=ecs.ContainerImage.from_ecr_repository,
        ) as constructor:
            image = image_from_digest(repository, _DIGEST)
            constructor.assert_called_once_with(repository, _DIGEST)
        assert isinstance(image, ecs.ContainerImage)
        assert isinstance(image, ecs.EcrImage)
        assert stack.resolve(image.image_name) == stack.resolve(
            repository.repository_uri + "@" + _DIGEST
        )


@pytest.mark.parametrize(
    "digest",
    [
        None,
        True,
        256,
        1.5,
        b"sha256:" + b"a" * 64,
        [],
        {},
        "",
        "latest",
        "v1.0",
        "a" * 64,
        "sha256:" + "a" * 63,
        "sha256:" + "a" * 65,
        "SHA256:" + "a" * 64,
        "sha256:" + "A" * 64,
        "sha256:" + "g" * 64,
        "sha256:" + "\uff11" * 64,
        "sha384:" + "a" * 64,
        " " + _DIGEST,
        _DIGEST + " ",
        "\t" + _DIGEST,
        _DIGEST + "\n",
        "sha256: " + "a" * 64,
        "https://example.invalid/repository@" + _DIGEST,
        "111122223333.dkr.ecr.us-east-1.amazonaws.com/backend@" + _DIGEST,
        "backend:" + _DIGEST,
    ],
)
def test_invalid_digest_is_rejected_before_image_construction(
    digest: object, tmp_path: Path
) -> None:
    stack = Stack(App(outdir=str(tmp_path / "invalid")), "Invalid")
    repository = ecr.Repository.from_repository_name(stack, "Repository", "backend")
    with patch.object(ecs.ContainerImage, "from_ecr_repository") as constructor:
        with pytest.raises(ValueError, match="image digest"):
            image_from_digest(repository, cast(str, digest))
        constructor.assert_not_called()


def test_builders_add_no_constructs_or_infrastructure(settings_case: _Case) -> None:
    stack, assets, database, resources = settings_case
    before_template = Template.from_stack(stack).to_json()
    before_construct_paths = tuple(node.node.path for node in stack.node.find_all())
    builders: tuple[Callable[[], object], ...] = (
        lambda: application_environment(database, resources),
        lambda: application_secrets(database),
        lambda: bootstrap_environment(database),
        lambda: bootstrap_secrets(database),
        lambda: image_from_digest(assets.backend_repository, _DIGEST),
    )
    for builder in builders:
        builder()
        assert Template.from_stack(stack).to_json() == before_template
        assert (
            tuple(node.node.path for node in stack.node.find_all())
            == before_construct_paths
        )
    template = Template.from_stack(stack)
    for resource_type in (
        "AWS::ECS::TaskDefinition",
        "AWS::ECS::Service",
        "AWS::IAM::Role",
        "AWS::IAM::Policy",
        "AWS::IAM::User",
        "AWS::IAM::AccessKey",
    ):
        template.resource_count_is(resource_type, 0)
    assert not before_template.get("Outputs")


def test_hosting_stack_keeps_task_settings_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "dormant")),
        "Dormant",
        env=Environment(account=_ACCOUNT, region="us-east-1"),
    )
    template = Template.from_stack(stack)
    expected = {
        "AWS::SQS::Queue": 4,
        "AWS::SQS::QueuePolicy": 4,
        "AWS::S3::Bucket": 1,
        "AWS::S3::BucketPolicy": 1,
    }
    for resource_type, count in expected.items():
        template.resource_count_is(resource_type, count)
    assert {item["Type"] for item in template.to_json()["Resources"].values()} <= (
        set(expected) | {"AWS::CDK::Metadata"}
    )
    assert set(template.to_json()["Outputs"]) == {
        "AgentQueueUrl",
        "AgentDlqUrl",
        "SyncQueueUrl",
        "SyncDlqUrl",
        "ArtifactBucketName",
    }
