"""Honest latency and token aggregation for evaluation batch slots."""

import math
from typing import cast

_FAILED = frozenset({"failed", "partial"})
_QUALITY_NOTE = (
    "Counts do not establish quality, tool selection, claim support, "
    "or live provider readiness."
)
_TOKEN_NOTE = (
    "known_input_tokens and known_output_tokens sum known_usage_slots. "
    "input_tokens and output_tokens are null when unknown_usage_slots is not 0 "
    "or known_usage_slots is 0. Fixtures do not imply observed zero usage. "
    "Missing usage stays unknown."
)


def _as_map(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def _elapsed(value: object) -> float | None:
    if type(value) is bool:
        return None
    if type(value) is int:
        try:
            seconds = float(value)
        except OverflowError:
            return None
    elif type(value) is float:
        seconds = value
    else:
        return None
    if not math.isfinite(seconds) or seconds < 0.0:
        return None
    return seconds


def _tokens(value: object) -> tuple[int, int] | None:
    usage = _as_map(value)
    if usage is None:
        return None
    input_tokens = usage.get("inputTokens")
    output_tokens = usage.get("outputTokens")
    if type(input_tokens) is not int or type(output_tokens) is not int:
        return None
    if input_tokens < 0 or output_tokens < 0:
        return None
    return input_tokens, output_tokens


def _measure(turns: object) -> tuple[float | None, tuple[int, int] | None]:
    if type(turns) is not list or not turns:
        return None, None
    total = 0.0
    input_tokens = 0
    output_tokens = 0
    latency_ok = True
    usage_ok = True
    for item in turns:
        body = _as_map(item)
        if body is None:
            return None, None
        seconds = _elapsed(body.get("elapsed_seconds"))
        if seconds is None or not math.isfinite(total + seconds):
            latency_ok = False
        else:
            total += seconds
        result = _as_map(body.get("result"))
        pair = None if result is None else _tokens(result.get("usage"))
        if body.get("status") != "completed" or pair is None:
            usage_ok = False
        else:
            input_tokens += pair[0]
            output_tokens += pair[1]
    latency = total if latency_ok else None
    usage = (input_tokens, output_tokens) if usage_ok else None
    return latency, usage


def summarize_telemetry(slots: list[dict[str, object]]) -> dict[str, object]:
    """Report inspectable slot counts, nearest-rank latency, and known tokens."""
    if type(slots) is not list:
        raise ValueError("slots is invalid")
    total = 0
    observed = 0
    completed = 0
    failed = 0
    latencies: list[float] = []
    known = 0
    unknown = 0
    known_in = 0
    known_out = 0
    for item in slots:
        total += 1
        slot = _as_map(item)
        if slot is None or "observation" not in slot:
            continue
        observed += 1
        observation = _as_map(slot.get("observation"))
        if observation is None:
            unknown += 1
            continue
        status = observation.get("status")
        if status == "completed":
            completed += 1
        elif type(status) is str and status in _FAILED:
            failed += 1
        latency, usage = _measure(observation.get("turns"))
        if latency is not None:
            latencies.append(latency)
        if status != "completed" or usage is None:
            unknown += 1
            continue
        known += 1
        known_in += usage[0]
        known_out += usage[1]
    overall_in: int | None = known_in if known and unknown == 0 else None
    overall_out: int | None = known_out if known and unknown == 0 else None
    p50: float | None = None
    p95: float | None = None
    if latencies:
        ordered = sorted(latencies)
        count = len(ordered)
        p50 = ordered[math.ceil(50 / 100 * count) - 1]
        p95 = ordered[math.ceil(95 / 100 * count) - 1]
    return {
        "total_slots": total,
        "observed_slots": observed,
        "completed_observations": completed,
        "failed_or_partial_observations": failed,
        "latency_sample_count": len(latencies),
        "p50_latency_seconds": p50,
        "p95_latency_seconds": p95,
        "percentile_method": "nearest-rank",
        "known_usage_slots": known,
        "unknown_usage_slots": unknown,
        "known_input_tokens": known_in,
        "known_output_tokens": known_out,
        "input_tokens": overall_in,
        "output_tokens": overall_out,
        "quality_note": _QUALITY_NOTE,
        "token_note": _TOKEN_NOTE,
    }
