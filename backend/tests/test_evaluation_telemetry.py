import json
from copy import deepcopy
from decimal import Decimal
from typing import cast

import pytest

from app.evaluation_telemetry import summarize_telemetry


def _turn(
    usage: object,
    *,
    calls: object = 1,
    elapsed: object = 2.0,
    provider_elapsed: object = 0.5,
    status: str = "completed",
) -> dict[str, object]:
    return {
        "usage": usage,
        "provider_calls": calls,
        "elapsed_seconds": elapsed,
        "provider_elapsed_seconds": provider_elapsed,
        "status": status,
        "result": {"usage": {"inputTokens": 999, "outputTokens": 999}},
    }


def _slot(
    turns: object,
    *,
    elapsed: object = 3.0,
    condition: str = "tool_enabled",
    evidence: str = "live_bedrock",
    status: str = "completed",
) -> dict[str, object]:
    return {
        "case_id": "A01",
        "repeat": 1,
        "condition": condition,
        "elapsed_seconds": elapsed,
        "observation": {
            "case_id": "A01",
            "condition": condition,
            "evidence_class": evidence,
            "model_id": "pinned-model",
            "status": status,
            "turns": turns,
        },
    }


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _groups(report: dict[str, object]) -> list[dict[str, object]]:
    groups = report["groups"]
    assert isinstance(groups, list)
    return [_mapping(group) for group in groups]


def _group(slots: list[dict[str, object]]) -> dict[str, object]:
    groups = _groups(summarize_telemetry(slots))
    assert len(groups) == 1
    return groups[0]


def test_usage_comes_from_provider_capture_and_keeps_exact_integers() -> None:
    large = 2**64 + 1
    group = _group(
        [
            _slot(
                [
                    _turn({"inputTokens": large, "outputTokens": 2}),
                    _turn({"inputTokens": 3, "outputTokens": 4}, calls=2),
                ]
            )
        ]
    )
    assert group["input_tokens"] == large + 3
    assert type(group["input_tokens"]) is int
    assert group["output_tokens"] == 6
    assert group["known_input_tokens"] == large + 3
    assert group["known_usage_turns"] == 2
    assert group["unknown_usage_turns"] == 0
    assert group["known_usage_slots"] == 1
    assert _mapping(group["provider_calls"])["total"] == 3


def test_partial_usage_keeps_each_known_component_as_a_lower_bound() -> None:
    group = _group(
        [
            _slot([_turn({"inputTokens": 8, "outputTokens": 3})]),
            _slot(
                [
                    _turn({"inputTokens": 4}),
                    _turn(None, status="failed"),
                ],
                status="partial",
            ),
        ]
    )
    assert group["input_tokens"] is None
    assert group["output_tokens"] is None
    assert group["known_input_tokens"] == 12
    assert group["known_output_tokens"] == 3
    assert group["known_usage_turns"] == 1
    assert group["unknown_usage_turns"] == 2
    assert group["known_usage_slots"] == 1
    assert group["unknown_usage_slots"] == 1


def test_missing_usage_does_not_fall_back_to_public_result() -> None:
    turn = _turn(None)
    del turn["usage"]
    group = _group([_slot([turn])])
    assert group["input_tokens"] is None
    assert group["known_input_tokens"] is None
    assert group["known_output_tokens"] is None
    assert group["unknown_usage_turns"] == 1
    assert group["unknown_usage_slots"] == 1


def test_failed_attempts_retain_calls_and_measured_elapsed() -> None:
    group = _group(
        [
            _slot(
                [_turn(None, calls=2, provider_elapsed=1.25, status="failed")],
                elapsed=4.0,
                status="failed",
            ),
            _slot([_turn({"inputTokens": 1, "outputTokens": 2})]),
        ]
    )
    assert _mapping(group["provider_calls"])["total"] == 3
    assert _mapping(group["provider_elapsed_seconds"])["total"] == 1.75
    assert _mapping(group["slot_elapsed_seconds"])["sample_count"] == 2
    assert group["observation_counts"] == {
        "completed": 1,
        "failed": 1,
        "partial": 0,
        "unknown": 0,
    }
    assert group["input_tokens"] is None


