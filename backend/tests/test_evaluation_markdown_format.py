from __future__ import annotations

import sys
from decimal import Decimal

import pytest

from app.evaluation_markdown_format import cell, source_link, table


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "Unknown"),
        (True, "true"),
        (False, "false"),
        (0, "0"),
        (0.0, "0.0"),
        (-0.0, "-0.0"),
        (-12, "-12"),
        (1.25, "1.25"),
        ("", ""),
        ("plain text", "plain text"),
        ("Unknown", "Unknown"),
        ("$0.0100", r"\$0\.0100"),
        ("0.00000000000000000001", r"0\.00000000000000000001"),
        ("ab" * 32, "ab" * 32),
        ("gpt-6.1-sol", r"gpt\-6\.1\-sol"),
    ],
)
def test_scalar_cells(value: object, expected: str) -> None:
    assert cell(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(10**255, "1" + "0" * 255), (-(10**254), "-1" + "0" * 254)],
)
def test_integer_cells_preserve_256_character_values(value: int, expected: str) -> None:
    assert len(expected) == 256
    assert cell(value) == expected


@pytest.mark.parametrize("value", [10**256, -(10**255)])
def test_integer_cells_reject_257_character_values(value: int) -> None:
    with pytest.raises(ValueError) as error:
        cell(value)
    assert str(error.value) == "Invalid Markdown cell."
    assert error.value.__cause__ is None
    assert error.value.__context__ is None


def test_integer_conversion_failure_has_a_static_error() -> None:
    digit_limit = sys.get_int_max_str_digits()
    if digit_limit == 0:
        pytest.skip("Python integer-string digit limit is disabled.")
    value = 10**digit_limit
    with pytest.raises(ValueError) as error:
        cell(value)
    assert str(error.value) == "Invalid Markdown cell."
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__


class Untrusted:
    def __str__(self) -> str:
        raise AssertionError("Custom conversion executed.")


class CustomInt(int):
    pass


@pytest.mark.parametrize(
    "value",
    [
        [],
        {},
        (),
        set(),
        b"text",
        Decimal("1.00"),
        Untrusted(),
        CustomInt(0),
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_invalid_cells_have_static_errors(value: object) -> None:
    with pytest.raises(ValueError) as error:
        cell(value)
    assert str(error.value) == "Invalid Markdown cell."
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("left|right", r"left\|right"),
        ("a\r\n\t\nb", "a b"),
        ("a\u2028\u2029b", "a b"),
        ("`code`", r"\`code\`"),
        ("*bold* _text_ ~~gone~~", r"\*bold\* \_text\_ \~\~gone\~\~"),
        ("[label](target)", r"\[label\]\(target\)"),
        ("![image](target)", r"\!\[image\]\(target\)"),
        ("<script>&value</script>", r"\<script\>\&value\<\/script\>"),
        ("# heading", r"\# heading"),
        ("- item + item", r"\- item \+ item"),
        ("1. item", r"1\. item"),
        ("\\|", r"\\\|"),
        ("a\x00\x08\x1b\x7f\x85b", "ab"),
        ("a\u061c\u200e\u200f\u202e\u202c\u2066\u2069b", "ab"),
    ],
)
def test_labels_cannot_create_markdown(value: str, expected: str) -> None:
    assert cell(value) == expected


def test_long_text_has_a_visible_bounded_suffix() -> None:
    assert cell("a" * 256) == "a" * 256
    assert cell("a" * 257) == "a" * 255 + "…"
    assert cell("界" * 257) == "界" * 255 + "…"
    assert cell("*" * 128) == r"\*" * 128
    assert cell("*" * 129) == r"\*" * 127 + "…"
    assert cell("a" * 254 + "|extra") == "a" * 254 + "…"
    assert cell("a" * 254 + "\\extra") == "a" * 254 + "…"


def test_table_shape_and_input_immutability() -> None:
    headers = ("Model", "Cost", "Seen")
    rows: list[tuple[object, ...]] = [("model", "$0.00", True), ("other", 0, None)]
    before = list(rows)
    assert table(headers, rows) == (
        "| Model | Cost | Seen |\n"
        "| --- | --- | --- |\n"
        r"| model | \$0\.00 | true |"
        "\n| other | 0 | Unknown |"
    )
    assert headers == ("Model", "Cost", "Seen")
    assert rows == before
    assert all(
        current is original for current, original in zip(rows, before, strict=True)
    )


def test_empty_table_is_valid() -> None:
    assert table(("Name", "Cost"), []) == "| Name | Cost |\n| --- | --- |"


def test_table_escapes_headers_and_values() -> None:
    expected = r"| a\|b |" + "\n| --- |\n" + r"| x \|y |"
    assert table(("a|b",), [("x\n|y",)]) == expected


@pytest.mark.parametrize(
    ("headers", "rows"),
    [((), []), (("a",), [()]), (("a",), [(1, 2)]), (("a", "b"), [(1,)])],
)
def test_invalid_table_shape_has_static_errors(
    headers: tuple[str, ...], rows: list[tuple[object, ...]]
) -> None:
    before = list(rows)
    with pytest.raises(ValueError) as error:
        table(headers, rows)
    assert str(error.value) == "Invalid Markdown table."
    assert rows == before


def test_invalid_table_value_uses_static_cell_error() -> None:
    with pytest.raises(ValueError) as error:
        table(("Value",), [(Untrusted(),)])
    assert str(error.value) == "Invalid Markdown cell."


def test_source_link_encodes_markdown_punctuation() -> None:
    url = 'https://Example.com:443/a(b)[c]|`x`<y> "z"?q=[a](b)&x=1#*note*'
    assert source_link("[rate] !`<x>|", url) == (
        r"[\[rate\] \!\`\<x\>\|]("
        "https://example.com:443/a%28b%29%5Bc%5D%7C%60x%60%3Cy%3E%20%22z%22"
        "?q=%5Ba%5D%28b%29&x=1#%2Anote%2A)"
    )


def test_source_link_preserves_separators_and_existing_encoding() -> None:
    url = "https://docs.example.com/a%20b?q=1+2&x=a/b#part"
    assert source_link("Source", url) == "[Source](" + url + ")"
    assert source_link("Source", "https://example.com./") == (
        "[Source](https://example.com./)"
    )


def test_source_link_uses_a_bounded_safe_label() -> None:
    result = source_link("*" * 129, "https://example.com")
    assert result == "[" + r"\*" * 127 + "…](https://example.com)"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "javascript:alert(1)",
        "https://user:pass@example.com",
        "https://user@example.com",
        "https://example.com:bad",
        "https://example.com:65536",
        "https://example.com:0",
        "https://example.com:",
        "https://example.com:-1",
        "https://example.com/a\nb",
        "https://example.com/a\tb",
        "https://example.com/a\x00b",
        "https://example.com/\u202eb",
        "https://example.com\\path",
        "https://example.com/a%zz",
        "https://example.com/%",
        "https:///missing",
        "https://",
        "https:example.com",
        " https://example.com",
        "https://[broken",
        "https://a..example.com",
        "https://.example.com",
        "https://example.com..",
        "https://-example.com",
        "https://example-.com",
        "https://bad_host.example.com",
        "https://exa mple.com",
        "https://example.com%40other.com",
        "https://éxample.com",
        "https://" + "a" * 64 + ".com",
        "https://" + ".".join(["a" * 63] * 4),
    ],
)
def test_invalid_source_links_have_static_errors(url: str) -> None:
    with pytest.raises(ValueError) as error:
        source_link("Source", url)
    assert str(error.value) == "Invalid source link."
    assert error.value.__cause__ is None
