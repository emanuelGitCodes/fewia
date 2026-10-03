"""Validate local and task-role job transport settings."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, NoReturn

from app.providers.aws_sqs_sender import validate_queue_url
from app.providers.local_sqs import ALLOWED_ENDPOINTS

_FORBIDDEN_AWS_KEYS = frozenset(
    {
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CONFIG_FILE",
        "FEWIA_AWS_PROFILE",
        "AWS_ENDPOINT_URL",
        "AWS_ENDPOINT_URL_SQS",
    }
)
_QUEUE_KEYS = ("FEWIA_AWS_AGENT_QUEUE_URL", "FEWIA_AWS_SYNC_QUEUE_URL")


def _invalid() -> NoReturn:
    raise ValueError("Job transport configuration is invalid")


@dataclass(frozen=True)
class JobTransportSettings:
    mode: Literal["local", "aws"]
    endpoint: str | None = field(default=None, repr=False)
    region: str | None = None
    agent_queue_url: str | None = field(default=None, repr=False)
    sync_queue_url: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.mode) is not str or self.mode not in ("local", "aws"):
            _invalid()
        if self.mode == "local":
            if (
                type(self.endpoint) is not str
                or self.endpoint not in ALLOWED_ENDPOINTS
                or self.region is not None
                or self.agent_queue_url is not None
                or self.sync_queue_url is not None
            ):
                _invalid()
            return
        if (
            self.endpoint is not None
            or type(self.region) is not str
            or type(self.agent_queue_url) is not str
            or type(self.sync_queue_url) is not str
        ):
            _invalid()
        valid = False
        try:
            agent = validate_queue_url(self.region, self.agent_queue_url)
            sync = validate_queue_url(self.region, self.sync_queue_url)
            valid = agent != sync and agent.split("/")[3] == sync.split("/")[3]
        except ValueError:
            pass
        if not valid:
            _invalid()


def load_job_transport(
    *,
    mode: str | None = None,
    endpoint: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> JobTransportSettings:
    env = os.environ if environ is None else environ
    keys = frozenset(env)
    env_mode = env.get("FEWIA_TRANSPORT_MODE", "local")
    if mode is not None and "FEWIA_TRANSPORT_MODE" in keys and mode != env_mode:
        _invalid()
    selected_mode = env_mode if mode is None else mode
    if type(selected_mode) is not str or selected_mode not in ("local", "aws"):
        _invalid()
    if selected_mode == "local":
        if any(key in keys for key in _QUEUE_KEYS):
            _invalid()
        env_endpoint = env.get("FEWIA_LOCAL_ENDPOINT_URL", "http://127.0.0.1:4566")
        if (
            endpoint is not None
            and "FEWIA_LOCAL_ENDPOINT_URL" in keys
            and endpoint != env_endpoint
        ):
            _invalid()
        return JobTransportSettings(
            mode="local", endpoint=env_endpoint if endpoint is None else endpoint
        )
    if (
        endpoint is not None
        or "FEWIA_LOCAL_ENDPOINT_URL" in keys
        or any(key in keys for key in _FORBIDDEN_AWS_KEYS)
    ):
        _invalid()
    return JobTransportSettings(
        mode="aws",
        region=env.get("AWS_REGION"),
        agent_queue_url=env.get(_QUEUE_KEYS[0]),
        sync_queue_url=env.get(_QUEUE_KEYS[1]),
    )