def test_failed_status_does_not_discard_known_usage() -> None:
    group = _group(
        [_slot([_turn({"inputTokens": 7, "outputTokens": 2})], status="failed")]
    )
    assert group["input_tokens"] == 7
    assert group["output_tokens"] == 2


@pytest.mark.parametrize(
    "invalid", [True, False, -1, -0.5, 1.0, float("nan"), Decimal("2"), "2", None]
)
def test_token_and_call_counts_require_exact_nonnegative_integers(
    invalid: object,
) -> None:
    group = _group(
        [_slot([_turn({"inputTokens": invalid, "outputTokens": 5}, calls=invalid)])]
    )
    assert group["input_tokens"] is None
    assert group["output_tokens"] is None
    assert group["known_input_tokens"] is None
    assert group["known_output_tokens"] == 5
    calls = _mapping(group["provider_calls"])
    assert calls["total"] is None
    assert calls["known_total"] is None
    assert calls["unknown_count"] == 1


@pytest.mark.parametrize(
    "invalid",
    [True, False, -1, -0.5, float("nan"), float("inf"), Decimal("0"), "0", None],
)
def test_latency_requires_finite_nonnegative_numbers(invalid: object) -> None:
    group = _group(
        [
            _slot(
                [_turn(None, elapsed=invalid, provider_elapsed=invalid)],
                elapsed=invalid,
            )
        ]
    )
    for key in (
        "slot_elapsed_seconds",
        "turn_elapsed_seconds",
        "provider_elapsed_seconds",
    ):
        metric = _mapping(group[key])
        assert metric["total"] is None
        assert metric["known_total"] is None
        assert metric["sample_count"] == 0
        assert metric["unknown_count"] == 1
    slot_latency = _mapping(group["slot_elapsed_seconds"])
    assert slot_latency["p50"] is None
    assert slot_latency["p95"] is None


def test_nearest_rank_uses_only_measured_slot_samples() -> None:
    slots = [_slot([], elapsed=value) for value in range(20, 0, -1)]
    slots.append(_slot([_turn(None, elapsed=100)], elapsed=None))
    metric = _mapping(_group(slots)["slot_elapsed_seconds"])
    assert metric["sample_count"] == 20
    assert metric["unknown_count"] == 1
    assert metric["p50"] == 10.0
    assert metric["p95"] == 19.0
    assert metric["percentile_method"] == "nearest-rank"
    assert metric["known_total"] == 210.0
    assert metric["total"] is None


def test_slot_turn_and_provider_latencies_do_not_double_count() -> None:
    group = _group(
        [
            _slot(
                [
                    _turn(None, elapsed=3, provider_elapsed=1),
                    _turn(None, elapsed=4, provider_elapsed=2),
                ],
                elapsed=12,
            )
        ]
    )
    assert _mapping(group["slot_elapsed_seconds"])["total"] == 12.0
    assert _mapping(group["slot_elapsed_seconds"])["p50"] == 12.0
    assert _mapping(group["turn_elapsed_seconds"])["total"] == 7.0
    assert _mapping(group["provider_elapsed_seconds"])["total"] == 3.0


def test_conditions_and_evidence_classes_stay_distinct() -> None:
    slots = [
        _slot([_turn(None)], condition="tool_enabled"),
        _slot([_turn(None)], condition="no_tool"),
        _slot([_turn(None, calls=0)], condition="deterministic", evidence="fixture"),
        _slot([_turn(None, calls=5)], evidence="controlled_fixture"),
    ]
    report = summarize_telemetry(slots)
    groups = _groups(report)
    assert report["total_slots"] == 4
    assert len(groups) == 4
    assert {(group["condition"], group["evidence_class"]) for group in groups} == {
        ("tool_enabled", "live_bedrock"),
        ("no_tool", "live_bedrock"),
        ("deterministic", "fixture"),
        ("tool_enabled", "controlled_fixture"),
    }
    for group in groups:
        assert group["total_slots"] == 1
        assert "provider capture" in str(group["scope"])


