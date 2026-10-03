"""Aggregate captured evaluation metrics without model output."""

import math
from typing import cast


def _map(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _number(value: object, latency: bool = False) -> int | float | None:
    if type(value) is int and value >= 0:
        if not latency:
            return value
        try:
            return float(value)
        except OverflowError:
            return None
    if latency and type(value) is float and math.isfinite(value) and value >= 0:
        return value
    return None


def _metric(values: list[object], latency: bool = False) -> dict[str, object]:
    known = [n for value in values if (n := _number(value, latency)) is not None]
    total = sum(known) if known else None
    if isinstance(total, float) and not math.isfinite(total):
        total = None
    return {
        "total": total if len(known) == len(values) else None,
        "known_total": total,
        "sample_count": len(known),
        "unknown_count": len(values) - len(known),
    }


def _turns(slot: dict[str, object]) -> list[dict[str, object]]:
    turns = _map(slot.get("observation")).get("turns")
    return [_map(turn) for turn in turns] if isinstance(turns, list) else []


def _measure(bundles: list[list[dict[str, object]]]) -> dict[str, object]:
    turns = [turn for bundle in bundles for turn in bundle]
    usage = [_map(turn.get("usage")) for turn in turns]
    unknown_turns = sum(
        any(_number(item.get(key)) is None for key in ("inputTokens", "outputTokens"))
        for item in usage
    )
    unknown_slots = sum(
        not bundle
        or any(
            _number(_map(turn.get("usage")).get(key)) is None
            for turn in bundle
            for key in ("inputTokens", "outputTokens")
        )
        for bundle in bundles
    )
    result: dict[str, object] = {
        "known_usage_turns": len(turns) - unknown_turns,
        "unknown_usage_turns": unknown_turns,
        "known_usage_slots": len(bundles) - unknown_slots,
        "unknown_usage_slots": unknown_slots,
    }
    for source in ("inputTokens", "outputTokens"):
        target = "input_tokens" if source == "inputTokens" else "output_tokens"
        metric = _metric([item.get(source) for item in usage])
        result[target] = metric["total"] if not unknown_slots else None
        result[f"known_{target}"] = metric["known_total"]
    for key in ("provider_calls", "elapsed_seconds", "provider_elapsed_seconds"):
        latency = key != "provider_calls"
        metric = _metric([turn.get(key) for turn in turns], latency)
        metric["unknown_slot_count"] = sum(
            not bundle
            or any(_number(turn.get(key), latency) is None for turn in bundle)
            for bundle in bundles
        )
        if any(not bundle for bundle in bundles):
            metric["total"] = None
        result["turn_elapsed_seconds" if key == "elapsed_seconds" else key] = metric
    return result


def _label(value: object) -> str:
    return value if isinstance(value, str) else "unknown"


def summarize_telemetry(slots: list[dict[str, object]]) -> dict[str, object]:
    """Report captured attempts by condition and evidence class."""
    if type(slots) is not list:
        raise ValueError("slots is invalid")
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for item in slots:
        slot = _map(item)
        observation = _map(slot.get("observation"))
        condition = _label(slot.get("condition", observation.get("condition")))
        evidence = _label(observation.get("evidence_class"))
        grouped.setdefault((condition, evidence), []).append(slot)
    groups: list[dict[str, object]] = []
    for (condition, evidence), items in sorted(grouped.items()):
        elapsed = _metric([slot.get("elapsed_seconds") for slot in items], True)
        ordered = sorted(
            number
            for slot in items
            if (number := _number(slot.get("elapsed_seconds"), True)) is not None
        )
        for percentile in (50, 95):
            rank = (percentile * len(ordered) + 99) // 100
            elapsed[f"p{percentile}"] = ordered[rank - 1] if ordered else None
        elapsed["percentile_method"] = "nearest-rank"
        rows: list[dict[str, object]] = []
        statuses = {"completed": 0, "failed": 0, "partial": 0, "unknown": 0}
        for slot in items:
            observation = _map(slot.get("observation"))
            status = _label(observation.get("status"))
            status = status if status in statuses else "unknown"
            statuses[status] += 1
            rows.append(
                {
                    "case_id": _label(slot.get("case_id", observation.get("case_id"))),
                    "repeat": _number(slot.get("repeat")),
                    "model_id": _label(observation.get("model_id")),
                    "status": status,
                    "slot_elapsed_seconds": _number(slot.get("elapsed_seconds"), True),
                    **_measure([_turns(slot)]),
                }
            )
        groups.append(
            {
                "condition": condition,
                "evidence_class": evidence,
                "scope": (
                    "All attempts in this condition and evidence class. "
                    "Usage/calls: turn provider capture; known totals: lower bounds. "
                    "Slot/turn seconds: end-to-end; provider seconds: provider-only."
                ),
                "total_slots": len(items),
                "observed_slots": sum(
                    isinstance(slot.get("observation"), dict) for slot in items
                ),
                "observation_counts": statuses,
                "slot_elapsed_seconds": elapsed,
                **_measure([_turns(slot) for slot in items]),
                "slots": rows,
            }
        )
    return {"total_slots": len(slots), "groups": groups, "billed_cost_estimate": None}
