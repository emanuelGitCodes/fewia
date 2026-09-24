from __future__ import annotations

import copy
import re
from collections.abc import Callable

import pytest

from app.evaluation_markdown import render_evaluation_markdown
from app.evaluation_report_values import INVALID

DIGEST = "0123456789abcdef0123456789abcdef01234567"
SECRET = "FIXTURE_SECRET_MARKER"
FAKE = "deterministic_fake_provider"
REAL = "real_bedrock"


def _invalid(run: Callable[[], object]) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(INVALID)}$") as caught:
        run()
    assert str(caught.value) == INVALID
    assert SECRET not in str(caught.value)


def _checks(**counts: object) -> dict[str, object]:
    body: dict[str, object] = {
        "assessed": 0,
        "passed": 0,
        "failed": 0,
        "invalid": 0,
        "outside_scope": 0,
    }
    body.update(counts)
    return body


def _summary(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "total_slots": 0,
        "execution_counts": {
            "scored": 0,
            "observed": 0,
            "failed": 0,
            "unassessed": 0,
            "invalid": 0,
        },
        "fixture_checks": _checks(),
        "controlled_checks": _checks(),
        "final_plan_checks": _checks(),
        "evidence_breakdown": {
            "observation": {FAKE: 0, REAL: 0, "unknown": 0},
        },
        "metrics_status": "unassessed",
        "quality_note": SECRET,
        "metadata": {"case_id": "P04", "answer": SECRET},
        "answers": {"P04": SECRET},
        "plan_accepted": True,
    }
    body.update(overrides)
    return body


def _telemetry(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "total_slots": 0,
        "observed_slots": 0,
        "completed_observations": 0,
        "failed_or_partial_observations": 0,
        "latency_sample_count": 0,
        "p50_latency_seconds": None,
        "p95_latency_seconds": None,
        "percentile_method": "nearest-rank",
        "known_usage_slots": 0,
        "unknown_usage_slots": 0,
        "known_input_tokens": 0,
        "known_output_tokens": 0,
        "input_tokens": None,
        "output_tokens": None,
        "quality_note": SECRET,
        "token_note": SECRET,
    }
    body.update(overrides)
    return body


def _drop(body: dict[str, object], key: str) -> dict[str, object]:
    out = dict(body)
    del out[key]
    return out


def _render(
    summary: object | None = None,
    telemetry: object | None = None,
    *,
    revision: str = DIGEST,
    model_id: str | None = "eval-fake-v1",
    source_region: str | None = "us-east-1",
) -> str:
    return render_evaluation_markdown(
        _summary() if summary is None else summary,
        _telemetry() if telemetry is None else telemetry,
        revision=revision,
        model_id=model_id,
        source_region=source_region,
    )


def test_empty_coverage_renders_zeros_and_unknown_optional_fields() -> None:
    text = _render(model_id=None, source_region=None)
    assert text.startswith("# FEWIA evaluation record\n")
    assert f"Revision: {DIGEST}" in text
    assert "Model: not recorded" in text
    assert "Source region: not recorded" in text
    assert "Global quality: UNASSESSED" in text
    assert "| scored | observed | failed | unassessed | invalid |" in text
    assert "| 0 | 0 | 0 | 0 | 0 |" in text
    assert "| fixture | 0 | 0 | 0 | 0 | 0 |" in text
    assert "| control | 0 | 0 | 0 | 0 | 0 |" in text
    assert "| final-plan | 0 | 0 | 0 | 0 | 0 |" in text
    assert f"| {FAKE} | {REAL} | unknown |" in text
    assert "Sample count: 0" in text
    assert "Method: nearest-rank" in text
    assert "p50: unknown" in text
    assert "p95: unknown" in text
    assert "known_usage_slots: 0" in text
    assert "unknown_usage_slots: 0" in text
    assert "known_input_tokens: 0" in text
    assert "known_output_tokens: 0" in text
    assert "input_tokens: unknown" in text
    assert "output_tokens: unknown" in text
    assert "Latency sums user-turn elapsed times for each observation." in text
    assert "Final-plan checks cover the last structured plan only." in text
    assert "Fake evidence and live evidence are not interchangeable." in text


def test_complete_telemetry_shows_known_overall_tokens_and_latency() -> None:
    text = _render(
        _summary(
            execution_counts={
                "scored": 48,
                "observed": 24,
                "failed": 0,
                "unassessed": 18,
                "invalid": 0,
            },
            fixture_checks=_checks(assessed=48, passed=48, outside_scope=42),
            controlled_checks=_checks(assessed=3, passed=3, outside_scope=87),
            final_plan_checks=_checks(
                assessed=15, passed=12, failed=3, outside_scope=75
            ),
            evidence_breakdown={"observation": {FAKE: 24, REAL: 3, "unknown": 1}},
        ),
        _telemetry(
            latency_sample_count=3,
            p50_latency_seconds=2.0,
            p95_latency_seconds=4.0,
            known_usage_slots=2,
            unknown_usage_slots=0,
            known_input_tokens=16,
            known_output_tokens=6,
            input_tokens=16,
            output_tokens=6,
        ),
    )
    assert "| 48 | 24 | 0 | 18 | 0 |" in text
    assert "| fixture | 48 | 48 | 0 | 0 | 42 |" in text
    assert "| control | 3 | 3 | 0 | 0 | 87 |" in text
    assert "| final-plan | 15 | 12 | 3 | 0 | 75 |" in text
    assert "| 24 | 3 | 1 |" in text
    assert "Sample count: 3" in text
    assert "p50: 2.000 s" in text
    assert "p95: 4.000 s" in text
    assert "known_usage_slots: 2" in text
    assert "unknown_usage_slots: 0" in text
    assert "input_tokens: 16" in text
    assert "output_tokens: 6" in text


