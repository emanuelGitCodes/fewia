from copy import deepcopy

import pytest

from app.evaluation_metric_counts import (
    sum_binary_metrics,
    sum_claim_counts,
    summarize_assessment_statuses,
)

_CLAIM_FIELDS = (
    "supported_count",
    "assessed_count",
    "unsupported_count",
    "unknown_count",
    "supported_refusal_count",
)
_COUNT_ERROR = "metric counts MUST be nonnegative integers with coherent totals"


def _claims(
    supported: int = 0,
    assessed: int = 0,
    unsupported: int = 0,
    unknown: int = 0,
    refusals: int = 0,
) -> dict[str, object]:
    return {
        "scope": "public_output_only",
        "supported_count": supported,
        "assessed_count": assessed,
        "unsupported_count": unsupported,
        "unknown_count": unknown,
        "supported_refusal_count": refusals,
    }


def test_assessment_statuses_count_only_supplied_statuses() -> None:
    statuses: list[object] = [
        "passed",
        "failed",
        "failed",
        "unassessed",
        "not_applicable",
    ]
    assert summarize_assessment_statuses(statuses) == {
        "passed": 1,
        "failed": 2,
        "unassessed": 1,
        "not_applicable": 1,
        "numerator": 1,
        "denominator": 3,
        "pass_rate": 1 / 3,
    }


def test_missing_assessment_needs_explicit_unassessed_status() -> None:
    assert summarize_assessment_statuses([]) == {
        "passed": 0,
        "failed": 0,
        "unassessed": 0,
        "not_applicable": 0,
        "numerator": 0,
        "denominator": 0,
        "pass_rate": None,
    }
    explicit = summarize_assessment_statuses(["unassessed"])
    assert explicit["unassessed"] == 1
    assert explicit["passed"] == 0
    assert explicit["pass_rate"] is None


def test_inapplicable_statuses_do_not_add_assessed_denominator() -> None:
    summary = summarize_assessment_statuses(["not_applicable", "unassessed"])
    assert summary["denominator"] == 0
    assert summary["pass_rate"] is None


@pytest.mark.parametrize("status", [True, 1, None, "completed", "", [], {}])
def test_malformed_status_has_static_error(status: object) -> None:
    with pytest.raises(ValueError) as error:
        summarize_assessment_statuses([status])
    assert str(error.value) == (
        "assessment status MUST be passed, failed, unassessed, or not_applicable"
    )


def test_binary_metrics_sum_unequal_denominators() -> None:
    metrics: list[dict[str, object]] = [
        {"numerator": 1, "denominator": 1, "rate": 1.0},
        {"numerator": 1, "denominator": 9, "rate": 1 / 9},
    ]
    assert sum_binary_metrics(metrics) == {
        "numerator": 2,
        "denominator": 10,
        "rate": 0.2,
    }


@pytest.mark.parametrize("field", ["numerator", "denominator"])
@pytest.mark.parametrize("value", [True, False, -1, 1.0, "raw-marker", None])
def test_binary_metrics_reject_invalid_counts(field: str, value: object) -> None:
    metric: dict[str, object] = {"numerator": 0, "denominator": 1}
    metric[field] = value
    with pytest.raises(ValueError) as error:
        sum_binary_metrics([metric])
    assert str(error.value) == _COUNT_ERROR


@pytest.mark.parametrize("field", ["numerator", "denominator"])
def test_binary_metrics_reject_missing_counts(field: str) -> None:
    metric: dict[str, object] = {"numerator": 0, "denominator": 1}
    del metric[field]
    with pytest.raises(ValueError, match="^metric counts MUST"):
        sum_binary_metrics([metric])


@pytest.mark.parametrize("denominator", [0, 1])
def test_binary_metrics_reject_impossible_counts(denominator: int) -> None:
    with pytest.raises(ValueError, match="^metric counts MUST"):
        sum_binary_metrics([{"numerator": 2, "denominator": denominator}])


def test_binary_metrics_keep_large_integer_totals_exact() -> None:
    count = 2**100 + 1
    assert sum_binary_metrics(
        [
            {"numerator": count, "denominator": count * 2},
            {"numerator": 2, "denominator": 4},
        ]
    ) == {"numerator": count + 2, "denominator": count * 2 + 4, "rate": 0.5}


@pytest.mark.parametrize("metrics", [[], [{"numerator": 0, "denominator": 0}]])
def test_binary_zero_denominators_yield_null_rate(
    metrics: list[dict[str, object]],
) -> None:
    assert sum_binary_metrics(metrics) == {
        "numerator": 0,
        "denominator": 0,
        "rate": None,
    }


