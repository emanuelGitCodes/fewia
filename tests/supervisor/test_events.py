import json

import pytest

from dev_supervisor.events import Events
from dev_supervisor.usage import CLAUDE_PROVENANCE, CODEX_PROVENANCE, GROK_PROVENANCE

CLAUDE_SUCCESS = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": 1,
        "result": "OK",
        "usage": {
            "input_tokens": 2,
            "cache_creation_input_tokens": 4404,
            "cache_read_input_tokens": 544,
            "output_tokens": 4,
            "output_tokens_details": {"thinking_tokens": 0},
        },
        "permission_denials": [],
    }
)


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


def test_claude_success_records_tokens_and_provenance() -> None:
    state = Events()
    state.feed(CLAUDE_SUCCESS)
    assert state.complete
    assert state.outcome(0) == "completed"
    assert state.tokens == {
        "input_tokens": 4950,
        "cached_tokens": 544,
        "output_tokens": 4,
        "reasoning_tokens": 0,
    }
    assert state.provenance == CLAUDE_PROVENANCE


def test_claude_max_turns_is_task_failure() -> None:
    state = Events()
    state.feed(
        '{"type":"result","subtype":"error_max_turns","is_error":true,"num_turns":30}'
    )
    assert state.saw_error
    assert not state.complete
    assert state.outcome(0) == "task_failed"
    assert state.outcome(1) == "task_failed"


def test_claude_error_result_with_success_subtype_is_failure() -> None:
    state = Events()
    state.feed('{"type":"result","subtype":"success","is_error":true}')
    assert state.outcome(0) == "task_failed"


def test_claude_retry_then_error_result_reports_rate_limit() -> None:
    state = Events()
    state.feed(
        '{"type":"system","subtype":"api_retry","error":"rate_limit","attempt":1}'
    )
    assert state.saw_error
    state.feed('{"type":"result","subtype":"error_during_execution","is_error":true}')
    assert state.outcome(1) == "rate_limit"


def test_claude_retry_then_success_completes() -> None:
    state = Events()
    state.feed(
        '{"type":"system","subtype":"api_retry","error":"overloaded","attempt":1}'
    )
    assert state.failure == "unavailable"
    state.feed(CLAUDE_SUCCESS)
    assert state.failure == "unknown"
    assert not state.saw_error
    assert state.outcome(0) == "completed"


@pytest.mark.parametrize(
    "code, expected",
    [
        ("rate_limit", "rate_limit"),
        ("overloaded", "unavailable"),
        ("server_error", "unavailable"),
        ("model_not_found", "unavailable"),
        ("authentication_failed", "unavailable"),
        ("oauth_org_not_allowed", "unavailable"),
        ("billing_error", "quota"),
        ("account_on_hold", "quota"),
        ("something_new", "unknown"),
    ],
)
def test_claude_retry_codes(code: str, expected: str) -> None:
    state = Events()
    state.feed(json.dumps({"type": "system", "subtype": "api_retry", "error": code}))
    assert state.failure == expected
    assert state.saw_error


def test_claude_system_events_other_than_retry_are_ignored() -> None:
    state = Events()
    state.feed('{"type":"system","subtype":"init","error":"rate_limit"}')
    assert state.failure == "unknown"
    assert not state.saw_error


def test_claude_tool_lifecycle() -> None:
    state = Events()
    state.feed(
        '{"type":"assistant","message":{"content":[{"type":"text","text":"hi"},'
        '{"type":"tool_use","id":"toolu_1","name":"Edit","input":{}},'
        '{"type":"tool_use","id":"toolu_2","name":"Read","input":{}}]}}'
    )
    assert state.active_tools == {"toolu_1", "toolu_2"}
    state.feed(
        '{"type":"user","message":{"content":[{"type":"tool_result",'
        '"tool_use_id":"toolu_1"}]}}'
    )
    assert state.active_tools == {"toolu_2"}
    state.feed(
        '{"type":"user","message":{"content":[{"type":"tool_result",'
        '"tool_use_id":"toolu_2"}]}}'
    )
    assert not state.active_tools


def test_claude_malformed_content_is_ignored() -> None:
    state = Events()
    state.feed('{"type":"assistant","message":"text"}')
    state.feed('{"type":"assistant","message":{"content":"text"}}')
    state.feed('{"type":"user","message":{"content":[1,{"type":"tool_result"}]}}')
    assert not state.active_tools
    assert state.outcome(0) == "task_failed"


def test_feed_grok_usage_event_adds_nothing() -> None:
    state = Events()
    state.feed(
        '{"type":"usage","input_tokens":99,"cache_read_input_tokens":1,'
        '"output_tokens":4,"reasoning_tokens":2}'
    )
    assert state.tokens is None
    assert state.provenance == "none"
