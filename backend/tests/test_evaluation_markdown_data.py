import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

from app.evaluation_cost import estimate_cost
from app.evaluation_manifest import build_manifest
from app.evaluation_markdown_data import prepare_report
from app.evaluation_markdown_manifest import prepare_manifest
from app.evaluation_runner import run_evaluation
from app.evaluation_summary import summarize_evaluation
from app.evaluation_telemetry import summarize_telemetry

_ERROR = "^Invalid evaluation report input$"
_MODEL = "us.amazon.nova-2-lite-v1:0"


def _map(value: object) -> dict[str, object]:
    assert type(value) is dict
    return cast(dict[str, object], value)


def _rows(value: object) -> list[dict[str, object]]:
    assert type(value) is list
    return cast(list[dict[str, object]], value)


def _slot(
    *,
    condition: str = "tool_enabled",
    evidence: object = "real_bedrock",
    repeat: int = 1,
    status: str = "completed",
) -> dict[str, object]:
    return {
        "case_id": "A02",
        "repeat": repeat,
        "condition": condition,
        "driver": "no_tool" if condition == "no_tool" else "model",
        "status": status,
        "elapsed_seconds": 2.0,
        "assessments": {},
        "report": None,
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


def _assess(slot: dict[str, object]) -> None:
    slot["assessments"] = {
        "plan": {
            "status": "passed",
            "scope": "final_plan",
            "constraint_violations": [],
        },
        "outcome": {
            "status": "passed",
            "scope": "final_turn",
            "clarification_required": False,
            "clarification_correct": None,
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


def test_canonical_results_come_from_actual_primary_and_baseline_helpers() -> None:
    primary = _slot()
    baseline = _slot(condition="no_tool")
    _assess(baseline)
    report = _batch([primary], [baseline])
    report.update(summary={"total_slots": 999}, telemetry={}, cost={"status": "free"})
    pricing = _rates()
    result = prepare_report(report, rates=pricing)
    slots = [primary, baseline]
    summary = summarize_evaluation(slots)
    telemetry = summarize_telemetry(slots)
    assert result["summary"] == summary
    assert result["telemetry"] == telemetry
    assert result["cost"] == estimate_cost(
        telemetry, pricing, model_id=_MODEL, region="us-east-1"
    )
    assert _map(result["cost"])["estimated_usd"] == "0.01166"
    assert result["coverage"] == {
        "primary_slots": 1,
        "baseline_slots": 1,
        "total_slots": 2,
        "scored_slots": 1,
        "unassessed_slots": 1,
        "failed_slots": 0,
    }
    assert result["mode"] == "complete_evaluation"
    public_manifest = _map(_map(result["metadata"])["manifest"])
    assert public_manifest == {
        key: value
        for key, value in _map(report["manifest"]).items()
        if key != "catalog"
    }
    assert public_manifest == prepare_manifest(report["manifest"])
    assert result["failures"] == []


def test_failures_reuse_summary_metrics_and_keep_execution_separate() -> None:
    failed_quality = _slot(condition="no_tool")
    _assess(failed_quality)
    _map(_map(failed_quality["assessments"])["outcome"]).update(
        status="failed", checks={"completed_request": False}
    )
    failed_execution = _slot(status="failed")
    result = prepare_report(_batch([failed_execution], [failed_quality]))
    groups = _rows(_map(result["summary"])["groups"])
    expected = [
        item
        for group in groups
        for item in cast(list[object], _map(group["metrics"])["known_failures"])
    ]
    assert result["failures"] == expected
    assert len(expected) == 1
    assert _map(result["coverage"])["failed_slots"] == 1
    assert _map(result["coverage"])["scored_slots"] == 2


def test_legacy_fixture_has_42_scored_and_48_unassessed_without_metrics() -> None:
    path = Path(__file__).parent / "evaluation" / "scenarios.json"
    legacy = run_evaluation(_map(json.loads(path.read_text(encoding="utf-8"))))
    result = prepare_report(legacy)
    assert result["mode"] == "legacy_coverage"
    assert result["coverage"] == {
        "primary_slots": 90,
        "baseline_slots": 0,
        "total_slots": 90,
        "scored_slots": 42,
        "unassessed_slots": 48,
        "failed_slots": 0,
    }
    assert result["metadata"] == {
        "version": "grocery-eval-v1",
        "repeats": 3,
        "metrics_status": "unassessed",
    }
    assert all(result[key] is None for key in ("summary", "telemetry", "cost"))
    assert result["failures"] == []


def test_legacy_nested_reports_are_never_read_or_copied() -> None:
    class Unreadable(dict[str, object]):
        def get(self, key: str, default: object = None) -> object:
            raise AssertionError("nested report accessed")

        def __iter__(self) -> object:
            raise AssertionError("nested report traversed")

    report: dict[str, object] = {
        "version": "grocery-eval-v1",
        "repeats": 3,
        "slot_count": 2,
        "metrics_status": "unassessed",
        "slots": [
            {"status": "scored", "report": Unreadable(answer="PRIVATE_LEGACY")},
            {"status": "failed", "report": object()},
        ],
        "profile": "PRIVATE_PROFILE",
    }
    result = prepare_report(report)
    assert _map(result["coverage"])["failed_slots"] == 1
    assert "PRIVATE_" not in repr(result)


@pytest.mark.parametrize("field", ["primary_slot_count", "total_slot_count"])
@pytest.mark.parametrize("value", [True, False, -1, 0, 2, 1.0, "1", None])
def test_canonical_count_types_and_lengths_are_validated(
    field: str, value: object
) -> None:
    report = _batch()
    report[field] = value
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(report)


@pytest.mark.parametrize("value", [True, -1, 1, "0", 0.0, None])
def test_legacy_count_is_validated(value: object) -> None:
    report: dict[str, object] = {
        "version": "grocery-eval-v1",
        "repeats": 3,
        "slot_count": value,
        "metrics_status": "unassessed",
        "slots": [],
    }
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(report)


@pytest.mark.parametrize("value", [None, True, [], "PRIVATE_REPORT", 1])
def test_malformed_report_types_have_static_errors(value: object) -> None:
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(cast(dict[str, object], value))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slots", None),
        ("slots", {}),
        ("slots", [None]),
        ("baseline_slots", None),
        ("baseline_slots", [True]),
        ("manifest", None),
        ("manifest", []),
        ("mode", "PRIVATE_MODE"),
        ("mode", True),
        ("revision", "A" * 40),
        ("revision", "a" * 39),
        ("revision", True),
        ("started_at", "2026-10-03T12:00:00"),
        ("started_at", "2026-10-03T12:00:00+01:00"),
        ("started_at", "2026-10-03T11:00:00-00:00"),
        ("finished_at", "2026-02-30T12:00:00Z"),
        ("finished_at", "2026-10-03T11:59:59Z"),
        ("finished_at", "PRIVATE_TIME"),
    ],
)
def test_malformed_batch_fields_have_static_errors(field: str, value: object) -> None:
    report = _batch()
    report[field] = value
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_id", None),
        ("model_id", "PRIVATE MODEL TEXT"),
        ("region", "PRIVATE_REGION"),
        ("region", []),
        ("model_config", None),
        ("model_config", []),
        ("conditions", "tool_enabled"),
        ("conditions", ["PRIVATE_CONDITION"]),
        ("conditions", [True]),
        ("version", {"secret": "PRIVATE_SECRET"}),
        ("catalog_version", "PRIVATE VERSION TEXT"),
        ("manifest_hash", "PRIVATE_HASH"),
        ("catalog_hash", "B" * 64),
    ],
)
def test_malformed_public_manifest_values_are_rejected(
    field: str, value: object
) -> None:
    report = _batch()
    _map(report["manifest"])[field] = value
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(report)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_tokens", True),
        ("max_tokens", 0),
        ("max_tokens", 4097),
        ("temperature", True),
        ("temperature", float("nan")),
        ("temperature", float("inf")),
        ("temperature", -0.01),
        ("reasoning_effort", "PRIVATE_EFFORT"),
        ("reasoning_effort", []),
    ],
)
def test_allowed_inference_values_are_validated(field: str, value: object) -> None:
    report = _batch()
    _map(_map(report["manifest"])["model_config"])[field] = value
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(report)


