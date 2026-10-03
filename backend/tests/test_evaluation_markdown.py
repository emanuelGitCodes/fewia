import json
from copy import deepcopy
from pathlib import Path
from typing import cast
from unittest.mock import patch

import pytest

from app.evaluation_manifest import build_manifest
from app.evaluation_markdown import render_report
from app.evaluation_markdown_data import prepare_report
from app.evaluation_markdown_format import cell, table
from app.evaluation_markdown_sections import render_quality
from app.evaluation_markdown_telemetry import render_telemetry
from app.evaluation_runner import run_evaluation

_MODEL = "us.amazon.nova-2-lite-v1:0"
_ERROR = "^Invalid evaluation report input$"


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def _rows(value: object) -> list[dict[str, object]]:
    assert type(value) is list
    return cast(list[dict[str, object]], value)


def _slot(
    *,
    condition: str = "tool_enabled",
    evidence: str = "real_bedrock",
    status: str = "completed",
    repeat: int = 1,
) -> dict[str, object]:
    return {
        "case_id": "A02",
        "repeat": repeat,
        "condition": condition,
        "driver": "no_tool" if condition == "no_tool" else "model",
        "status": status,
        "elapsed_seconds": 2.0,
        "report": None,
        "assessments": {},
        "observation": {
            "case_id": "A02",
            "condition": condition,
            "status": status,
            "evidence_class": evidence,
            "model_id": _MODEL,
            "turns": [
                {
                    "status": status,
                    "usage": {"inputTokens": 1000, "outputTokens": 2000},
                    "provider_calls": 1,
                    "elapsed_seconds": 1.5,
                    "provider_elapsed_seconds": 0.5,
                }
            ],
        },
    }


def _assess(slot: dict[str, object], *, failed: bool = False) -> None:
    slot["assessments"] = {
        "plan": {
            "status": "passed",
            "scope": "final_plan",
            "constraint_violations": [],
        },
        "outcome": {
            "status": "failed" if failed else "passed",
            "scope": "final_turn",
            "clarification_required": False,
            "clarification_correct": None,
            "checks": {"completed_request": not failed},
        },
        "claims": {
            "status": "passed",
            "scope": "public_output_only",
            "supported_count": 1,
            "assessed_count": 1,
            "unsupported_count": 0,
            "unknown_count": 0,
            "supported_refusal_count": 0,
        },
    }


