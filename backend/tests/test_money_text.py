import pytest

from app.agent import budget_tool, chat_answer, money_text
from app.agent.chat_dispatch import _usd_cents_display
from app.agent.money_text import format_usd


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "USD $0.00"),
        (5, "USD $0.05"),
        (99, "USD $0.99"),
        (100, "USD $1.00"),
        (1234, "USD $12.34"),
        (-1, "USD -$0.01"),
        (-100, "USD -$1.00"),
        (-1234, "USD -$12.34"),
        (100000000, "USD $1000000.00"),
    ],
)
def test_format_usd(cents: int, text: str) -> None:
    assert format_usd(cents) == text


def test_usd_aliases_are_one_function() -> None:
    assert chat_answer._usd is money_text.format_usd
    assert budget_tool._usd is money_text.format_usd


@pytest.mark.parametrize("value", [True, 1.5, "100", None])
def test_usd_cents_display_rejects_non_int(value: object) -> None:
    assert _usd_cents_display(value) is None


def test_usd_cents_display_formats_int() -> None:
    assert _usd_cents_display(1234) == format_usd(1234)
