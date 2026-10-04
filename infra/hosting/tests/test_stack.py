from pathlib import Path
from typing import Any, cast

import pytest
from aws_cdk import App, Aws, Environment
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from aws_cdk.assertions import Template
from constructs import Construct

from stack import HostingResources, HostingStack

_ACCOUNT = "111122223333"
_TAGS = {
    "Project": "FEWIA",
    "Environment": "development",
    "ManagedBy": "AWS-CDK",
    "Component": "hosting",
}


@pytest.fixture
def stack(tmp_path: Path) -> HostingStack:
    return HostingStack(
        App(outdir=str(tmp_path / "assembly")),
        "Test",
        env=Environment(account=_ACCOUNT, region="us-east-1"),
    )


@pytest.fixture
def template(stack: HostingStack) -> Template:
    return Template.from_stack(stack)


def _logical_id(stack: HostingStack, resource: Construct) -> str:
    child = resource.node.default_child
    assert isinstance(child, (sqs.CfnQueue, s3.CfnBucket))
    return stack.get_logical_id(child)


def _assert_tls_deny(statement: dict[str, Any], action: str) -> None:
    assert statement["Effect"] == "Deny"
    assert statement["Action"] == action
    assert statement["Principal"] in ("*", {"AWS": "*"})
    assert statement["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}


def test_inventory_has_only_private_storage_resources(template: Template) -> None:
    resources = template.to_json()["Resources"]
    expected = {
        "AWS::SQS::Queue": 4,
        "AWS::SQS::QueuePolicy": 4,
        "AWS::S3::Bucket": 1,
        "AWS::S3::BucketPolicy": 1,
    }
    types = {item["Type"] for item in resources.values()}
    assert set(expected) <= types
    assert types <= set(expected) | {"AWS::CDK::Metadata"}
    for resource_type, count in expected.items():
        template.resource_count_is(resource_type, count)


def test_construct_exports_typed_resources(stack: HostingStack) -> None:
    resources = stack.resources
    assert isinstance(resources, HostingResources)
    queues = (
        resources.agent_queue,
        resources.agent_dlq,
        resources.sync_queue,
        resources.sync_dlq,
    )
    assert all(isinstance(queue, sqs.Queue) for queue in queues)
    assert len({_logical_id(stack, queue) for queue in queues}) == 4
    assert isinstance(resources.artifact_bucket, s3.Bucket)


def test_sources_use_exact_distinct_dlqs(
    stack: HostingStack, template: Template
) -> None:
    queues = template.find_resources("AWS::SQS::Queue")
    resources = stack.resources
    for source, dlq in (
        (resources.agent_queue, resources.agent_dlq),
        (resources.sync_queue, resources.sync_dlq),
    ):
        source_props = queues[_logical_id(stack, source)]["Properties"]
        dlq_props = queues[_logical_id(stack, dlq)]["Properties"]
        assert source_props["RedrivePolicy"] == {
            "deadLetterTargetArn": {
                "Fn::GetAtt": [_logical_id(stack, dlq), "Arn"],
            },
            "maxReceiveCount": 3,
        }
        assert source_props["VisibilityTimeout"] == 120
        assert source_props["MessageRetentionPeriod"] == 4 * 24 * 60 * 60
        assert dlq_props["MessageRetentionPeriod"] == 14 * 24 * 60 * 60
        assert "RedrivePolicy" not in dlq_props


def test_all_queues_are_encrypted_standard_and_retained(template: Template) -> None:
    for resource in template.find_resources("AWS::SQS::Queue").values():
        props = resource["Properties"]
        assert props["SqsManagedSseEnabled"] is True
        assert "KmsMasterKeyId" not in props
        assert "QueueName" not in props
        assert not props.get("FifoQueue", False)
        assert not props.get("ContentBasedDeduplication", False)
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["UpdateReplacePolicy"] == "Retain"


def test_each_queue_denies_insecure_transport(template: Template) -> None:
    queues = template.find_resources("AWS::SQS::Queue")
    protected: set[str] = set()
    for policy in template.find_resources("AWS::SQS::QueuePolicy").values():
        props = policy["Properties"]
        statements = props["PolicyDocument"]["Statement"]
        assert len(statements) == 1
        statement = statements[0]
        _assert_tls_deny(statement, "sqs:*")
        queue_id, attribute = statement["Resource"]["Fn::GetAtt"]
        assert attribute == "Arn"
        assert queue_id in queues
        assert queue_id not in protected
        assert props["Queues"] == [{"Ref": queue_id}]
        protected.add(queue_id)
    assert protected == set(queues)


def test_artifacts_are_private_encrypted_versioned_and_retained(
    template: Template,
) -> None:
    buckets = template.find_resources("AWS::S3::Bucket")
    assert len(buckets) == 1
    bucket = next(iter(buckets.values()))
    props = bucket["Properties"]
    assert props["BucketEncryption"] == {
        "ServerSideEncryptionConfiguration": [
            {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}},
        ],
    }
    assert props["VersioningConfiguration"] == {"Status": "Enabled"}
    assert props["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
    for key in (
        "BucketName",
        "AccessControl",
        "CorsConfiguration",
        "WebsiteConfiguration",
        "LifecycleConfiguration",
    ):
        assert key not in props
    assert bucket["DeletionPolicy"] == "Retain"
    assert bucket["UpdateReplacePolicy"] == "Retain"


def test_artifacts_deny_insecure_bucket_and_object_access(
    stack: HostingStack, template: Template
) -> None:
    policies = template.find_resources("AWS::S3::BucketPolicy")
    assert len(policies) == 1
    props = next(iter(policies.values()))["Properties"]
    bucket = stack.resources.artifact_bucket
    assert props["Bucket"] == {"Ref": _logical_id(stack, bucket)}
    statements = props["PolicyDocument"]["Statement"]
    assert len(statements) == 1
    statement = statements[0]
    _assert_tls_deny(statement, "s3:*")
    assert statement["Resource"] == stack.resolve(
        [bucket.bucket_arn, bucket.arn_for_objects("*")]
    )


def test_tags_and_outputs_reference_only_defined_resources(
    stack: HostingStack, template: Template
) -> None:
    for resource_type in ("AWS::SQS::Queue", "AWS::S3::Bucket"):
        for resource in template.find_resources(resource_type).values():
            tags = resource["Properties"]["Tags"]
            assert {tag["Key"]: tag["Value"] for tag in tags} == _TAGS
    resources = stack.resources
    expected = {
        "AgentQueueUrl": resources.agent_queue.queue_url,
        "AgentDlqUrl": resources.agent_dlq.queue_url,
        "SyncQueueUrl": resources.sync_queue.queue_url,
        "SyncDlqUrl": resources.sync_dlq.queue_url,
        "ArtifactBucketName": resources.artifact_bucket.bucket_name,
    }
    outputs = template.to_json()["Outputs"]
    assert set(outputs) == set(expected)
    for name, value in expected.items():
        assert outputs[name] == {"Value": stack.resolve(value)}


@pytest.mark.parametrize(
    "account",
    [
        None,
        "",
        "11112222333",
        "1111222233333",
        "11112222333x",
        " 111122223333",
        "111122223333\n",
        "１１１１２２２２３３３３",
        Aws.ACCOUNT_ID,
    ],
)
def test_invalid_account_fails_before_stack_exists(
    tmp_path: Path, account: str | None
) -> None:
    app = App(outdir=str(tmp_path / "assembly"))
    with pytest.raises(ValueError, match="12-digit"):
        HostingStack(
            app,
            "Invalid",
            env=Environment(account=account, region="us-east-1"),
        )
    assert app.node.try_find_child("Invalid") is None
    assert app.synth().stacks == []


@pytest.mark.parametrize("region", [None, "", "us-east-2", "us-west-2", Aws.REGION])
def test_invalid_region_fails_before_stack_exists(
    tmp_path: Path, region: str | None
) -> None:
    app = App(outdir=str(tmp_path / "assembly"))
    with pytest.raises(ValueError, match="us-east-1"):
        HostingStack(
            app,
            "Invalid",
            env=Environment(account=_ACCOUNT, region=region),
        )
    assert app.node.try_find_child("Invalid") is None
    assert app.synth().stacks == []


def test_app_synthesizes_locally_from_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app as entrypoint

    application = App(
        outdir=str(tmp_path / "assembly"),
        context={"account": _ACCOUNT, "region": "us-east-1"},
    )
    monkeypatch.setattr(entrypoint, "App", lambda: application)
    entrypoint.main()
    result = cast(HostingStack, application.node.find_child("FewiaHostingDev"))
    assert result.account == _ACCOUNT
    assert result.region == "us-east-1"
    Template.from_stack(result).resource_count_is("AWS::SQS::Queue", 4)


@pytest.mark.parametrize(
    "context",
    [{}, {"account": 123, "region": "us-east-1"}, {"account": _ACCOUNT}],
)
def test_app_rejects_missing_or_nonstring_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, context: dict[str, object]
) -> None:
    import app as entrypoint

    application = App(outdir=str(tmp_path / "assembly"), context=context)
    monkeypatch.setattr(entrypoint, "App", lambda: application)
    with pytest.raises(ValueError, match="CDK context"):
        entrypoint.main()
    assert application.node.try_find_child("FewiaHostingDev") is None