def test_unknown_telemetry_and_missing_rates_remain_unknown() -> None:
    slot = _slot()
    turn = _rows(_map(slot["observation"])["turns"])[0]
    turn.update(usage=None, provider_calls="PRIVATE_CALLS", elapsed_seconds=None)
    result = prepare_report(_batch([slot]))
    group = _rows(_map(result["telemetry"])["groups"])[0]
    assert group["input_tokens"] is None
    assert group["unknown_usage_slots"] == 1
    assert _map(group["provider_calls"])["total"] is None
    assert _map(result["cost"])["status"] == "unknown"
    assert _map(result["cost"])["estimated_usd"] is None
    assert "PRIVATE_CALLS" not in repr(result)


@pytest.mark.parametrize("rates", [{}, {"secret": "PRIVATE_RATES"}, True, []])
def test_invalid_rates_have_static_errors(rates: object) -> None:
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(_batch(), rates=cast(dict[str, object], rates))


def test_rate_model_mismatch_does_not_publish_cost() -> None:
    rates = _rates()
    rates["model_id"] = "another-model"
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(_batch(), rates=rates)


def test_condition_and_evidence_groups_stay_separate_without_inferred_evidence() -> (
    None
):
    slots = [
        _slot(),
        _slot(evidence="deterministic_fake_provider", repeat=2),
        _slot(evidence="PRIVATE_EVIDENCE", repeat=3),
    ]
    slots[2]["case_id"] = "P05"
    _map(slots[2]["observation"])["case_id"] = "P05"
    baseline = _slot(condition="no_tool")
    result = prepare_report(_batch(slots, [baseline]), rates=_rates())
    labels = [
        (group["condition"], group["evidence_class"])
        for group in _rows(_map(result["summary"])["groups"])
    ]
    assert labels == [
        ("no_tool", "real_bedrock"),
        ("tool_enabled", "deterministic_fake_provider"),
        ("tool_enabled", "real_bedrock"),
        ("tool_enabled", "unknown"),
    ]
    telemetry = _rows(_map(result["telemetry"])["groups"])
    assert [(row["condition"], row["evidence_class"]) for row in telemetry] == labels
    assert _map(result["cost"])["status"] == "unknown"
    assert _map(result["coverage"])["scored_slots"] == 0
    assert "PRIVATE_EVIDENCE" not in repr(result)
    assert "local_postgresql" not in repr(result)
    assert "injection_success" not in repr(result)


