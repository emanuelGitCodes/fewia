"""Separate evaluation scoring data from durable public artifacts."""

import hashlib
import math
import re
from typing import cast

from app.evaluation_summary_metrics import (
    _CLAIMS,
    sum_binary_metrics,
    sum_claim_counts,
    validate_checks,
)

_PINNED = {
    "scenarios": "e79ac07c30a52cea05be3e72eb106528ba8f12b9e968876a6a332efaf1931222",
    "conversation": "7a63b0d979de741d45bc7fc5bc1e2250329ff6e136746c52b76c85f38c9bf467",
}
_VALUES = frozenset(
    "completed failed partial unassessed assessed passed not_applicable "
    "planned needs_revision clarification incomplete limit success error "
    "tool_enabled no_tool deterministic controlled_fixture deterministic_fixture "
    "model no_tool reference duplicate budget plan refresh kroger retrieval "
    "meals followup missing handoff protocol unknown "
    "real_bedrock real_openai deterministic_fake_provider deterministic_reference "
    "fixture controlled_fake pure_function local_floci local_database "
    "complete_evaluation grocery-eval-v1.1 conversation-eval-v1.6 "
    "sample-prices-v2 evaluation-manifest-v1 conversation-manifest-v1 "
    "template model none clean proposal tool_failed not_final planner no_tools "
    "refusal planned_terminal discovery_terminal guardrail saved_plan_read "
    "swap_not_saved missing invalid low medium high USD PASS FAIL "
    "nova-2-lite nova-2-pro gpt-6-luna gpt-6-sol gpt-6.1-sol "
    "us.amazon.nova-2-lite-v1:0 us.amazon.nova-2-pro-v1:0 "
    "us-east-1 us-west-2 us global "
    "get_plan get_meal get_budget_summary get_ingredient_facts plan_groceries "
    "what_if_substitute price_lines propose_plan_change search_meals unsupported "
    "missing_local_services slot_execution_failed provider_unavailable "
    "protocol_error unexpected_error secret_leak capture_incomplete "
    "provider_failed invalid_inputs invalid_output tool_use_rejected "
    "evidence_contract_mismatch tool_selection tool_arguments unnecessary_calls "
    "claim_support ingredient_coverage budget_compliance constraint_violations "
    "completion recovery duplicate_jobs price_staleness secret_leakage "
    "purchase_attempts purchase_refusal_rate latency_p50_ms latency_p95_ms "
    "cost_per_turn_usd numeric_mismatch unsupported_number unsupported_claim "
    "money_mismatch unmatched_number unsupported_text unsupported_character "
    "empty too_long store_price forbidden_claim medical_claim number_word "
    "conversation-report-v1 lower_is_better final_plan final_turn public_output_only "
    "valid_calls expected_tool_selection expected_arguments "
    "N/A prose grounded_rate unsupported_numbers".split()
)
_HASH_KEYS = frozenset(
    "revision corpus_sha256 corpus_hash catalog_hash system_prompt_hash "
    "baseline_system_prompt_hash proposal_prompt_hash tool_specs_hash "
    "model_config_hash manifest_hash selection_hash".split()
)
_SECRET = re.compile(
    r"(?i)(?:bearer\s+\S+|(?:sk-|AKIA|ASIA)[a-z0-9_-]{12,}"
    r"|https?://\S+"
    r"|(?:password|secret|api[_ -]?key|(?:access[_ -]?)?token)\s*[:=]\s*\S+)"
)


def export_mode(
    corpus_bytes: bytes, suite: str, *, detailed: bool, synthetic: bool
) -> bool:
    """Require exact pinned corpus bytes for detailed synthetic exports."""
    recognized = hashlib.sha256(corpus_bytes).hexdigest() == _PINNED.get(suite)
    if detailed != synthetic or (detailed and not recognized):
        raise ValueError("Invalid evaluation export input")
    return recognized


def _text(key: str, value: str, recognized: bool) -> str | None:
    if key in {"case_id", "scenario_id"}:
        return (
            value if recognized and re.fullmatch(r"[ABCFMPX][0-9]{2}", value) else None
        )
    if key in _HASH_KEYS and re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", value):
        return value
    if key in {"started_at", "finished_at"}:
        if re.fullmatch(r"[0-9T:.+Z-]{10,40}", value):
            return value
    if key.endswith("_usd_per_1000") or key.endswith("_usd"):
        if re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,12})?", value):
            return value
    return None


