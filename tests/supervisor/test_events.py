import json

import pytest

from dev_supervisor.events import Events
from dev_supervisor.usage import CODEX_PROVENANCE, GROK_PROVENANCE


def test_tool_failure_is_not_provider_failure() -> None:
    state = Events()
    state.feed('{"type":"item.started","item":{"type":"command_execution","id":"a"}}')
    assert state.active_tools == {"a"}
    state.feed(
        '{"type":"item.completed","item":{"type":"command_execution","id":"a","aggregated_output":"quota_exceeded","exit_code":1}}'
    )
    assert not state.active_tools
    assert state.outcome(1) == "task_failed"


@pytest.mark.parametrize(
    "code, expected",
    [
        ("insufficient_quota", "quota"),
        ("rate_limit_exceeded", "rate_limit"),
        ("FS_PERMISSION_DENIED", "permission"),
        ("unexpected", "unknown"),
    ],
)
def test_provider_codes(code: str, expected: str) -> None:
    state = Events()
    state.feed('{"type":"error","code":"' + code + '"}')
    assert state.failure == expected


def test_permission_and_untrusted_text() -> None:
    state = Events()
    state.feed("quota_exceeded")
    state.feed(
        '{"type":"item.completed","item":{"type":"agent_message","text":"rate_limit_exceeded"}}'
    )
    assert state.failure == "unknown"
    state.feed('{"type":"permission_request"}')
    assert state.outcome(1) == "permission"


def test_observed_grok_tool_lifecycle() -> None:
    state = Events()
    state.feed(
        '{"type":"tool_call","toolCallId":"call-1","status":"pending","toolName":"read_file"}'
    )
    state.feed('{"type":"tool_call_update","toolCallId":"call-1","status":null}')
    assert state.active_tools == {"call-1"}
    state.feed('{"type":"tool_call_update","toolCallId":"call-1","status":"completed"}')
    assert not state.active_tools
    state.feed('{"type":"end","stopReason":"end_turn"}')
    assert state.outcome(0) == "completed"


def test_turn_cap_and_unknown_error_are_not_success() -> None:
    state = Events()
    state.feed('{"type":"end","stopReason":"max_turns"}')
    assert state.outcome(0) == "task_failed"
    state.feed('{"type":"error","message":"unknown failure"}')
    assert state.outcome(0) == "task_failed"


def test_success_after_internal_retry_clears_failure() -> None:
    state = Events()
    state.feed('{"type":"error","code":"rate_limit_exceeded"}')
    state.feed('{"type":"turn.completed"}')
    assert state.outcome(0) == "completed"


def test_completed_question_does_not_wait() -> None:
    state = Events()
    state.feed(
        '{"type":"tool_call_update","toolCallId":"answered","toolName":"ask_user_question","status":"completed"}'
    )
    state.feed('{"type":"end","stopReason":"end_turn"}')
    assert state.outcome(0) == "completed"
    assert not state.active_tools
    assert not state.waiting


def test_pending_question_waits_until_cleared() -> None:
    state = Events()
    state.feed(
        '{"type":"tool_call","toolCallId":"q1","toolName":"ask_user_question","status":"pending"}'
    )
    assert state.outcome(0) == "permission"
    state.feed(
        '{"type":"tool_call_update","toolCallId":"q1","toolName":"ask_user_question","status":"failed"}'
    )
    state.feed('{"type":"turn.completed"}')
    assert state.outcome(0) == "completed"


def test_embedded_grok_permission_code() -> None:
    state = Events()
    state.feed(
        json.dumps(
            {
                "type": "error",
                "message": 'Could not create session: {"code": "FS_PERMISSION_DENIED"}',
            }
        )
    )
    assert state.outcome(1) == "permission"


def test_sums_two_turn_completed_usages() -> None:
    state = Events()
    state.feed(
        '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":1,"output_tokens":5,"reasoning_output_tokens":2}}'
    )
    state.feed(
        '{"type":"turn.completed","usage":{"input_tokens":4,"cached_input_tokens":1,"output_tokens":3,"reasoning_output_tokens":2}}'
    )
    assert state.tokens == {
        "input_tokens": 14,
        "cached_tokens": 2,
        "output_tokens": 8,
        "reasoning_tokens": 4,
    }
    assert state.provenance == CODEX_PROVENANCE


def test_feed_grok_end_records_tokens() -> None:
    state = Events()
    state.feed(
        json.dumps(
            {
                "type": "end",
                "stopReason": "end_turn",
                "usage": {
                    "input_tokens": 18411,
                    "cache_read_input_tokens": 128,
                    "cache_creation_input_tokens": 0,
                    "output_tokens": 22,
                    "reasoning_tokens": 21,
                    "total_tokens": 18561,
                },
                "num_turns": 1,
            }
        )
    )
    assert state.tokens == {
        "input_tokens": 18539,
        "cached_tokens": 128,
        "output_tokens": 22,
        "reasoning_tokens": 21,
    }
    assert state.provenance == GROK_PROVENANCE


def test_feed_grok_usage_event_adds_nothing() -> None:
    state = Events()
    state.feed(
        '{"type":"usage","input_tokens":99,"cache_read_input_tokens":1,'
        '"output_tokens":4,"reasoning_tokens":2}'
    )
    assert state.tokens is None
    assert state.provenance == "none"
