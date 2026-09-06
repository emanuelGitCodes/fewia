import pytest

from dev_supervisor.events import Events


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


def test_embedded_grok_permission_code() -> None:
    import json

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
