import re

from aws_cdk import CfnOutput, Duration, Environment, RemovalPolicy, Stack, Tags
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct

from network import HOSTING_AVAILABILITY_ZONES


class HostingResources(Construct):
    def __init__(self, scope: Construct, construct_id: str) -> None:
        super().__init__(scope, construct_id)
        self.agent_dlq: sqs.Queue = self._queue("AgentDlq", 14)
        self.sync_dlq: sqs.Queue = self._queue("SyncDlq", 14)
        self.agent_queue: sqs.Queue = self._queue("AgentQueue", 4, self.agent_dlq)
        self.sync_queue: sqs.Queue = self._queue("SyncQueue", 4, self.sync_dlq)
        self.artifact_bucket: s3.Bucket = s3.Bucket(
            self,
            "Artifacts",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            enforce_ssl=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

    def _queue(
        self, name: str, retention_days: int, dlq: sqs.Queue | None = None
    ) -> sqs.Queue:
        return sqs.Queue(
            self,
            name,
            encryption=sqs.QueueEncryption.SQS_MANAGED,
            enforce_ssl=True,
            visibility_timeout=Duration.seconds(120),
            retention_period=Duration.days(retention_days),
            removal_policy=RemovalPolicy.RETAIN,
            dead_letter_queue=(
                sqs.DeadLetterQueue(queue=dlq, max_receive_count=3) if dlq else None
            ),
        )


class HostingStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, env: Environment
    ) -> None:
        if env.account is None or re.fullmatch(r"[0-9]{12}", env.account) is None:
            raise ValueError("stack account MUST be a concrete 12-digit AWS account id")
        if env.region != "us-east-1":
            raise ValueError("stack region MUST be us-east-1")
        super().__init__(scope, construct_id, env=env)
        self.resources: HostingResources = HostingResources(self, "Resources")
        for key, value in {
            "Project": "FEWIA",
            "Environment": "development",
            "ManagedBy": "AWS-CDK",
            "Component": "hosting",
        }.items():
            Tags.of(self).add(key, value)
        for key, value in {
            "AgentQueueUrl": self.resources.agent_queue.queue_url,
            "AgentDlqUrl": self.resources.agent_dlq.queue_url,
            "SyncQueueUrl": self.resources.sync_queue.queue_url,
            "SyncDlqUrl": self.resources.sync_dlq.queue_url,
            "ArtifactBucketName": self.resources.artifact_bucket.bucket_name,
        }.items():
            CfnOutput(self, key, value=value)

    @property
    def availability_zones(self) -> list[str]:
        return list(HOSTING_AVAILABILITY_ZONES)