def test_missing_evidence_is_unknown_in_summary_telemetry_and_cost() -> None:
    slot = _slot()
    _map(slot["observation"]).pop("evidence_class")
    result = prepare_report(_batch([slot]), rates=_rates())
    for section in ("summary", "telemetry", "cost"):
        group = _rows(_map(result[section])["groups"])[0]
        assert group["evidence_class"] == "unknown"
    assert _map(result["cost"])["estimated_usd"] is None


def test_raw_text_secrets_and_unknown_fields_are_omitted() -> None:
    slot = _slot()
    slot.update(report={"answer": "PRIVATE_ANSWER"}, exception="PRIVATE_EXCEPTION")
    observation = _map(slot["observation"])
    observation.update(reason="PRIVATE_REASON", hidden_reasoning="PRIVATE_REASONING")
    _rows(observation["turns"])[0].update(
        result={"answer": "PRIVATE_TURN"},
        message="PRIVATE_MESSAGE",
        exception="PRIVATE_TURN_EXCEPTION",
        hidden_reasoning="PRIVATE_HIDDEN",
    )
    slot["assessments"] = {
        "outcome": {
            "status": "unassessed",
            "scope": "final_turn",
            "unassessed_reasons": ["PRIVATE_REASON_CODE"],
        }
    }
    report = _batch([slot])
    report.update(profile="PRIVATE_PROFILE", database_url="PRIVATE_DATABASE")
    manifest = _map(report["manifest"])
    manifest.update(
        private_catalog={"body": "PRIVATE_CATALOG"},
        credentials="PRIVATE_KEY",
        private_config={"secret": "PRIVATE_CONFIG", "profile": "PRIVATE_NESTED"},
    )
    result = prepare_report(report)
    assert "PRIVATE_" not in repr(result)
    public = _map(_map(result["metadata"])["manifest"])
    assert set(_map(public["model_config"])) == {
        "max_tokens",
        "temperature",
        "reasoning_effort",
    }
    assert "catalog" not in public
    assert "credentials" not in public
    assert public == prepare_manifest(manifest)
    assert set(result) == {
        "mode",
        "coverage",
        "metadata",
        "summary",
        "telemetry",
        "cost",
        "failures",
    }


