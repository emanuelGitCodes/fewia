from __future__ import annotations

import math
from typing import cast

import pytest

from app.evaluation_telemetry import summarize_telemetry

MODEL_ID = "eval-fake-v1"
EVIDENCE = "deterministic_fake_provider"


def _completed_turn(
    elapsed: object,
    input_tokens: object,
    output_tokens: object,
    *,
    missing_usage: bool = False,
) -> dict[str, object]:
    result: dict[str, object] = {
        "model_turns": 1,
        "planner_revisions": 0,
        "usage": None,
    }
    if not missing_usage:
        result["usage"] = {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
        }
    return {
        "status": "completed",
        "elapsed_seconds": elapsed,
        "result": result,
    }


def _failed_turn(elapsed: object) -> dict[str, object]:
    return {
        "status": "failed",
        "reason": "provider_unavailable",
        "elapsed_seconds": elapsed,
    }


def _observation(
    status: str,
    turns: object,
) -> dict[str, object]:
    return {
        "status": status,
        "turns": turns,
        "model_id": MODEL_ID,
        "evidence_class": EVIDENCE,
    }


def _observed(observation: object) -> dict[str, object]:
    return {"observation": observation}


def _fixture() -> dict[str, object]:
    return {
        "case_id": "B01",
        "status": "scored",
        "report": {"checks": {"accepted": True}},
    }


def _summary(slots: list[dict[str, object]]) -> dict[str, object]:
    return summarize_telemetry(slots)


def test_empty_slots_report_zero_counts_and_null_percentiles() -> None:
    result = _summary([])
    assert result["total_slots"] == 0
    assert result["observed_slots"] == 0
    assert result["completed_observations"] == 0
    assert result["failed_or_partial_observations"] == 0
    assert result["latency_sample_count"] == 0
    assert result["p50_latency_seconds"] is None
    assert result["p95_latency_seconds"] is None
    assert result["percentile_method"] == "nearest-rank"
    assert result["known_usage_slots"] == 0
    assert result["unknown_usage_slots"] == 0
    assert result["known_input_tokens"] == 0
    assert result["known_output_tokens"] == 0
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert "quality" in str(result["quality_note"])
    assert "Fixtures" in str(result["token_note"])
    assert "known_usage_slots is 0" in str(result["token_note"])


def test_fixture_only_slots_keep_known_totals_zero_and_overall_null() -> None:
    result = _summary([_fixture(), _fixture()])
    assert result["total_slots"] == 2
    assert result["observed_slots"] == 0
    assert result["known_usage_slots"] == 0
    assert result["unknown_usage_slots"] == 0
    assert result["known_input_tokens"] == 0
    assert result["known_output_tokens"] == 0
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["latency_sample_count"] == 0


def test_mixed_fixture_observed_failure_and_partial() -> None:
    slots = [
        _fixture(),
        _observed(
            _observation(
                "completed",
                [_completed_turn(1.0, 10, 4), _completed_turn(3.0, 6, 2)],
            )
        ),
        _observed(_observation("failed", [_failed_turn(2.0)])),
        _observed(
            _observation(
                "partial",
                [_completed_turn(0.5, 8, 1), _failed_turn(0.5)],
            )
        ),
    ]
    result = _summary(slots)
    assert result["total_slots"] == 4
    assert result["observed_slots"] == 3
    assert result["completed_observations"] == 1
    assert result["failed_or_partial_observations"] == 2
    assert result["latency_sample_count"] == 3
    assert result["p50_latency_seconds"] == 2.0
    assert result["p95_latency_seconds"] == 4.0
    assert result["known_usage_slots"] == 1
    assert result["unknown_usage_slots"] == 2
    assert result["known_input_tokens"] == 16
    assert result["known_output_tokens"] == 6
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_missing_usage_on_one_turn_keeps_slot_unknown() -> None:
    known = _observed(_observation("completed", [_completed_turn(1.0, 5, 7)]))
    missing = _observed(
        _observation(
            "completed",
            [
                _completed_turn(1.0, 9, 3),
                _completed_turn(1.0, 0, 0, missing_usage=True),
            ],
        )
    )
    result = _summary([known, missing])
    assert result["observed_slots"] == 2
    assert result["completed_observations"] == 2
    assert result["known_usage_slots"] == 1
    assert result["unknown_usage_slots"] == 1
    assert result["known_input_tokens"] == 5
    assert result["known_output_tokens"] == 7
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["latency_sample_count"] == 2


