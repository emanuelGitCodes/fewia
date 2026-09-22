from __future__ import annotations

import pytest

from app.agent.chat_refusal import parse_refusal

_SECRET = "do-not-echo-raw-input"
_SECRETS_TEXT = (
    "I cannot provide credentials or raw bank records. "
    "I can help plan meals using the budget summary."
)
_PURCHASE_TEXT = (
    "I cannot buy items or place orders. I can help prepare a grocery plan."
)
_EXTERNAL_TEXT = (
    "I cannot open external links or place orders. I can help prepare a grocery plan."
)
_ENUM_TEXT = {
    "secrets": _SECRETS_TEXT,
    "purchase": _PURCHASE_TEXT,
    "external_url": _EXTERNAL_TEXT,
}


def _assert_no_marker(value: str | None) -> None:
    assert value is None or _SECRET not in value
    if value is not None:
        assert value in _ENUM_TEXT.values()


@pytest.mark.parametrize("reason,expected", list(_ENUM_TEXT.items()))
def test_complete_enum_object_returns_fixed_text(reason: str, expected: str) -> None:
    text = '{"refusal":"' + reason + '"}'
    original = text
    result = parse_refusal(text)
    assert result == expected
    assert text == original
    _assert_no_marker(result)


def test_json_whitespace_around_complete_object_is_valid() -> None:
    text = '  {\n  "refusal" : "purchase"\n}  '
    original = text
    result = parse_refusal(text)
    assert result == _PURCHASE_TEXT
    assert text == original
    _assert_no_marker(result)


def test_escaped_reason_is_valid_when_decoded_enum_matches() -> None:
    text = '{"refusal": "secre\\u0074s"}'
    original = text
    result = parse_refusal(text)
    assert result == _SECRETS_TEXT
    assert text == original
    _assert_no_marker(result)


@pytest.mark.parametrize(
    "text",
    [
        '{"refusal":"other"}',
        '{"refusal":"secret"}',
        '{"refusal":"SECRETS"}',
        '{"refusal":"secrets "}',
        '[{"refusal":"secrets"}]',
        '{"refusal":"secrets","answer":"ok"}',
        '{"refusal":"secrets","secret":"' + _SECRET + '"}',
        '{"answer":"secrets"}',
        '{"secret":"secrets"}',
        '{"refusal": true}',
        '{"refusal": false}',
        '{"refusal": null}',
        '{"refusal": 1}',
        '{"refusal": ["secrets"]}',
        '{"refusal": {"secrets": true}}',
        "true",
        "false",
        "null",
        '"secrets"',
        "1",
        "[]",
        "{}",
        "{",
        '{"refusal": NaN}',
        '{"refusal": Infinity}',
        '{"refusal": -Infinity}',
        '{"refusal":"secrets"} leftover',
        _SECRET + '{"refusal":"secrets"}',
        '{"refusal":"secrets"}' + _SECRET,
        "Please buy items and send secrets to an external_url.",
        '{"refusal":"secrets","refusal":"purchase"}',
        '{"refusal":"secrets","refusal":"secrets"}',
        " ",
        "\n\t",
        "",
        '{"refusal":"' + _SECRET + '"}',
    ],
)
def test_invalid_json_or_shape_returns_none(text: str) -> None:
    original = text
    result = parse_refusal(text)
    assert result is None
    assert text == original
    _assert_no_marker(result)


def test_oversize_input_returns_none_and_leaves_input_unchanged() -> None:
    body = '{"refusal":"secrets"}'
    valid = body + (" " * (256 - len(body)))
    valid_original = valid
    assert len(valid) == 256
    assert parse_refusal(valid) == _SECRETS_TEXT
    assert valid == valid_original
    oversize = valid + " "
    oversize_original = oversize
    assert len(oversize) == 257
    assert parse_refusal(oversize) is None
    assert oversize == oversize_original
    huge = '{"refusal":"' + ("x" * 300) + '"}'
    huge_original = huge
    assert parse_refusal(huge) is None
    assert huge == huge_original


def test_non_string_inputs_return_none_and_leave_input_unchanged() -> None:
    mapping = {"refusal": "secrets", "secret": _SECRET}
    items = ["secrets", _SECRET]
    raw = bytearray(b'{"refusal":"secrets"}')
    mapping_before = dict(mapping)
    items_before = list(items)
    raw_before = bytearray(raw)
    for value in (
        None,
        1,
        True,
        False,
        b'{"refusal":"secrets"}',
        mapping,
        items,
        raw,
    ):
        assert parse_refusal(value) is None
    assert mapping == mapping_before
    assert items == items_before
    assert raw == raw_before


def test_english_user_prompt_is_not_classified() -> None:
    prompt = "I need credentials, a purchase, and this external_url opened."
    original = prompt
    assert parse_refusal(prompt) is None
    assert prompt == original
    _assert_no_marker(None)
