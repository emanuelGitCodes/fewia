"""Tests for the shared FEWIA_JOB_TEST_DATABASE_URL gate."""

import pytest
from conftest import require_test_database_url, skip_or_fail_unreachable_test_database


def test_require_test_database_url_skips_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEWIA_JOB_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("FEWIA_REQUIRE_DB", raising=False)
    with pytest.raises(pytest.skip.Exception):
        require_test_database_url()


def test_require_test_database_url_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEWIA_JOB_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("FEWIA_REQUIRE_DB", "1")
    with pytest.raises(pytest.fail.Exception) as caught:
        require_test_database_url()
    message = str(caught.value)
    assert "FEWIA_REQUIRE_DB" in message
    assert "FEWIA_JOB_TEST_DATABASE_URL" in message


@pytest.mark.parametrize("require_db", [None, "1", "0"])
def test_require_test_database_url_returns_set_value(
    monkeypatch: pytest.MonkeyPatch, require_db: str | None
) -> None:
    sample = "postgresql://example/fewia"
    monkeypatch.setenv("FEWIA_JOB_TEST_DATABASE_URL", sample)
    if require_db is None:
        monkeypatch.delenv("FEWIA_REQUIRE_DB", raising=False)
    else:
        monkeypatch.setenv("FEWIA_REQUIRE_DB", require_db)
    assert require_test_database_url() == sample


def test_skip_or_fail_unreachable_test_database_skips_when_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEWIA_REQUIRE_DB", raising=False)
    with pytest.raises(pytest.skip.Exception) as caught:
        skip_or_fail_unreachable_test_database(RuntimeError("boom"))
    assert "FEWIA_JOB_TEST_DATABASE_URL" in str(caught.value)


def test_skip_or_fail_unreachable_test_database_fails_when_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEWIA_REQUIRE_DB", "1")
    with pytest.raises(pytest.fail.Exception) as caught:
        skip_or_fail_unreachable_test_database(RuntimeError("boom"))
    message = str(caught.value)
    assert "FEWIA_REQUIRE_DB" in message
    assert "FEWIA_JOB_TEST_DATABASE_URL" in message