def test_inputs_and_rates_are_immutable_on_success_and_failure() -> None:
    report, rates = _batch(), _rates()
    original_report, original_rates = deepcopy(report), deepcopy(rates)
    result = prepare_report(report, rates=rates)
    assert report == original_report
    assert rates == original_rates
    public = _map(_map(result["metadata"])["manifest"])
    _map(public["model_config"]).clear()
    cast(list[object], public["conditions"]).clear()
    _rows(_map(result["telemetry"])["groups"]).clear()
    assert report == original_report
    rates["source_url"] = "https://user:PRIVATE_RATE_SECRET@pricing.example.org"
    original_rates = deepcopy(rates)
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(report, rates=rates)
    assert report == original_report
    assert rates == original_rates


def test_duplicate_slot_identity_across_primary_and_baseline_is_rejected() -> None:
    slot = _slot()
    with pytest.raises(ValueError, match=_ERROR):
        prepare_report(_batch([slot], [deepcopy(slot)]))


def test_empty_batch_returns_zero_coverage_without_claiming_target_success() -> None:
    result = prepare_report(_batch([], []))
    assert all(value == 0 for value in _map(result["coverage"]).values())
    assert _map(result["cost"])["status"] == "unknown"
    assert result["failures"] == []
    assert "target_achieved" not in repr(result)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_invalid_provenance(report: dict[str, object]) -> None:
    original = deepcopy(report)
    with pytest.raises(ValueError, match=_ERROR) as caught:
        prepare_report(report)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__
    assert report == original


@pytest.mark.parametrize("field", ["model_config_hash", "manifest_hash"])
def test_model_settings_change_rejects_each_stale_hash(field: str) -> None:
    report = _batch()
    manifest = _map(report["manifest"])
    config = _map(manifest["model_config"])
    stale_hash = manifest[field]
    config["max_tokens"] = 2048
    manifest["model_config_hash"] = _digest(config)
    manifest["manifest_hash"] = _digest(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )
    manifest[field] = stale_hash
    if field == "model_config_hash":
        manifest["manifest_hash"] = _digest(
            {key: value for key, value in manifest.items() if key != "manifest_hash"}
        )
    _assert_invalid_provenance(report)


@pytest.mark.parametrize(
    "field",
    [
        "catalog",
        "manifest_hash",
        "corpus_hash",
        "catalog_hash",
        "system_prompt_hash",
        "baseline_system_prompt_hash",
        "model_config_hash",
    ],
)
def test_missing_manifest_provenance_is_rejected(field: str) -> None:
    report = _batch()
    del _map(report["manifest"])[field]
    _assert_invalid_provenance(report)


def test_unknown_inference_config_is_rejected_with_matching_hashes() -> None:
    report = _batch()
    manifest = _map(report["manifest"])
    config = _map(manifest["model_config"])
    config["unsupported_setting"] = "PRIVATE_CONFIG"
    manifest["model_config_hash"] = _digest(config)
    manifest["manifest_hash"] = _digest(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )
    _assert_invalid_provenance(report)
