import json

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


def test_codex_usage_ignores_nested_malformed_and_replay() -> None:
    state = Events()
    payload = {
        "type": "turn.completed",
        "id": "t1",
        "usage": {
            "input_tokens": 2,
            "cached_input_tokens": 1,
            "output_tokens": 3,
            "reasoning_output_tokens": 4,
        },
    }
    state.feed(json.dumps(payload))
    state.feed(json.dumps(payload))
    state.feed(
        '{"type":"item.completed","item":{"type":"command_execution","id":"a",'
        '"aggregated_output":"{\\"type\\":\\"turn.completed\\",\\"usage\\":{\\"input_tokens\\":99}}"}}'
    )
    state.feed('{"type":"event_msg","payload":{"type":"token_count","input_tokens":8}}')
    assert state.usage == {
        "input_tokens": 2,
        "cached_tokens": 1,
        "output_tokens": 3,
        "reasoning_tokens": 4,
    }
    bad = Events()
    bad.feed(
        '{"type":"turn.completed","usage":{"input_tokens":"1","output_tokens":-2}}'
    )
    assert bad.usage == {
        "input_tokens": None,
        "cached_tokens": None,
        "output_tokens": None,
        "reasoning_tokens": None,
    }
    grok = Events()
    grok.feed('{"type":"end","stopReason":"end_turn"}')
    assert grok.usage is None
    assert grok.usage_provenance == "unsupported"


def _usage_event(turn_id: str | None = None) -> str:
    payload: dict[str, object] = {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 2,
            "cached_input_tokens": 1,
            "output_tokens": 3,
            "reasoning_output_tokens": 4,
        },
    }
    if turn_id is not None:
        payload["id"] = turn_id
    return json.dumps(payload)


def test_identical_turns_without_id_are_counted() -> None:
    state = Events()
    payload = _usage_event()
    state.feed(payload)
    state.feed(payload)
    assert state.usage == {
        "input_tokens": 4,
        "cached_tokens": 2,
        "output_tokens": 6,
        "reasoning_tokens": 8,
    }


def test_duplicate_known_id_is_not_double_counted() -> None:
    state = Events()
    payload = _usage_event("t1")
    state.feed(payload)
    state.feed(payload)
    assert state.usage == {
        "input_tokens": 2,
        "cached_tokens": 1,
        "output_tokens": 3,
        "reasoning_tokens": 4,
    }


def test_established_turn_without_id_dedups_until_next_start() -> None:
    state = Events()
    payload = _usage_event()
    state.feed('{"type":"turn.started"}')
    state.feed(payload)
    state.feed(payload)
    assert state.usage == {
        "input_tokens": 2,
        "cached_tokens": 1,
        "output_tokens": 3,
        "reasoning_tokens": 4,
    }
    state.feed('{"type":"turn.started"}')
    state.feed(payload)
    assert state.usage == {
        "input_tokens": 4,
        "cached_tokens": 2,
        "output_tokens": 6,
        "reasoning_tokens": 8,
    }
