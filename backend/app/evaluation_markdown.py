from app.evaluation_report_values import (
    INVALID,
    count,
    group,
    label,
    optional_count,
    seconds,
)
from app.evaluation_report_values import (
    revision as render_revision,
)
from app.evaluation_score_values import as_map

_UNASSESSED = "unassessed"
_METHOD = "nearest-rank"
_EXEC = ("scored", "observed", "failed", "unassessed", "invalid")
_CHECK = ("assessed", "passed", "failed", "invalid", "outside_scope")
_EVIDENCE = ("deterministic_fake_provider", "real_bedrock", "unknown")
_LATENCY_NOTE = "Latency sums user-turn elapsed times for each observation."
_SCOPE_NOTE = (
    "Final-plan checks cover the last structured plan only. "
    "Fake evidence and live evidence are not interchangeable."
)
_REFERENCE_NOTE = (
    "Structured-reference checks use structured inputs. "
    "They compare the final result only. "
    "They do not measure language understanding or earlier-turn quality."
)


def _body(value: object) -> dict[str, object]:
    mapped = as_map(value)
    if mapped is None:
        raise ValueError(INVALID)
    return mapped


def _need(body: dict[str, object], key: str) -> object:
    if key not in body:
        raise ValueError(INVALID)
    return body[key]


def _table(headers: tuple[str, ...], rows: tuple[tuple[str, ...], ...]) -> str:
    sep = tuple("---" for _ in headers)
    return "\n".join("| " + " | ".join(item) + " |" for item in (headers, sep, *rows))


def render_evaluation_markdown(
    summary: object,
    telemetry: object,
    *,
    revision: str,
    model_id: str | None,
    source_region: str | None,
) -> str:
    record = _body(summary)
    measures = _body(telemetry)
    if _need(record, "metrics_status") != _UNASSESSED:
        raise ValueError(INVALID)
    if _need(measures, "percentile_method") != _METHOD:
        raise ValueError(INVALID)
    execution = group(_need(record, "execution_counts"), _EXEC)
    fixture = group(_need(record, "fixture_checks"), _CHECK)
    control = group(_need(record, "controlled_checks"), _CHECK)
    final_plan = group(_need(record, "final_plan_checks"), _CHECK)
    observation = group(
        _need(_body(_need(record, "evidence_breakdown")), "observation"),
        _EVIDENCE,
    )
    check_rows: list[tuple[str, ...]] = [
        ("fixture", *(fixture[key] for key in _CHECK)),
        ("control", *(control[key] for key in _CHECK)),
        ("final-plan", *(final_plan[key] for key in _CHECK)),
    ]
    notes = [_SCOPE_NOTE]
    if "reference_checks" in record:
        reference = group(record["reference_checks"], _CHECK)
        check_rows.append(("structured-reference", *(reference[key] for key in _CHECK)))
        notes.extend(["", _REFERENCE_NOTE])
    return "\n".join(
        [
            "# FEWIA evaluation record",
            "",
            f"Revision: {render_revision(revision)}",
            f"Model: {label(model_id)}",
            f"Source region: {label(source_region)}",
            "",
            "Global quality: UNASSESSED",
            "",
            "## Execution counts",
            "",
            _table(_EXEC, (tuple(execution[key] for key in _EXEC),)),
            "",
            "## Check groups",
            "",
            _table(("group", *_CHECK), tuple(check_rows)),
            "",
            "## Observation evidence",
            "",
            _table(_EVIDENCE, (tuple(observation[key] for key in _EVIDENCE),)),
            "",
            "## Latency",
            "",
            f"Sample count: {count(_need(measures, 'latency_sample_count'))}",
            f"Method: {_METHOD}",
            f"p50: {seconds(_need(measures, 'p50_latency_seconds'))}",
            f"p95: {seconds(_need(measures, 'p95_latency_seconds'))}",
            "",
            _LATENCY_NOTE,
            "",
            "## Tokens",
            "",
            f"known_usage_slots: {count(_need(measures, 'known_usage_slots'))}",
            f"unknown_usage_slots: {count(_need(measures, 'unknown_usage_slots'))}",
            f"known_input_tokens: {count(_need(measures, 'known_input_tokens'))}",
            f"known_output_tokens: {count(_need(measures, 'known_output_tokens'))}",
            f"input_tokens: {optional_count(_need(measures, 'input_tokens'))}",
            f"output_tokens: {optional_count(_need(measures, 'output_tokens'))}",
            "",
            *notes,
            "",
        ]
    )