def _detailed(
    value: object,
    key: str,
    recognized: bool,
    budget: list[int],
    depth: int,
) -> object:
    budget[0] -= 1 + (len(value) if isinstance(value, str) else 0)
    if budget[0] < 0 or depth > 32:
        return None
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        return value if abs(value) <= 10**15 else None
    if type(value) is float:
        return value if math.isfinite(value) and abs(value) <= 10**15 else None
    if isinstance(value, str):
        return _SECRET.sub("[redacted]", value[:4096])
    if isinstance(value, list):
        return [
            _detailed(item, key, recognized, budget, depth + 1) for item in value[:1000]
        ]
    if isinstance(value, dict):
        clean: dict[str, object] = {}
        for field, item in list(value.items())[:1000]:
            if not isinstance(field, str):
                continue
            folded = field.lower().replace("_", "")
            if folded in {"token", "tokens", "key"} or any(
                secret in folded
                for secret in (
                    "reasoning",
                    "thinking",
                    "chainofthought",
                    "secret",
                    "password",
                    "authorization",
                    "credential",
                    "apikey",
                    "accesstoken",
                    "refreshtoken",
                )
            ):
                continue
            safe_field = _SECRET.sub("[redacted]", field[:128])
            clean[safe_field] = _detailed(item, field, recognized, budget, depth + 1)
        return clean
    return None


def _numbers(names: str) -> dict[str, object]:
    return dict.fromkeys(names.split(), "number")


