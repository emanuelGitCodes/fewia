import json
from pathlib import Path

import pytest
from aws_cdk import App, Environment, Stack, Token
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_logs as logs
from aws_cdk.assertions import Template
from constructs import Construct

from assets import HostingAssets
from stack import HostingStack


@pytest.fixture
def assets_stack(tmp_path: Path) -> tuple[Stack, HostingAssets, Template]:
    stack = Stack(App(outdir=str(tmp_path / "assembly")), "AssetsTest")
    assets = HostingAssets(stack, "Assets")
    return stack, assets, Template.from_stack(stack)


def _logical_id(stack: Stack, resource: Construct) -> str:
    child = resource.node.default_child
    assert isinstance(child, (ecr.CfnRepository, logs.CfnLogGroup))
    return stack.get_logical_id(child)


def test_inventory_has_only_two_repositories_and_five_log_groups(
    assets_stack: tuple[Stack, HostingAssets, Template],
) -> None:
    _, _, template = assets_stack
    template.resource_count_is("AWS::ECR::Repository", 2)
    template.resource_count_is("AWS::Logs::LogGroup", 5)
    resources = template.to_json()["Resources"]
    assert {resource["Type"] for resource in resources.values()} <= {
        "AWS::ECR::Repository",
        "AWS::Logs::LogGroup",
        "AWS::CDK::Metadata",
    }
    assert not template.to_json().get("Outputs")


def test_repositories_are_encrypted_immutable_scanned_and_retained(
    assets_stack: tuple[Stack, HostingAssets, Template],
) -> None:
    _, _, template = assets_stack
    for resource in template.find_resources("AWS::ECR::Repository").values():
        props = resource["Properties"]
        encryption = props.get("EncryptionConfiguration", {"EncryptionType": "AES256"})
        assert encryption == {"EncryptionType": "AES256"}
        assert props["ImageTagMutability"] == "IMMUTABLE"
        assert props["ImageScanningConfiguration"] == {"ScanOnPush": True}
        assert props.get("EmptyOnDelete", False) is False
        assert set(props) <= {
            "EncryptionConfiguration",
            "ImageTagMutability",
            "ImageScanningConfiguration",
            "EmptyOnDelete",
        }
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["UpdateReplacePolicy"] == "Retain"


def test_log_groups_expire_events_after_one_month_and_survive_deletion(
    assets_stack: tuple[Stack, HostingAssets, Template],
) -> None:
    _, _, template = assets_stack
    for resource in template.find_resources("AWS::Logs::LogGroup").values():
        assert resource["Properties"] == {"RetentionInDays": 30}
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["UpdateReplacePolicy"] == "Retain"


def test_construct_exports_distinct_typed_resources(
    assets_stack: tuple[Stack, HostingAssets, Template],
) -> None:
    stack, assets, template = assets_stack
    repositories = (assets.backend_repository, assets.frontend_repository)
    groups = (
        assets.api_logs,
        assets.web_logs,
        assets.agent_logs,
        assets.sync_logs,
        assets.bootstrap_logs,
    )
    assert all(isinstance(repository, ecr.Repository) for repository in repositories)
    assert all(isinstance(group, logs.LogGroup) for group in groups)
    repository_ids = {_logical_id(stack, repository) for repository in repositories}
    group_ids = {_logical_id(stack, group) for group in groups}
    assert len(repository_ids) == 2
    assert len(group_ids) == 5
    assert repository_ids == set(template.find_resources("AWS::ECR::Repository"))
    assert group_ids == set(template.find_resources("AWS::Logs::LogGroup"))
    assert repository_ids.isdisjoint(group_ids)


@pytest.mark.parametrize("environment_value", [None, "invalid-environment-value"])
def test_synthesis_needs_no_environment_account_region_or_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, environment_value: str | None
) -> None:
    for name in (
        "CDK_DEFAULT_ACCOUNT",
        "CDK_DEFAULT_REGION",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ):
        if environment_value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, environment_value)
    app = App(outdir=str(tmp_path / "assembly"), context={})
    stack = Stack(app, "NoEnvironment")
    HostingAssets(stack, "Assets")
    assert Token.is_unresolved(stack.account)
    assert Token.is_unresolved(stack.region)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::ECR::Repository", 2)
    template.resource_count_is("AWS::Logs::LogGroup", 5)
    assembly = app.synth()
    assert len(assembly.stacks) == 1
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing")


def test_hosting_stack_keeps_assets_dormant(tmp_path: Path) -> None:
    stack = HostingStack(
        App(outdir=str(tmp_path / "assembly")),
        "HostingTest",
        env=Environment(account="111122223333", region="us-east-1"),
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
    assert not any(isinstance(child, HostingAssets) for child in stack.node.children)