def _batch(
    primary: list[dict[str, object]] | None = None,
    baseline: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    primary = [_slot()] if primary is None else primary
    baseline = [] if baseline is None else baseline
    return {
        "mode": "complete_evaluation",
        "slots": primary,
        "baseline_slots": baseline,
        "primary_slot_count": len(primary),
        "total_slot_count": len(primary) + len(baseline),
        "revision": "a" * 40,
        "started_at": "2026-10-03T12:00:00Z",
        "finished_at": "2026-10-03T12:00:10+00:00",
        "manifest": build_manifest(
            {},
            model_id=_MODEL,
            region="us-east-1",
            model_config={
                "max_tokens": 1024,
                "temperature": 0,
                "reasoning_effort": "low",
            },
        ),
    }


def _rates() -> dict[str, object]:
    return {
        "model_id": _MODEL,
        "region": "us-east-1",
        "currency": "USD",
        "input_usd_per_1000": "0.00033",
        "output_usd_per_1000": "0.00275",
        "source_url": "https://pricing.example.org/bedrock.json",
        "source_version": "20260930230255",
        "published_at": "2026-09-30T23:02:55Z",
        "effective_date": "2026-09-01",
        "retrieved_at": "2026-10-02",
    }


def test_actual_legacy_corpus_renders_42_scored_and_48_unassessed() -> None:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    corpus = _map(json.loads(path.read_text(encoding="utf-8")))
    report = run_evaluation(corpus)
    original = deepcopy(report)
    result = render_report(report)
    assert result.index("## Coverage") < result.index("## Quality\n")
    for label, count in (
        ("Primary slots", 90),
        ("Baseline slots", 0),
        ("Total slots", 90),
        ("Scored slots", 42),
        ("Unassessed slots", 48),
        ("Execution-failed slots", 0),
    ):
        assert f"| {cell(label)} | {count} |" in result
    assert "Coverage-only mode" in result
    assert "legacy runner does not assess complete model/provider quality" in result
    assert "Metrics unavailable." in result
    assert "Unavailable (legacy report)." in result
    assert "No quality failures were recorded." in result
    assert "No assessment or execution issues were recorded." in result
    assert "Empty findings do not establish that targets are met." in result
    assert report == original


def test_mixed_conditions_preserve_quality_and_execution_scopes() -> None:
    primary = _slot()
    baseline = _slot(condition="no_tool", evidence="deterministic_fake_provider")
    for slot in (primary, baseline):
        _assess(slot, failed=True)
    missing = _slot(repeat=2, status="failed")
    _map(missing["observation"])["reason"] = "missing_local_services"
    unknown = _slot(repeat=3, evidence="PRIVATE_EVIDENCE")
    passed = _slot(repeat=4)
    _assess(passed)
    report = _batch([primary, missing, unknown, passed], [baseline])
    original = deepcopy(report)
    prepared = prepare_report(report)
    result = render_report(report)
    assert result.index("## Coverage") < result.index("## Quality\n")
    assert "| Primary slots | 4 |" in result
    assert "| Baseline slots | 1 |" in result
    assert "| Total slots | 5 |" in result
    assert "| Scored slots | 4 |" in result
    assert "| Unassessed slots | 1 |" in result
    assert "| Execution\\-failed slots | 1 |" in result
    assert "Scored includes passed and failed quality assessments" in result
    assert render_quality(_map(prepared["summary"])) in result
    failures = result.split("## Quality failures\n\n", 1)[1].split("\n\n##", 1)[0]
    assert len(_rows(prepared["failures"])) == 2
    for failure in _rows(prepared["failures"]):
        identity = tuple(
            failure[key]
            for key in (
                "case_id",
                "repeat",
                "condition",
                "evidence_class",
                "assessment",
            )
        )
        for check in cast(list[object], failure["checks"]):
            rendered_row = (
                "| " + " | ".join(cell(item) for item in (*identity, check)) + " |"
            )
            assert rendered_row in failures
    issues = result.split("## Assessment and execution issues\n\n", 1)[1]
    for issue in _rows(prepared["issues"]):
        assert cell(issue["reason_code"]) in issues
    assert "required\\_evidence\\_unavailable" in issues
    assert "assessment\\_failed" in issues
    assert "missing\\_local\\_services" in issues
    assert "| failed | failed | missing\\_local\\_services |" in issues
    assert "| unassessed | completed | required\\_evidence\\_unavailable |" in issues
    assert "PRIVATE_EVIDENCE" not in result
    scope = "reference, and fake evidence does not establish real-model quality"
    assert scope in result
    assert report == original


def test_canonical_metadata_includes_allowed_settings_and_all_six_hashes() -> None:
    report = _batch()
    result = render_report(report)
    manifest = _map(report["manifest"])
    assert "| Mode | complete\\_evaluation |" in result
    for key in ("revision", "started_at", "finished_at"):
        assert cell(report[key]) in result
    for key in (
        "version",
        "model_id",
        "region",
        "catalog_version",
        "manifest_hash",
        "corpus_hash",
        "catalog_hash",
        "system_prompt_hash",
        "baseline_system_prompt_hash",
        "model_config_hash",
    ):
        assert cell(manifest[key]) in result
    for key in (
        "manifest_hash",
        "corpus_hash",
        "catalog_hash",
        "system_prompt_hash",
        "baseline_system_prompt_hash",
        "model_config_hash",
    ):
        assert f"| {cell(key)} | {cell(manifest[key])} |" in result
    config = _map(manifest["model_config"])
    for key in ("max_tokens", "temperature", "reasoning_effort"):
        assert f"| {cell(key)} | {cell(config[key])} |" in result
    for condition in cast(list[object], manifest["conditions"]):
        assert f"| Condition | {cell(condition)} |" in result
    assert "| UTC start |" in result
    assert "| UTC end |" in result


def test_quality_and_telemetry_delegate_prepared_results_and_rates() -> None:
    report, rates = _batch(), _rates()
    prepared = prepare_report(report, rates=rates)
    with (
        patch(
            "app.evaluation_markdown.prepare_report", wraps=prepare_report
        ) as prepare,
        patch(
            "app.evaluation_markdown.render_quality", wraps=render_quality
        ) as quality,
        patch(
            "app.evaluation_markdown.render_telemetry", wraps=render_telemetry
        ) as telemetry,
    ):
        result = render_report(report, rates=rates)
    prepare.assert_called_once_with(report, rates=rates)
    quality.assert_called_once_with(prepared["summary"])
    telemetry.assert_called_once_with(prepared["telemetry"], prepared["cost"])
    expected = render_telemetry(_map(prepared["telemetry"]), _map(prepared["cost"]))
    assert expected in result
    assert "0\\.00583" in result


def test_unknown_measurements_and_absent_settings_remain_unknown() -> None:
    slot = _slot()
    _rows(_map(slot["observation"])["turns"])[0].update(usage=None, provider_calls=None)
    result = render_report(_batch([slot]))
    assert "| input tokens | Unknown |" in result
    assert "| Estimated USD | Unknown |" in result
    prepared = prepare_report(_batch())
    _map(_map(_map(prepared["metadata"])["manifest"])["model_config"]).clear()
    with patch("app.evaluation_markdown.prepare_report", return_value=prepared):
        result = render_report({})
    assert "| max\\_tokens | Unknown |" in result


def test_raw_answers_exceptions_and_private_fields_are_absent() -> None:
    slot = _slot()
    slot.update(report={"answer": "PRIVATE_ANSWER"}, exception="PRIVATE_EXCEPTION")
    observation = _map(slot["observation"])
    observation.update(
        reason="PRIVATE_REASON",
        reason_code="PRIVATE_CODE",
        hidden_reasoning="PRIVATE_REASONING",
        credentials="PRIVATE_CREDENTIALS",
        response={"answer": "https://PRIVATE_MODEL_URL.example/"},
    )
    _rows(observation["turns"])[0].update(
        message="PRIVATE_MESSAGE", hidden_reasoning="PRIVATE_HIDDEN"
    )
    report = _batch([slot])
    report.update(raw_corpus="PRIVATE_CORPUS", summary={"answer": "PRIVATE_SUMMARY"})
    _map(report["manifest"]).update(credentials="PRIVATE_KEY", corpus="PRIVATE_CORPUS")
    result = render_report(report)
    assert "PRIVATE" not in result
    assert "| catalog |" not in result
    assert "https://" not in result


def test_dynamic_finding_labels_are_escaped_and_bounded() -> None:
    slot = _slot()
    _assess(slot, failed=True)
    prepared = prepare_report(_batch([slot]))
    label = "case|[link](https://example.org)\n" + "a" * 300
    _rows(prepared["issues"])[0]["case_id"] = label
    _rows(prepared["failures"])[0]["case_id"] = label
    with patch("app.evaluation_markdown.prepare_report", return_value=prepared):
        result = render_report({})
    assert result.count(cell(label)) == 2
    assert len(cell(label)) <= 256
    assert "…" in cell(label)
    assert label not in result
    assert "[link](https://example.org)" not in result


def test_empty_canonical_report_has_neutral_findings_and_no_target_assertion() -> None:
    report = _batch([], [])
    result = render_report(report)
    assert "| Total slots | 0 |" in result
    assert "Metrics unassessed." in result
    assert "No quality failures were recorded." in result
    assert "No assessment or execution issues were recorded." in result
    assert "Empty findings do not establish that targets are met." in result
    assert "Targets met" not in result
    assert "target\\_achieved" not in result


def test_inputs_and_rates_are_unchanged_on_success_and_failure() -> None:
    report, rates = _batch(), _rates()
    original_report, original_rates = deepcopy(report), deepcopy(rates)
    render_report(report, rates=rates)
    assert report == original_report
    assert rates == original_rates
    rates["source_url"] = "https://user:PRIVATE_RATE@pricing.example.org"
    original_rates = deepcopy(rates)
    with pytest.raises(ValueError, match=_ERROR) as caught:
        render_report(report, rates=rates)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    assert "PRIVATE" not in str(caught.value)
    assert report == original_report
    assert rates == original_rates


@pytest.mark.parametrize("value", [None, True, [], "PRIVATE_REPORT", 1])
def test_malformed_report_types_return_static_error(value: object) -> None:
    with pytest.raises(ValueError, match=_ERROR):
        render_report(cast(dict[str, object], value))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slots", [None]),
        ("baseline_slots", None),
        ("manifest", {"answer": "PRIVATE_MANIFEST"}),
        ("mode", "PRIVATE_MODE"),
        ("revision", "PRIVATE_REVISION"),
        ("started_at", "2026-10-03T12:00:00+01:00"),
        ("finished_at", "2026-02-30T12:00:00Z"),
        ("primary_slot_count", True),
        ("total_slot_count", 99),
    ],
)
def test_malformed_canonical_values_return_static_error(
    field: str, value: object
) -> None:
    report = _batch()
    report[field] = value
    original = deepcopy(report)
    with pytest.raises(ValueError, match=_ERROR):
        render_report(report)
    assert report == original