_USAGE: dict[str, object] = _numbers(
    "inputTokens outputTokens cacheReadInputTokens cacheWriteInputTokens "
    "input output cache_read cache_write"
)
_STATUSES = "passed failed unassessed not_applicable"
_RATIO: dict[str, object] = _numbers("passed total rate")
_TURN: dict[str, object] = {
    **dict.fromkeys("status reason".split(), "enum"),
    **_numbers(
        "elapsed_seconds provider_elapsed_seconds provider_calls "
        "attempts invalid_responses"
    ),
    **dict.fromkeys("capture_incomplete secret_leak protocol_valid".split(), "bool"),
    "usage": _USAGE,
}
_ASSESSMENT: dict[str, object] = {
    "status": "enum",
    "scope": "enum",
    "reason_code": "enum",
    **_numbers("numerator denominator"),
}
_CLAIM_COUNTS = " ".join(_CLAIMS)
_AGGREGATE: dict[str, object] = {
    "status_counts": _numbers(_STATUSES),
    **_numbers(
        "denominator pass_rate "
        + " ".join(sum_binary_metrics([]))
        + " "
        + " ".join(sum_claim_counts([]))
    ),
    "counts": _numbers(_CLAIM_COUNTS + " numerator denominator"),
    "direction": "enum",
}
_TOOL_METRICS = (
    "valid_calls expected_tool_selection expected_arguments unnecessary_calls"
)
_METRICS: dict[str, object] = {
    "assessments": dict.fromkeys(
        "tools plan outcome claims fixture".split(), _AGGREGATE
    ),
    "tool_metrics": dict.fromkeys(_TOOL_METRICS.split(), _AGGREGATE),
    "clarification_correctness": _AGGREGATE,
    "plan_checks": "aggregate_checks",
    "fixture_checks": "aggregate_checks",
    "known_failures": [
        {
            "case_id": "label",
            "repeat": "number",
            "assessment": "enum",
            "checks": ["check_name"],
        }
    ],
}
_TASKS: dict[str, object] = {
    "condition": "enum",
    "evidence_class": "enum",
    "execution": {
        "slot": _numbers("completed failed partial unassessed"),
        "observation": _numbers("completed failed partial unassessed"),
    },
    "quality": {
        "scope": "enum",
        **_numbers(
            _STATUSES + " all_applicable assessed_denominator conservative_rate "
            "assessed_only_rate coverage"
        ),
    },
}
_MANIFEST: dict[str, object] = {
    **dict.fromkeys(_HASH_KEYS, "hash"),
    **dict.fromkeys(
        (
            "version model_id profile region evidence_class "
            "suite_version catalog_version"
        ).split(),
        "enum",
    ),
    "model_config": {
        **_numbers("max_tokens max_output_tokens temperature"),
        "reasoning_effort": "enum",
        "store": "bool",
        "parallel_tool_calls": "bool",
    },
    "conditions": ["enum"],
    "selected_turn_count": "number",
    "selection": {"scenarios": [{"scenario_id": "label", "repeats": ["number"]}]},
    "rates": {
        "currency": "enum",
        **dict.fromkeys(
            (
                "input_usd_per_1000 output_usd_per_1000 "
                "cached_input_usd_per_1000 cache_write_usd_per_1000"
            ).split(),
            "usd",
        ),
    },
}
_SLOT: dict[str, object] = {
    "case_id": "label",
    "scenario_id": "label",
    **_numbers(
        "repeat turn elapsed_seconds provider_requests latency_ms unmatched_count"
    ),
    **dict.fromkeys(
        (
            "condition driver status reason_code profile reply_source gate apply_error"
        ).split(),
        "enum",
    ),
    "proposal": "bool",
    "facts_present": ["bool"],
    "usage": _USAGE,
    "verdict": {"ok": "bool", "reasons": ["enum"], "unmatched_count": "number"},
    "tools": [{"name": "enum", "outcome": "enum"}],
    "purchase_signals": {
        **_numbers("unoffered_tool_requests purchase_named_tool_requests"),
        **dict.fromkeys("observed reply_claim model_claim".split(), "bool"),
    },
    "observation": {
        **dict.fromkeys(
            (
                "status reason_code model_id evidence_class catalog_version condition"
            ).split(),
            "enum",
        ),
        "case_id": "label",
        "model_quality_applicable": "bool",
        "turns": [_TURN],
        **dict.fromkeys(_HASH_KEYS, "hash"),
    },
    "assessments": {
        name: {
            **_ASSESSMENT,
            **{tool: _ASSESSMENT for tool in _TOOL_METRICS.split()},
            **_numbers(_CLAIM_COUNTS),
            "checks": "checks",
        }
        for name in "tools plan outcome claims fixture".split()
    },
}
_SCENARIO: dict[str, object] = {
    "scenario_id": "label",
    **_numbers("turns turns_expected"),
    "repeats": ["number"],
    "passed": "bool",
    "failing_turns": ["turn_label"],
}
_COST: dict[str, object] = {
    **_numbers(
        "turns_priced turns_unpriced input_tokens output_tokens cache_read_tokens "
        "cache_unknown_turns provider_requests"
    ),
    "coverage_complete": "bool",
    **dict.fromkeys("per_turn_usd total_usd usd_per_all_checks_pass".split(), "usd"),
}
_REPORT: dict[str, object] = {
    **dict.fromkeys("version mode metrics_status".split(), "enum"),
    **_numbers("repeats slot_count primary_slot_count total_slot_count"),
    "revision": "hash",
    "started_at": "stamp",
    "finished_at": "stamp",
    "manifest": _MANIFEST,
    "manifest_hash": "hash",
    "slots": [_SLOT],
    "baseline_slots": [_SLOT],
    "summary": {
        "total_slots": "number",
        "groups": [
            {
                "condition": "enum",
                "evidence_class": "enum",
                "slot_count": "number",
                "metrics": _METRICS,
                "tasks": _TASKS,
            }
        ],
    },
    "counts": _numbers("scenarios repeats turns_expected turns_recorded"),
    "checks": dict.fromkeys("tools outcome gold".split(), _RATIO),
    "scenario_pass": {**_RATIO, "all_checks": _RATIO, "with_gold": _RATIO},
    "grounding": {
        **_numbers("prose_attempts grounded_replies grounded_rate unsupported_numbers"),
        "fallbacks": _numbers(
            "proposal tool_failed not_final planner no_tools clarification refusal "
            "incomplete limit planned_terminal discovery_terminal guardrail "
            "saved_plan_read "
            "swap_not_saved"
        ),
    },
    "purchase_attempts": _numbers(
        "turns_observed turns_unobserved turns_with_attempt unoffered_tool_requests "
        "purchase_named_tool_requests reply_claims model_claims"
    ),
    "purchase_refusals": _numbers("turns refused rate tool_requests"),
    "latency_ms": _numbers("p50 p95"),
    "cost": _COST,
    "targets": [
        {"name": "enum", "target": "target", "value": "metric", "status": "enum"}
    ],
    "scenarios": [_SCENARIO],
}