def test_zero_actual_usage_is_known() -> None:
    slots = [
        _observed(_observation("completed", [_completed_turn(0.0, 0, 0)])),
    ]
    result = _summary(slots)
    assert result["known_usage_slots"] == 1
    assert result["unknown_usage_slots"] == 0
    assert result["known_input_tokens"] == 0
    assert result["known_output_tokens"] == 0
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["latency_sample_count"] == 1
    assert result["p50_latency_seconds"] == 0.0
    assert result["p95_latency_seconds"] == 0.0


def test_bool_negative_and_nonfinite_elapsed_are_unknown_latency() -> None:
    slots = [
        _observed(_observation("completed", [_completed_turn(True, 1, 1)])),
        _observed(_observation("completed", [_completed_turn(-1.0, 1, 1)])),
        _observed(_observation("completed", [_completed_turn(math.nan, 1, 1)])),
        _observed(_observation("completed", [_completed_turn(math.inf, 1, 1)])),
        _observed(_observation("completed", [_completed_turn(10**400, 1, 1)])),
        _observed(_observation("completed", [_completed_turn(2.0, 4, 5)])),
    ]
    result = _summary(slots)
    assert result["latency_sample_count"] == 1
    assert result["p50_latency_seconds"] == 2.0
    assert result["p95_latency_seconds"] == 2.0
    assert result["known_usage_slots"] == 6
    assert result["input_tokens"] == 9
    assert result["output_tokens"] == 10


def test_bool_and_negative_usage_are_unknown() -> None:
    slots = [
        _observed(_observation("completed", [_completed_turn(1.0, True, 1)])),
        _observed(_observation("completed", [_completed_turn(1.0, 1, True)])),
        _observed(_observation("completed", [_completed_turn(1.0, -1, 0)])),
        _observed(_observation("completed", [_completed_turn(1.0, 0, -2)])),
        _observed(_observation("completed", [_completed_turn(1.0, 3, 4)])),
    ]
    result = _summary(slots)
    assert result["known_usage_slots"] == 1
    assert result["unknown_usage_slots"] == 4
    assert result["known_input_tokens"] == 3
    assert result["known_output_tokens"] == 4
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_nearest_rank_uses_upper_tail_for_p95() -> None:
    turns = [[_completed_turn(float(index), 0, 0)] for index in range(1, 21)]
    slots = [_observed(_observation("completed", turn)) for turn in turns]
    result = _summary(slots)
    assert result["latency_sample_count"] == 20
    assert result["p50_latency_seconds"] == 10.0
    assert result["p95_latency_seconds"] == 19.0
    assert result["percentile_method"] == "nearest-rank"


def test_order_does_not_change_summary() -> None:
    slots = [
        _fixture(),
        _observed(_observation("completed", [_completed_turn(4.0, 2, 3)])),
        _observed(_observation("failed", [_failed_turn(1.0)])),
        _observed(_observation("completed", [_completed_turn(8.0, 11, 13)])),
        _observed(_observation("partial", [_failed_turn(2.0)])),
    ]
    forward = _summary(slots)
    backward = _summary(list(reversed(slots)))
    assert forward == backward