def test_partial_telemetry_keeps_overall_tokens_unknown() -> None:
    text = _render(
        telemetry=_telemetry(
            latency_sample_count=3,
            p50_latency_seconds=1.25,
            p95_latency_seconds=4.0,
            known_usage_slots=1,
            unknown_usage_slots=2,
            known_input_tokens=8,
            known_output_tokens=3,
            input_tokens=None,
            output_tokens=None,
        )
    )
    assert "p50: 1.250 s" in text
    assert "known_input_tokens: 8" in text
    assert "known_output_tokens: 3" in text
    assert "input_tokens: unknown" in text
    assert "output_tokens: unknown" in text


def test_zero_token_totals_are_not_unknown() -> None:
    text = _render(
        telemetry=_telemetry(
            latency_sample_count=1,
            p50_latency_seconds=0.0,
            p95_latency_seconds=0,
            known_usage_slots=1,
            unknown_usage_slots=0,
            known_input_tokens=0,
            known_output_tokens=0,
            input_tokens=0,
            output_tokens=0,
        )
    )
    assert "p50: 0.000 s" in text
    assert "p95: 0.000 s" in text
    assert "known_input_tokens: 0" in text
    assert "input_tokens: 0" in text
    assert "output_tokens: 0" in text
    assert "input_tokens: unknown" not in text
    assert "p50: unknown" not in text


def test_output_has_no_quality_rate_or_copied_payloads() -> None:
    text = _render()
    lowered = text.lower()
    assert "%" not in text
    assert "success_rate" not in lowered
    assert "pass_rate" not in lowered
    assert "90%" not in text
    assert "95%" not in text
    assert SECRET not in text
    assert "P04" not in text
    assert "plan_accepted" not in text
    assert "quality_note" not in text
    assert "token_note" not in text
    assert "`eval-fake-v1`" in text
    assert "`us-east-1`" in text


def test_caller_inputs_are_unmodified() -> None:
    summary = _summary()
    telemetry = _telemetry(input_tokens=None, output_tokens=4)
    snapshot_summary = copy.deepcopy(summary)
    snapshot_telemetry = copy.deepcopy(telemetry)
    text = render_evaluation_markdown(
        summary,
        telemetry,
        revision=DIGEST,
        model_id="eval-fake-v1",
        source_region="us-east-1",
    )
    assert summary == snapshot_summary
    assert telemetry == snapshot_telemetry
    assert "input_tokens: unknown" in text
    assert "output_tokens: 4" in text


def test_missing_required_optional_count_is_rejected() -> None:
    _invalid(lambda: _render(telemetry=_drop(_telemetry(), "input_tokens")))
    _invalid(lambda: _render(telemetry=_drop(_telemetry(), "p50_latency_seconds")))
    _invalid(lambda: _render(telemetry=_drop(_telemetry(), "percentile_method")))
    _invalid(lambda: _render(summary=_drop(_summary(), "metrics_status")))
    _invalid(lambda: _render(summary=_drop(_summary(), "execution_counts")))
    _invalid(lambda: _render(summary=_summary(evidence_breakdown={})))
    _invalid(lambda: _render(telemetry=_telemetry(known_input_tokens=None)))
    _invalid(lambda: _render(telemetry=_telemetry(known_usage_slots=None)))
    _invalid(lambda: _render(telemetry=_telemetry(latency_sample_count=None)))
    _invalid(lambda: _render(telemetry=_telemetry(input_tokens=True)))


def test_metrics_status_and_percentile_method_must_match() -> None:
    _invalid(lambda: _render(summary=_summary(metrics_status="passed")))
    _invalid(lambda: _render(summary=_summary(metrics_status="UNASSESSED")))
    _invalid(lambda: _render(summary=_summary(metrics_status=None)))
    _invalid(lambda: _render(telemetry=_telemetry(percentile_method="linear")))
    _invalid(lambda: _render(telemetry=_telemetry(percentile_method=None)))
    _invalid(lambda: _render(revision="not-a-revision"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda: _render(summary=_summary(execution_counts={"scored": SECRET})),
        lambda: _render(
            summary=_summary(
                execution_counts={
                    "scored": -1,
                    "observed": 0,
                    "failed": 0,
                    "unassessed": 0,
                    "invalid": 0,
                }
            )
        ),
        lambda: _render(
            summary=_summary(
                execution_counts={
                    "scored": True,
                    "observed": 0,
                    "failed": 0,
                    "unassessed": 0,
                    "invalid": 0,
                }
            )
        ),
        lambda: _render(
            summary=_summary(
                execution_counts={
                    "scored": None,
                    "observed": 0,
                    "failed": 0,
                    "unassessed": 0,
                    "invalid": 0,
                }
            )
        ),
        lambda: _render(summary=[]),
        lambda: _render(telemetry=["latency"]),
        lambda: _render(summary=_summary(fixture_checks=_checks(assessed=SECRET))),
        lambda: _render(
            summary=_summary(evidence_breakdown={"observation": {FAKE: 0}})
        ),
    ],
)
def test_malformed_counts_raise_static_error_without_marker(
    mutate: Callable[[], object],
) -> None:
    _invalid(mutate)


@pytest.mark.parametrize(
    "payload",
    [
        f"[click](https://evil.example/{SECRET})",
        f"safe`{SECRET}`",
        f"col|{SECRET}",
        f"<script>{SECRET}</script>",
        f"line\n{SECRET}",
    ],
)
def test_model_and_region_markdown_injection_is_rejected(payload: str) -> None:
    _invalid(lambda: _render(model_id=payload))
    _invalid(lambda: _render(source_region=payload))
