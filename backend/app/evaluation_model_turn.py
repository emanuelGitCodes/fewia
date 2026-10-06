from collections.abc import Callable
from time import perf_counter
from types import TracebackType
from typing import cast

from app.agent import chat_loop
from app.agent.chat_messages import ChatProtocolError
from app.agent.provider import LLMProvider
from app.evaluation_adversarial import sanitize_public
from app.evaluation_capture import CaptureProvider
from app.evaluation_inputs import CaseContext


class _OrdinaryErrorBoundary:
    def __init__(self) -> None:
        self.failed: bool = False

    def __enter__(self) -> "_OrdinaryErrorBoundary":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if not isinstance(exception, Exception):
            return False
        if isinstance(exception, (chat_loop.ChatUnavailable, ChatProtocolError)):
            return False
        self.failed = True
        return True


def observe_model_turn(
    context: CaseContext,
    message: str,
    provider: LLMProvider,
    *,
    markers: tuple[str, ...],
    history: list[dict[str, str]],
    previous_request: dict[str, object] | None,
    record_evidence: Callable[[dict[str, object]], str],
    previous_ingredient_ids: list[str] | None = None,
) -> dict[str, object]:
    """Observe one production chat turn with sanitized public evidence."""
    started = perf_counter()
    capture = CaptureProvider(provider, markers)

    def public(value: dict[str, object]) -> dict[str, object]:
        try:
            capture.leakage |= capture._leaks(value, set())
        except (RecursionError, TypeError, ValueError):
            capture.capture_incomplete = True
        try:
            clean = sanitize_public(value, markers)
            capture.leakage |= clean != sanitize_public(value, ())
        except (RecursionError, TypeError, ValueError):
            capture.capture_incomplete = True
            raise
        return cast(dict[str, object], clean)

    def record(planning: dict[str, object]) -> str:
        return record_evidence(public(planning))

    result: dict[str, object] | None = None
    status = "completed"
    reason: str | None = None
    boundary = _OrdinaryErrorBoundary()
    inputs: dict[str, object] = {
        "message": message,
        "history": history,
        "previous_request": previous_request,
        "previous_ingredient_ids": previous_ingredient_ids,
    }
    try:
        leaked_inputs = capture._leaks(inputs, set())
        capture.leakage |= sanitize_public(inputs, markers) != inputs or leaked_inputs
    except (RecursionError, TypeError, ValueError):
        capture.capture_incomplete = True
    try:
        with boundary:
            if not capture.leakage and not capture.capture_incomplete:
                result = public(
                    chat_loop.run_chat(
                        capture,
                        message,
                        context.budget,
                        context.period,
                        user_id=context.user_id,
                        spending_source="fixture",
                        previous_request=previous_request,
                        previous_ingredient_ids=previous_ingredient_ids,
                        history=history or None,
                        record_evidence=record,
                        plan_cap_cents=context.plan_cap_cents,
                    )
                )
                if result.get("status") == "limit":
                    status, reason = "partial", "limit"
                elif result.get("status") == "incomplete":
                    status, reason = "partial", "incomplete"
    except chat_loop.ChatUnavailable:
        status, reason = "failed", "provider_unavailable"
    except ChatProtocolError:
        status, reason = "failed", "protocol_error"
    if boundary.failed:
        status, reason = "failed", "unexpected_error"
    if capture.leakage:
        status, reason = "failed", "secret_leak"
        secret_leak: bool | None = True
    elif capture.capture_incomplete:
        status = "partial" if result is not None else "failed"
        reason = "capture_incomplete"
        secret_leak = None
    else:
        secret_leak = False
    turn: dict[str, object] = {
        "status": status,
        "reason": reason,
        "result": result,
        "elapsed_seconds": perf_counter() - started,
        "provider_elapsed_seconds": capture.elapsed_seconds,
        "calls": capture.calls,
        "tool_results": capture.tool_results,
        "provider_calls": capture.provider_calls,
        "usage": capture.usage,
        "invalid_responses": capture.invalid_responses,
        "capture_incomplete": capture.capture_incomplete,
        "secret_leak": secret_leak,
    }
    return cast(dict[str, object], sanitize_public(turn, markers))
