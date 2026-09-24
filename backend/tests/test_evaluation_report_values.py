from __future__ import annotations

import math
import re
from collections.abc import Callable

import pytest

from app.evaluation_report_values import (
    INVALID,
    count,
    group,
    label,
    optional_count,
    revision,
    seconds,
)

DIGEST = "0123456789abcdef0123456789abcdef01234567"
SECRET_MARKER = "FIXTURE_SECRET_MARKER"


def _invalid(run: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(INVALID)}$") as caught:
        run()
    assert str(caught.value) == INVALID
    assert SECRET_MARKER not in str(caught.value)


def test_count_formats_zero_and_positive_ints() -> None:
    assert count(0) == "0"
    assert count(8) == "8"
    assert count(10**400) == str(10**400)


def test_optional_count_maps_none_to_unknown_and_zero_to_zero() -> None:
    assert optional_count(None) == "unknown"
    assert optional_count(0) == "0"
    assert optional_count(3) == "3"


def test_count_rejects_none_bool_float_and_negative() -> None:
    _invalid(lambda: count(None))
    _invalid(lambda: count(True))
    _invalid(lambda: count(False))
    _invalid(lambda: count(1.0))
    _invalid(lambda: count(-1))
    _invalid(lambda: count(""))


def test_optional_count_rejects_bool_float_and_negative() -> None:
    _invalid(lambda: optional_count(True))
    _invalid(lambda: optional_count(False))
    _invalid(lambda: optional_count(-1))
    _invalid(lambda: optional_count(2.0))


def test_seconds_formats_none_zero_int_and_float() -> None:
    assert seconds(None) == "unknown"
    assert seconds(0) == "0.000 s"
    assert seconds(0.0) == "0.000 s"
    assert seconds(-0.0) == "0.000 s"
    assert seconds(1) == "1.000 s"
    assert seconds(1.25) == "1.250 s"


def test_seconds_rejects_nan_infinite_bool_and_negative() -> None:
    _invalid(lambda: seconds(math.nan))
    _invalid(lambda: seconds(math.inf))
    _invalid(lambda: seconds(-math.inf))
    _invalid(lambda: seconds(True))
    _invalid(lambda: seconds(False))
    _invalid(lambda: seconds(-1))
    _invalid(lambda: seconds(-0.001))
    _invalid(lambda: seconds("1"))


def test_seconds_huge_int_raises_static_error() -> None:
    _invalid(lambda: seconds(10**400))


def test_revision_accepts_exact_forty_lowercase_hex() -> None:
    assert len(DIGEST) == 40
    assert revision(DIGEST) == DIGEST


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "0123456789abcdef0123456789abcdef0123456",
        f"{DIGEST}a",
        DIGEST.upper(),
        DIGEST[:-1] + "G",
        DIGEST[:-1] + "A",
        True,
        0,
    ],
)
def test_revision_rejects_invalid_formats(value: object) -> None:
    _invalid(lambda: revision(value))


def test_label_none_is_not_recorded() -> None:
    assert label(None) == "not recorded"


def test_label_renders_literal_inline_code() -> None:
    assert label("deterministic_fake_provider") == "`deterministic_fake_provider`"
    assert label("local PostgreSQL") == "`local PostgreSQL`"
    rendered = label("https://example.com/a-b_1:2")
    assert rendered == "`https://example.com/a-b_1:2`"
    assert "[" not in rendered
    assert "]" not in rendered
    assert "(" not in rendered
    assert ")" not in rendered
    assert "](" not in rendered


def test_label_accepts_bounded_trimmed_ascii() -> None:
    assert label("a" * 256) == "`" + ("a" * 256) + "`"
    assert label("Plaid Sandbox") == "`Plaid Sandbox`"
    assert label("real Bedrock") == "`real Bedrock`"


def test_label_rejects_untrimmed_empty_and_overlong() -> None:
    _invalid(lambda: label(""))
    _invalid(lambda: label(" "))
    _invalid(lambda: label(" foo"))
    _invalid(lambda: label("foo "))
    _invalid(lambda: label("a" * 257))


def test_malicious_markdown_labels_raise_static_error() -> None:
    payloads = (
        f"[click](https://evil.example/{SECRET_MARKER})",
        f"safe`{SECRET_MARKER}`",
        f"col|{SECRET_MARKER}",
        f"[{SECRET_MARKER}]",
        f"({SECRET_MARKER})",
        f"{{{SECRET_MARKER}}}",
        f"line\n{SECRET_MARKER}",
        f"line\r{SECRET_MARKER}",
        f"line\t{SECRET_MARKER}",
        f"<script>{SECRET_MARKER}</script>",
    )
    for payload in payloads:
        with pytest.raises(ValueError, match=f"^{re.escape(INVALID)}$") as caught:
            label(payload)
        assert str(caught.value) == INVALID
        assert SECRET_MARKER not in str(caught.value)
        assert payload not in str(caught.value)


def test_label_does_not_copy_repr_of_arbitrary_objects() -> None:
    class Payload:
        def __repr__(self) -> str:
            return "deterministic_fake_provider"

        def __str__(self) -> str:
            return "deterministic_fake_provider"

    _invalid(lambda: label(Payload()))
    _invalid(lambda: label(["deterministic_fake_provider"]))
    _invalid(lambda: label(0))
    _invalid(lambda: label(False))


def test_returned_labels_leave_inputs_unchanged() -> None:
    text = "deployed AWS evidence"
    assert label(text) == "`deployed AWS evidence`"
    assert text == "deployed AWS evidence"


def test_group_counts_required_keys_only() -> None:
    payload = {"runs": 0, "failures": 2, "extra": 9}
    assert group(payload, ("runs", "failures")) == {"runs": "0", "failures": "2"}
    assert group(payload, ("runs",)) == {"runs": "0"}


def test_group_missing_or_invalid_raises_static_error() -> None:
    _invalid(lambda: group({}, ("runs",)))
    _invalid(lambda: group({"runs": 1}, ("runs", "failures")))
    _invalid(lambda: group({"runs": None}, ("runs",)))
    _invalid(lambda: group({"runs": True}, ("runs",)))
    _invalid(lambda: group({"runs": -1}, ("runs",)))
    _invalid(lambda: group(None, ("runs",)))
    _invalid(lambda: group([("runs", 1)], ("runs",)))
    _invalid(lambda: group({1: 0}, ("runs",)))
    _invalid(lambda: group({1: 2, "runs": 1}, ("runs",)))


def test_group_whitelist_metadata_does_not_leak() -> None:
    payload = {
        "runs": 1,
        "secret": SECRET_MARKER,
        "source_urls": ["https://evil.example"],
        "cost": "not-a-count",
    }
    result = group(payload, ("runs",))
    assert result == {"runs": "1"}
    assert "secret" not in result
    assert "source_urls" not in result
    assert "cost" not in result
    assert SECRET_MARKER not in str(result)


def test_group_does_not_mutate_source() -> None:
    payload = {"runs": 2, "extra": 4}
    snapshot = dict(payload)
    result = group(payload, ("runs",))
    result["runs"] = "9"
    result["extra"] = "leaked"
    assert payload == snapshot
    assert payload["runs"] == 2