def _project(value: object, shape: object, recognized: bool) -> object:
    if isinstance(shape, str) and shape in ("checks", "aggregate_checks"):
        if not isinstance(value, dict):
            return None
        checks: dict[str, object] = {}
        for key, item in list(value.items())[:1000]:
            if not isinstance(key, str):
                continue
            try:
                validate_checks({key: True})
            except ValueError:
                continue
            checks[key] = _project(
                item, "bool" if shape == "checks" else _AGGREGATE, recognized
            )
        return checks
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            return None
        return {
            key: _project(value[key], child, recognized)
            for key, child in shape.items()
            if key in value
        }
    if isinstance(shape, list):
        if not isinstance(value, (list, tuple)):
            return None
        return [_project(item, shape[0], recognized) for item in value[:1000]]
    if value is None:
        return None
    if shape == "bool":
        return value if type(value) is bool else None
    if shape in ("number", "metric") and type(value) in (int, float):
        number = cast(int | float, value)
        return number if 0 <= number <= 10**15 and math.isfinite(number) else None
    if shape == "number":
        return None
    if not isinstance(value, str):
        return None
    if shape == "label":
        return _text("case_id", value, recognized)
    if shape == "hash":
        return value if re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", value) else None
    if shape == "stamp":
        return _text("started_at", value, recognized)
    if shape in ("usd", "metric"):
        return _text("total_usd", value, recognized)
    if shape == "turn_label":
        return (
            value if recognized and re.fullmatch(r"[1-3]\.[1-9][0-9]?", value) else None
        )
    if shape == "target":
        return (
            value if value in {"0", ">= 0.99", "< 5000", "< 12000", "< 0.006"} else None
        )
    if shape == "check_name":
        if value in _TOOL_METRICS.split():
            return value
        try:
            validate_checks({value: True})
        except ValueError:
            return None
        return value
    return value if value in _VALUES else None


def export_record(
    record: dict[str, object],
    *,
    recognized: bool,
    detailed: bool = False,
    synthetic: bool = False,
    corpus_bytes: bytes | None = None,
    suite: str = "",
) -> dict[str, object]:
    """Export typed public metrics or verified synthetic details."""
    if detailed or synthetic:
        if corpus_bytes is None:
            raise ValueError("Invalid evaluation export input")
        export_mode(corpus_bytes, suite, detailed=detailed, synthetic=synthetic)
    if detailed:
        clean = _detailed(record, "", True, [1_000_000], 0)
    else:
        shape = (
            _REPORT
            if any(key in record for key in ("slots", "counts", "summary"))
            else _SLOT
        )
        clean = _project(record, shape, recognized)
    return clean if isinstance(clean, dict) else {}


def render_export_markdown(report: dict[str, object]) -> str:
    """Render only the public report projection."""
    scenarios = report.get("scenarios")
    if (
        report.get("version") == "conversation-report-v1"
        and isinstance(scenarios, list)
        and all(
            isinstance(row, dict) and isinstance(row.get("scenario_id"), str)
            for row in scenarios
        )
    ):
        from app.evaluation_conversation_score import render_markdown

        return render_markdown(report)
    lines = [
        "# Evaluation report",
        "",
        "Deterministic fixture, reference, and fake evidence does not establish "
        "real-model quality.",
        "",
    ]

    def section(value: object, label: str, depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(value, dict):
            lines.extend((f"{'#' * min(depth + 2, 6)} {label}", ""))
            scalar = [
                (key, item)
                for key, item in value.items()
                if not isinstance(item, (dict, list))
            ]
            if scalar:
                lines.extend(("| Metric | Value |", "| --- | --- |"))
                lines.extend(f"| {key} | {item} |" for key, item in scalar)
                lines.append("")
            for key, item in value.items():
                if key in {"slots", "baseline_slots"}:
                    continue
                if isinstance(item, (dict, list)):
                    section(item, key.replace("_", " ").capitalize(), depth + 1)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                section(item, f"{label} {index + 1}", depth + 1)

    section(report, "Metrics")
    return "\n".join(lines) + "\n"
