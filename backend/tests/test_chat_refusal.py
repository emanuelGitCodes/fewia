from __future__ import annotations

import pytest

from app.agent.chat_refusal import parse_refusal

_SECRETS = (
    "I cannot provide credentials or raw bank records. "
    "I can help plan meals using the budget summary."
)
_PURCHASE = "I cannot buy items or place orders. I can help prepare a grocery plan."
_EXTERNAL = (
    "I cannot open external links or place orders. I can help prepare a grocery plan."
)
_SENTINEL = "do-not-echo-raw-input"


@pytest.mark.parametrize(
    ("text", "answer"),
    [
        ('{"refusal":"secrets"}', _SECRETS),
        ('{"refusal":"purchase"}', _PURCHASE),
        ('{"refusal":"external_url"}', _EXTERNAL),
        (' {"refusal": "secrets"} \n', _SECRETS),
    ],
)
def test_parse_refusal_accepts_exact_reasons(text: str, answer: str) -> None:
    assert parse_refusal(text) == answer


@pytest.mark.parametrize(
    "text",
    [
        '{"refusal":"secrets","refusal":"purchase"}',
        '{"refusal":"secrets","extra":"x"}',
        '{"refusal":"other"}',
        '{"refusal":1}',
        '{"refusal":true}',
        '{"refusal":false}',
        '{"refusal":["secrets"]}',
        '["secrets"]',
        '{"refusal":null}',
        "null",
        '{"refusal":"secrets"} leftover',
        '{"refusal":NaN}',
        '{"refusal":Infinity}',
        '{"refusal":-Infinity}',
    ],
)
def test_parse_refusal_rejects_invalid_payloads(text: str) -> None:
    result = parse_refusal(text)
    assert result is None
    assert result != text


def test_parse_refusal_rejects_oversized_input() -> None:
    valid = '{"refusal":"secrets"}'
    oversized = valid + (" " * (257 - len(valid)))
    assert len(oversized) == 257
    assert parse_refusal(oversized) is None
    bounded = valid + (" " * (256 - len(valid)))
    assert len(bounded) == 256
    assert parse_refusal(bounded) == _SECRETS


def test_parse_refusal_rejects_deeply_nested_malformed_input() -> None:
    nested = "{" * 128 + "}" * 128
    assert len(nested) == 256
    assert parse_refusal(nested) is None
    wrapped = '{"k":' * 40 + "null" + "}" * 40
    assert len(wrapped) <= 256
    assert parse_refusal(wrapped) is None


def test_parse_refusal_does_not_echo_raw_text() -> None:
    payloads: list[object] = [
        _SENTINEL,
        '{"refusal":"' + _SENTINEL + '"}',
        "{not-json " + _SENTINEL,
        '{"refusal":"secrets"} ' + _SENTINEL,
        {"refusal": _SENTINEL},
        1,
        True,
        b'{"refusal":"secrets"}',
    ]
    for payload in payloads:
        result = parse_refusal(payload)
        assert result is None
        assert result != payload
    assert parse_refusal(None) is None
