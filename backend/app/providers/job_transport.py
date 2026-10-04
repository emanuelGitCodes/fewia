from typing import cast

from app.providers.aws_sqs_consumer import AwsSqsConsumer
from app.providers.aws_sqs_sender import AwsSqsSender
from app.providers.job_transport_settings import JobTransportSettings
from app.providers.local_sqs import LocalSqsSender
from app.providers.local_sqs_consumer import LocalSqsConsumer
from app.services.job_delivery import JobQueue
from app.services.outbox_publisher import JobSender


def _validated_settings(settings: JobTransportSettings) -> JobTransportSettings:
    if type(settings) is not JobTransportSettings:
        raise ValueError("Job transport configuration is invalid")
    return JobTransportSettings(
        mode=settings.mode,
        endpoint=settings.endpoint,
        region=settings.region,
        agent_queue_url=settings.agent_queue_url,
        sync_queue_url=settings.sync_queue_url,
    )


def build_job_sender(settings: JobTransportSettings) -> JobSender:
    validated = _validated_settings(settings)
    if validated.mode == "local":
        return LocalSqsSender(endpoint_url=cast(str, validated.endpoint))
    return AwsSqsSender(
        region=cast(str, validated.region),
        agent_queue_url=cast(str, validated.agent_queue_url),
        sync_queue_url=cast(str, validated.sync_queue_url),
    )


def build_job_queue(settings: JobTransportSettings, kind: str) -> JobQueue:
    if type(kind) is not str or kind not in ("agent", "sync"):
        raise ValueError("kind MUST be agent or sync")
    validated = _validated_settings(settings)
    if validated.mode == "local":
        return LocalSqsConsumer(endpoint_url=cast(str, validated.endpoint), kind=kind)
    queue_url = (
        validated.agent_queue_url if kind == "agent" else validated.sync_queue_url
    )
    return AwsSqsConsumer(
        region=cast(str, validated.region), queue_url=cast(str, queue_url)
    )
