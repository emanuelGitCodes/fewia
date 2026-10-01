"""Tests for the shared evidence ID helper."""

from datetime import date

from app.tools.base import build_evidence_id


def test_evidence_id_uses_month_form_for_a_whole_month() -> None:
    got = build_evidence_id("health", 1, date(2026, 8, 1), date(2026, 8, 31))
    assert got == "health:user-1:2026-08"


def test_evidence_id_uses_day_form_for_any_other_range() -> None:
    got = build_evidence_id("health", 1, date(2026, 7, 15), date(2026, 8, 4))
    assert got == "health:user-1:2026-07-15..2026-08-04"


def test_evidence_id_uses_day_form_for_a_partial_month() -> None:
    got = build_evidence_id("finance", 2, date(2026, 8, 1), date(2026, 8, 30))
    assert got == "finance:user-2:2026-08-01..2026-08-30"
