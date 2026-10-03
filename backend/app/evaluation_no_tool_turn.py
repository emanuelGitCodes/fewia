from dataclasses import asdict
from time import perf_counter
from types import TracebackType
from typing import cast

from app.agent.chat_context import build_messages
from app.agent.provider import LLMProvider
from app.evaluation_adversarial import sanitize_public
from app.evaluation_baseline_response import (
    BASELINE_SYSTEM_PROMPT,
    parse_baseline_response,
)
from app.evaluation_capture import CaptureProvider
from app.evaluation_inputs import CaseContext
from app.evaluation_manifest import _canonical_json


class _ProviderFailure(Exception):
    pass


class _ProviderExceptionBoundary:
    def __enter__(self) -> None:
        pass

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if isinstance(exc_value, Exception):
            raise _ProviderFailure("provider_failed") from None


class _SanitizedProvider:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ) -> dict[str, object]:
        with _ProviderExceptionBoundary():
            return self._provider.converse(system_prompt, messages, tools)


def observe_no_tool_turn(
    context: CaseContext,
    message: str,
    provider: LLMProvider,
    *,
    catalog: dict[str, object],
    markers: tuple[str, ...],
    history: list[dict[str, str]],
    previous_request: dict[str, object] | None,
) -> dict[str, object]:
    started = perf_counter()
    capture = CaptureProvider(_SanitizedProvider(provider), markers)
    result: dict[str, object] | None = None
    reason: str | None = None
    protocol_valid: bool | None = None
    try:
        budget = asdict(context.budget)
        budget["warnings"] = list(context.budget.warnings)
        facts: dict[str, object] = {
            "message": message,
            "budget": budget,
            "catalog": catalog,
            "history": history,
            "previous_request": previous_request,
        }
        if sanitize_public(facts, markers) != facts:
            raise ValueError("invalid inputs")
        messages = build_messages(
            message,
            context.budget,
            context.period,
            user_id=context.user_id,
            plan_cap_cents=context.plan_cap_cents,
            previous_request=previous_request,
            history=history,
        )
        content = cast(list[dict[str, object]], messages[-1]["content"])
        content.insert(0, {"text": _canonical_json({"catalog": catalog})})
        outgoing = {"system_prompt": BASELINE_SYSTEM_PROMPT, "messages": messages}
        if sanitize_public(outgoing, markers) != outgoing:
            raise ValueError("invalid inputs")
        response = capture.converse(BASELINE_SYSTEM_PROMPT, messages, [])
    except _ProviderFailure:
        reason = "provider_failed"
    except (
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        LookupError,
        ArithmeticError,
        AttributeError,
    ):
        reason = "provider_failed" if capture.provider_calls else "invalid_inputs"
    else:
        protocol_valid = False
        try:
            parsed = parse_baseline_response(response)
            result = cast(
                dict[str, object],
                sanitize_public(parsed, markers),
            )
            capture.leakage |= result != parsed
            protocol_valid = True
        except (TypeError, ValueError, RecursionError, OverflowError):
            stop = response.get("stopReason") if isinstance(response, dict) else None
            reason = (
                "tool_use_rejected"
                if capture.calls or stop == "tool_use"
                else "invalid_output"
            )
    if capture.leakage:
        reason = "secret_leak"
    elif capture.capture_incomplete:
        reason = "capture_incomplete"
    secret_leak = None if capture.capture_incomplete else False
    return {
        "status": "failed" if reason else "completed",
        "result": result,
        "reason": reason,
        "calls": capture.calls,
        "tool_results": capture.tool_results,
        "usage": capture.usage if capture.provider_calls else None,
        "attempts": capture.provider_calls,
        "provider_calls": capture.provider_calls,
        "provider_elapsed_seconds": capture.elapsed_seconds,
        "elapsed_seconds": perf_counter() - started,
        "invalid_responses": capture.invalid_responses,
        "capture_incomplete": capture.capture_incomplete,
        "secret_leak": True if capture.leakage else secret_leak,
        "protocol_valid": protocol_valid,
    }