def test_measured_zero_is_known_but_missing_data_stays_unknown() -> None:
    report = summarize_telemetry(
        [
            _slot(
                [
                    _turn(
                        {"inputTokens": 0, "outputTokens": 0},
                        calls=0,
                        elapsed=0,
                        provider_elapsed=0,
                    )
                ],
                elapsed=0,
            )
        ]
    )
    group = _groups(report)[0]
    assert group["input_tokens"] == 0
    assert group["output_tokens"] == 0
    assert group["unknown_usage_turns"] == 0
    for key in (
        "slot_elapsed_seconds",
        "turn_elapsed_seconds",
        "provider_elapsed_seconds",
        "provider_calls",
    ):
        metric = _mapping(group[key])
        assert metric["total"] == 0
        assert metric["sample_count"] == 1
        assert metric["unknown_count"] == 0
    assert report["billed_cost_estimate"] is None
    missing = _group([_slot([])])
    assert missing["input_tokens"] is None
    assert missing["unknown_usage_slots"] == 1
    assert _mapping(missing["provider_calls"])["total"] is None


def test_missing_slot_observation_blocks_overall_totals() -> None:
    absent: dict[str, object] = {"condition": "tool_enabled"}
    known = _slot([_turn({"inputTokens": 1, "outputTokens": 2})], evidence="unknown")
    group = _group([known, absent])
    assert group["total_slots"] == 2
    assert group["observed_slots"] == 1
    assert group["unknown_usage_slots"] == 1
    assert group["known_input_tokens"] == 1
    assert group["input_tokens"] is None
    calls = _mapping(group["provider_calls"])
    assert calls["known_total"] == 1
    assert calls["total"] is None
    assert calls["unknown_slot_count"] == 1


def test_rows_report_case_repeat_model_and_sanitized_metrics() -> None:
    turn = _turn({"inputTokens": 2, "outputTokens": 1})
    turn["result"] = {"answer": "SYNTHETIC_ANSWER_MARKER"}
    turn["messages"] = ["SYNTHETIC_MESSAGE_MARKER"]
    turn["reason"] = "SYNTHETIC_ERROR_MARKER"
    slot = _slot([turn], status="partial")
    slot["repeat"] = 3
    slot["credentials"] = "SYNTHETIC_CREDENTIAL_MARKER"
    report = summarize_telemetry([slot])
    rows = _groups(report)[0]["slots"]
    assert isinstance(rows, list)
    row = _mapping(rows[0])
    assert row["case_id"] == "A01"
    assert row["repeat"] == 3
    assert row["model_id"] == "pinned-model"
    assert row["status"] == "partial"
    assert row["input_tokens"] == 2
    assert _mapping(row["provider_calls"])["total"] == 1
    encoded = json.dumps(report, allow_nan=False)
    assert "SYNTHETIC_" not in encoded
    assert "quality" not in encoded
    assert "pass" not in encoded


def test_inputs_remain_unchanged_and_empty_input_has_no_billed_estimate() -> None:
    slots = [_slot([_turn({"inputTokens": 1, "outputTokens": 2})])]
    before = deepcopy(slots)
    summarize_telemetry(slots)
    assert slots == before
    assert summarize_telemetry([]) == {
        "total_slots": 0,
        "groups": [],
        "billed_cost_estimate": None,
    }


def test_invalid_turns_and_missing_provider_counts_remain_unknown() -> None:
    turn = _turn({"inputTokens": 4, "outputTokens": 5})
    del turn["provider_calls"]
    group = _group([_slot([turn, None])])
    assert group["unknown_usage_turns"] == 1
    assert group["known_input_tokens"] == 4
    assert group["input_tokens"] is None
    assert _mapping(group["provider_calls"])["unknown_count"] == 2
    assert _mapping(group["turn_elapsed_seconds"])["total"] is None
    assert _mapping(group["turn_elapsed_seconds"])["known_total"] == 2.0


def test_huge_latency_values_do_not_produce_nonfinite_report_numbers() -> None:
    group = _group([_slot([], elapsed=10**1000)])
    assert _mapping(group["slot_elapsed_seconds"])["sample_count"] == 0
    slots = [_slot([], elapsed=1e308), _slot([], elapsed=1e308)]
    group = _group(slots)
    metric = _mapping(group["slot_elapsed_seconds"])
    assert metric["sample_count"] == 2
    assert metric["total"] is None
    assert metric["p95"] == 1e308
    json.dumps(group, allow_nan=False)
