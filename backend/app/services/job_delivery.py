import json
from collections.abc import Callable
from typing import Protocol, cast
from uuid import UUID

from app.providers.local_sqs_consumer import QueueMessage


class JobQueue(Protocol):
    def receive(self) -> QueueMessage | None: ...
    def acknowledge(self, message: QueueMessage) -> None: ...
    def extend(self, message: QueueMessage, seconds: int) -> None: ...


class JobHandler(Protocol):
    def __call__(
        self, payload: dict[str, object], heartbeat: Callable[[], None]
    ) -> dict[str, object]: ...


class LeaseLost(RuntimeError): ...


class RetryableJobError(RuntimeError): ...


class JobFailure(RuntimeError):
    def __init__(self, error_code: str, detail: dict[str, str]) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.detail = detail


_MAX_ENVELOPE_LENGTH = 256


def _object_without_duplicates(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    envelope: dict[str, object] = {}
    for key, value in pairs:
        if key in envelope:
            raise ValueError
        envelope[key] = value
    return envelope


def _job_id(body: str) -> str | None:
    if not isinstance(body, str) or len(body) > _MAX_ENVELOPE_LENGTH:
        return None
    try:
        envelope = json.loads(body, object_pairs_hook=_object_without_duplicates)
        if not isinstance(envelope, dict) or set(envelope) != {"job_id"}:
            return None
        value = envelope["job_id"]
        return value if isinstance(value, str) and str(UUID(value)) == value else None
    except (RecursionError, TypeError, ValueError, KeyError):
        return None


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError
    return cast(dict[str, object], json.loads(json.dumps(value, allow_nan=False)))
