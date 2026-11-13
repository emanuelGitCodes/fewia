import hashlib
import json
from pathlib import Path

import pytest

from app.evaluation_export import export_mode, export_record, render_export_markdown

_CORPORA = Path(__file__).parent / "evaluation"
_MARKER = "ARBITRARY_PRIVATE_EXPORT_MARKER"


@pytest.mark.parametrize("suite", ["scenarios", "conversation"])
def test_detailed_export_requires_both_flags_and_exact_corpus_bytes(suite: str) -> None:
    corpus = (_CORPORA / f"{suite}.json").read_bytes()
    assert export_mode(corpus, suite, detailed=False, synthetic=False)
    assert export_mode(corpus, suite, detailed=True, synthetic=True)
    for detailed, synthetic in ((False, True), (True, False), (True, True)):
        altered = corpus + b" " if detailed and synthetic else corpus
        with pytest.raises(ValueError, match="Invalid evaluation export input"):
            export_mode(altered, suite, detailed=detailed, synthetic=synthetic)
    assert not export_mode(corpus + b" ", suite, detailed=False, synthetic=False)
    other = "scenarios" if suite == "conversation" else "conversation"
    with pytest.raises(ValueError):
        export_mode(corpus, other, detailed=True, synthetic=True)


def test_default_projection_drops_private_data_and_unknown_fields_recursively() -> None:
    record: dict[str, object] = {
        "scenario_id": "C01",
        "status": "completed",
        "provider_requests": 2,
        "latency_ms": 15,
        "usage": {"input": 7, "output": 4},
        "result": {"answer": _MARKER},
        "plan": {"total": 87421},
        "input": {"count": 119883},
        "user_turn": _MARKER,
        "tools": [
            {
                "name": "get_meal",
                "outcome": "success",
                "inputs": {"recipe_id": _MARKER},
                "unknown": _MARKER,
            }
        ],
        "verdict": {"ok": True, "reasons": [_MARKER], "unknown": _MARKER},
        "budget": {"available_cents": 87421},
        "user_id": 119883,
        "unknown": {"status": _MARKER},
        _MARKER: "completed",
        "reply_sha256": hashlib.sha256(_MARKER.encode()).hexdigest(),
    }
    original = json.dumps(record, sort_keys=True)
    clean = export_record(record, recognized=True)
    encoded = json.dumps(clean, sort_keys=True)
    markdown = render_export_markdown(clean)
    assert _MARKER not in encoded + markdown
    for private in (
        "inputs",
        "recipe_id",
        "result",
        "user_turn",
        "available_cents",
        "user_id",
        "reply_sha256",
        "unknown",
    ):
        assert private not in encoded
    assert clean["usage"] == {"input": 7, "output": 4}
    assert clean["provider_requests"] == 2
    assert clean["scenario_id"] == "C01"
    assert "plan" not in clean
    assert "input" not in clean
    assert json.dumps(record, sort_keys=True) == original


def test_unrecognized_corpus_cannot_export_raw_scenario_identifiers() -> None:
    record: dict[str, object] = {
        "scenario_id": "C01",
        "case_id": _MARKER,
        "status": _MARKER,
    }
    clean = export_record(record, recognized=False)
    assert clean == {"scenario_id": None, "case_id": None, "status": None}


def test_detailed_projection_bounds_data_and_removes_secrets_and_reasoning() -> None:
    record: dict[str, object] = {
        "result": {
            "answer": "Synthetic comparison",
            "authorization": _MARKER,
            "reasoningContent": {"text": _MARKER},
            "thinking": _MARKER,
            "api_key": _MARKER,
        },
        "text": "Bearer fake-private-token",
        "large": "x" * 10000,
        "usage": {"inputTokens": 5, "outputTokens": 2},
    }
    clean = export_record(
        record,
        recognized=True,
        detailed=True,
        synthetic=True,
        corpus_bytes=(_CORPORA / "scenarios.json").read_bytes(),
        suite="scenarios",
    )
    encoded = json.dumps(clean)
    assert "Synthetic comparison" in encoded
    assert _MARKER not in encoded
    assert "fake-private-token" not in encoded
    assert "reasoningContent" not in encoded
    assert clean["usage"] == {"inputTokens": 5, "outputTokens": 2}
    assert len(str(clean["large"])) <= 4096


def test_detailed_projection_rejects_unrecognized_input() -> None:
    with pytest.raises(ValueError, match="Invalid evaluation export input"):
        export_record({"result": _MARKER}, recognized=False, detailed=True)


@pytest.mark.parametrize(
    ("detailed", "synthetic", "data"),
    [(True, False, b"{}"), (True, True, b"{}"), (False, True, b"{}")],
)
def test_direct_helper_cannot_trust_a_recognized_boolean(
    detailed: bool, synthetic: bool, data: bytes
) -> None:
    with pytest.raises(ValueError, match="Invalid evaluation export input"):
        export_record(
            {"result": _MARKER},
            recognized=True,
            detailed=detailed,
            synthetic=synthetic,
            corpus_bytes=data,
            suite="scenarios",
        )


def test_public_projection_rejects_allowed_names_in_wrong_structures() -> None:
    private_number = 87421
    record: dict[str, object] = {
        "status": private_number,
        "usage": {"input": {"count": private_number}, "output": 2},
        "tools": [{"name": {"count": private_number}, "outcome": "success"}],
        "observation": {
            "turns": [{"usage": {"inputTokens": {"total": private_number}}}]
        },
        "verdict": {"reasons": [{"count": private_number}]},
    }
    encoded = json.dumps(export_record(record, recognized=True))
    assert str(private_number) not in encoded
    assert '"output": 2' in encoded


def test_conversation_public_report_preserves_typed_aggregate_metrics() -> None:
    report: dict[str, object] = {
        "counts": {"turns_expected": 123, "turns_recorded": 122},
        "checks": {"gold": {"passed": 120, "total": 123, "rate": 0.9756}},
        "latency_ms": {"p50": 100, "p95": 350},
        "cost": {
            "turns_priced": 123,
            "per_turn_usd": "0.000125",
            "total_usd": "0.015375",
        },
        "grounding": {
            "prose_attempts": 90,
            "grounded_replies": 85,
            "unsupported_numbers": 3,
        },
    }
    assert export_record(report, recognized=False) == report