def test_token_totals_keep_integer_precision() -> None:
    token = 2**53 + 1
    slots = [
        _observed(_observation("completed", [_completed_turn(1.0, token, token)])),
        _observed(_observation("completed", [_completed_turn(1.0, token, 0)])),
    ]
    result = _summary(slots)
    assert type(result["known_input_tokens"]) is int
    assert type(result["known_output_tokens"]) is int
    assert result["known_input_tokens"] == token * 2
    assert result["known_output_tokens"] == token
    assert result["input_tokens"] == token * 2
    assert result["output_tokens"] == token


def test_malformed_turns_and_non_dict_observation_are_unknown() -> None:
    slots = [
        _observed(_observation("completed", "not-turns")),
        _observed(_observation("completed", [])),
        _observed("not-a-map"),
        _observed(_observation("unassessed", [_completed_turn(1.0, 1, 1)])),
        {"report": {"checks": {}}},
    ]
    result = _summary(slots)
    assert result["total_slots"] == 5
    assert result["observed_slots"] == 4
    assert result["completed_observations"] == 2
    assert result["failed_or_partial_observations"] == 0
    assert result["known_usage_slots"] == 0
    assert result["unknown_usage_slots"] == 4
    assert result["latency_sample_count"] == 1
    assert result["input_tokens"] is None


def test_non_list_slots_raise_static_value_error() -> None:
    with pytest.raises(ValueError, match="^slots is invalid$"):
        summarize_telemetry(cast(list[dict[str, object]], {"bad": True}))


def test_non_dict_slot_counts_in_total_only() -> None:
    slots = cast(list[dict[str, object]], [1, _fixture()])
    result = _summary(slots)
    assert result["total_slots"] == 2
    assert result["observed_slots"] == 0
    assert result["known_usage_slots"] == 0
    assert result["unknown_usage_slots"] == 0
    assert result["known_input_tokens"] == 0
    assert result["known_output_tokens"] == 0
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_summary_does_not_echo_raw_slot_payloads() -> None:
    marker = "do-not-echo-raw-input"
    slot = _observed(_observation("completed", [_completed_turn(1.0, 1, 1)]))
    slot["prompt"] = marker
    result = _summary([slot])
    assert marker not in str(result)


def test_partial_observation_with_only_completed_turns_keeps_overall_null() -> None:
    result = _summary(
        [_observed(_observation("partial", [_completed_turn(1.0, 8, 2)]))]
    )
    assert result["completed_observations"] == 0
    assert result["failed_or_partial_observations"] == 1
    assert result["known_usage_slots"] == 0
    assert result["unknown_usage_slots"] == 1
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["latency_sample_count"] == 1
    assert result["p50_latency_seconds"] == 1.0


def test_unknown_observation_status_with_only_completed_turns_keeps_overall_null() -> (
    None
):
    result = _summary(
        [_observed(_observation("running", [_completed_turn(2.0, 5, 3)]))]
    )
    assert result["completed_observations"] == 0
    assert result["known_usage_slots"] == 0
    assert result["unknown_usage_slots"] == 1
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["latency_sample_count"] == 1


def test_valid_completed_zero_usage_stays_overall_zero() -> None:
    result = _summary(
        [_observed(_observation("completed", [_completed_turn(0.0, 0, 0)]))]
    )
    assert result["known_usage_slots"] == 1
    assert result["unknown_usage_slots"] == 0
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


def test_mixed_valid_and_invalid_elapsed_in_same_slot_is_unknown_latency() -> None:
    result = _summary(
        [
            _observed(
                _observation(
                    "completed",
                    [
                        _completed_turn(1.0, 2, 3),
                        _completed_turn(-1.0, 4, 5),
                    ],
                )
            )
        ]
    )
    assert result["latency_sample_count"] == 0
    assert result["p50_latency_seconds"] is None
    assert result["p95_latency_seconds"] is None
    assert result["known_usage_slots"] == 1
    assert result["unknown_usage_slots"] == 0
    assert result["input_tokens"] == 6
    assert result["output_tokens"] == 8