@pytest.mark.parametrize("rates", [{}, {"secret": "PRIVATE_RATES"}, True, []])
def test_malformed_rates_return_static_error(rates: object) -> None:
    with pytest.raises(ValueError, match=_ERROR):
        render_report(_batch(), rates=cast(dict[str, object], rates))


@pytest.mark.parametrize("value", [True, None, {}, float("nan"), float("inf")])
def test_bad_inference_settings_return_static_error(value: object) -> None:
    report = _batch()
    _map(_map(report["manifest"])["model_config"])["temperature"] = value
    with pytest.raises(ValueError, match=_ERROR):
        render_report(report)


def test_formatter_errors_are_normalized_without_raw_input() -> None:
    with patch(
        "app.evaluation_markdown.table", side_effect=ValueError("PRIVATE_ERROR")
    ):
        with pytest.raises(ValueError, match=_ERROR) as caught:
            render_report(_batch())
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    assert "PRIVATE" not in str(caught.value)


def test_issue_rows_include_every_scoped_field() -> None:
    prepared = prepare_report(_batch())
    issue = _rows(prepared["issues"])[0]
    row = tuple(
        issue[key]
        for key in (
            "case_id",
            "repeat",
            "condition",
            "evidence_class",
            "quality_status",
            "execution_status",
            "reason_code",
        )
    )
    expected = table(
        (
            "Case",
            "Repeat",
            "Condition",
            "Evidence",
            "Quality status",
            "Execution status",
            "Reason",
        ),
        [row],
    )
    assert expected in render_report(_batch())