def test_claim_counts_sum_unequal_denominators_and_unknowns() -> None:
    assert sum_claim_counts(
        [_claims(1, 1, unknown=2), _claims(1, 9, 8, unknown=3, refusals=2)]
    ) == {
        "scope": "public_output_only",
        "supported_count": 2,
        "assessed_count": 10,
        "unsupported_count": 8,
        "unknown_count": 5,
        "supported_refusal_count": 2,
        "support_rate": 0.2,
        "conservative_support_rate": 2 / 15,
    }


@pytest.mark.parametrize("field", _CLAIM_FIELDS)
@pytest.mark.parametrize("value", [True, False, -1, 0.0, "raw-marker", None])
def test_claim_counts_reject_invalid_counts(field: str, value: object) -> None:
    claim = _claims()
    claim[field] = value
    with pytest.raises(ValueError) as error:
        sum_claim_counts([claim])
    assert str(error.value) == _COUNT_ERROR


@pytest.mark.parametrize("field", _CLAIM_FIELDS)
def test_claim_counts_reject_missing_counts(field: str) -> None:
    claim = _claims()
    del claim[field]
    with pytest.raises(ValueError, match="^metric counts MUST"):
        sum_claim_counts([claim])


@pytest.mark.parametrize("scope", ["final_plan", "", None, True, [], {}])
def test_claim_counts_reject_wrong_scope(scope: object) -> None:
    claim = _claims(refusals=3)
    claim["status"] = "not_applicable"
    claim["scope"] = scope
    with pytest.raises(ValueError) as error:
        sum_claim_counts([_claims(1, 1), claim])
    assert str(error.value) == _COUNT_ERROR


def test_claim_counts_reject_missing_scope() -> None:
    claim = _claims()
    del claim["scope"]
    with pytest.raises(ValueError) as error:
        sum_claim_counts([claim])
    assert str(error.value) == _COUNT_ERROR


@pytest.mark.parametrize("claim", [_claims(1, 0), _claims(0, 1), _claims(1, 1, 1)])
def test_claim_counts_reject_incoherent_totals(claim: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="^metric counts MUST"):
        sum_claim_counts([claim])


def test_claim_counts_validate_each_record_before_summing() -> None:
    with pytest.raises(ValueError, match="^metric counts MUST"):
        sum_claim_counts([_claims(1, 0), _claims(0, 1)])


def test_supported_refusals_stay_outside_factual_support() -> None:
    refusal = _claims(refusals=3)
    refusal["status"] = "not_applicable"
    assert sum_claim_counts([refusal]) == {
        "scope": "public_output_only",
        "supported_count": 0,
        "assessed_count": 0,
        "unsupported_count": 0,
        "unknown_count": 0,
        "supported_refusal_count": 3,
        "support_rate": None,
        "conservative_support_rate": None,
    }
    combined = sum_claim_counts([refusal, _claims(1, 2, 1)])
    assert combined["supported_refusal_count"] == 3
    assert combined["support_rate"] == 0.5
    assert combined["conservative_support_rate"] == 0.5


def test_unknown_claims_remain_visible_without_assessed_claims() -> None:
    summary = sum_claim_counts([_claims(unknown=4, refusals=2)])
    assert summary["unknown_count"] == 4
    assert summary["support_rate"] is None
    assert summary["conservative_support_rate"] == 0.0


def test_empty_claims_yield_zero_counts_and_null_rates() -> None:
    summary = sum_claim_counts([])
    assert all(summary[field] == 0 for field in _CLAIM_FIELDS)
    assert summary["scope"] == "public_output_only"
    assert summary["support_rate"] is None
    assert summary["conservative_support_rate"] is None


def test_inputs_remain_unchanged_and_raw_fields_are_not_copied() -> None:
    statuses: list[object] = ["passed", "unassessed"]
    metrics: list[dict[str, object]] = [
        {
            "numerator": 1,
            "denominator": 2,
            "rate": "raw-marker",
            "answer": "raw-marker",
            "report": {"arbitrary": ["raw-marker"]},
        }
    ]
    claims = [_claims(1, 2, 1, unknown=3, refusals=4)]
    claims[0]["answer"] = "raw-marker"
    claims[0]["report"] = {"arbitrary": ["raw-marker"]}
    snapshot = deepcopy((statuses, metrics, claims))
    outputs = (
        summarize_assessment_statuses(statuses),
        sum_binary_metrics(metrics),
        sum_claim_counts(claims),
    )
    assert (statuses, metrics, claims) == snapshot
    for output in outputs:
        assert "answer" not in output
        assert "report" not in output
        assert "raw-marker" not in repr(output)
