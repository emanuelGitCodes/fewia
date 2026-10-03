from typing import cast

from app.evaluation_markdown_data import prepare_report
from app.evaluation_markdown_format import table
from app.evaluation_markdown_sections import render_quality
from app.evaluation_markdown_telemetry import render_telemetry
from app.evaluation_markdown_values import as_map, slots

_HASHES = (
    "manifest_hash corpus_hash catalog_hash system_prompt_hash "
    "baseline_system_prompt_hash model_config_hash"
).split()
_COVERAGE = (
    ("primary_slots", "Primary slots"),
    ("baseline_slots", "Baseline slots"),
    ("total_slots", "Total slots"),
    ("scored_slots", "Scored slots"),
    ("unassessed_slots", "Unassessed slots"),
    ("failed_slots", "Execution-failed slots"),
)


def _metadata(data: dict[str, object]) -> str:
    metadata = as_map(data["metadata"])
    rows: list[tuple[object, ...]] = [("Mode", data["mode"])]
    if data["mode"] == "legacy_coverage":
        fields = "version repeats metrics_status"
        rows.extend((key.replace("_", " "), metadata[key]) for key in fields.split())
    else:
        rows.extend(
            (label, metadata[key])
            for key, label in (
                ("revision", "Revision"),
                ("started_at", "UTC start"),
                ("finished_at", "UTC end"),
            )
        )
        manifest = as_map(metadata["manifest"])
        rows.append(("Manifest version", manifest["version"]))
        fields = "model_id region catalog_version"
        rows.extend((key.replace("_", " "), manifest[key]) for key in fields.split())
        config = as_map(manifest["model_config"])
        rows.extend(
            (key, config.get(key))
            for key in ("max_tokens", "temperature", "reasoning_effort")
        )
        conditions = cast(list[object], manifest["conditions"])
        rows.extend(("Condition", item) for item in conditions)
        rows.extend((key, manifest[key]) for key in _HASHES)
    return "## Metadata\n\n" + table(("Field", "Value"), rows)


def _findings(data: dict[str, object]) -> str:
    failures: list[tuple[object, ...]] = []
    for failure in slots(data["failures"]):
        checks = cast(list[object], failure["checks"])
        fields = "case_id repeat condition evidence_class assessment"
        identity = tuple(failure[key] for key in fields.split())
        for check in checks or [None]:
            failures.append((*identity, check))
    failure_section = (
        table(
            ("Case", "Repeat", "Condition", "Evidence", "Assessment", "Failed check"),
            failures,
        )
        if failures
        else "No quality failures were recorded."
    )
    issues = [
        tuple(
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
        for issue in slots(data["issues"])
    ]
    issue_section = (
        table(
            (
                "Case",
                "Repeat",
                "Condition",
                "Evidence",
                "Quality status",
                "Execution status",
                "Reason",
            ),
            issues,
        )
        if issues
        else "No assessment or execution issues were recorded."
    )
    return "\n\n".join(
        (
            "## Quality failures",
            failure_section,
            "## Assessment and execution issues",
            issue_section,
        )
    )


def render_report(
    report: dict[str, object], *, rates: dict[str, object] | None = None
) -> str:
    try:
        data = prepare_report(report, rates=rates)
        coverage = as_map(data["coverage"])
        parts = [
            "# Evaluation report",
            "## Coverage",
            table(
                ("Coverage", "Count"),
                [(label, coverage[key]) for key, label in _COVERAGE],
            ),
            "Scored includes passed and failed quality assessments "
            "in complete evaluation mode.",
        ]
        if data["mode"] == "legacy_coverage":
            parts.append(
                "Coverage-only mode. Legacy scored slots contain domain checks. "
                "The legacy runner does not assess complete model/provider quality."
            )
        parts.extend(
            (
                _metadata(data),
                "Quality is scoped by condition and evidence. Deterministic fixture, "
                "reference, and fake evidence does not establish real-model quality. "
                "Unknown values remain unknown. Empty findings do not establish "
                "that targets are met.",
                render_quality(cast(dict[str, object] | None, data["summary"])),
                _findings(data),
                render_telemetry(
                    cast(dict[str, object] | None, data["telemetry"]),
                    cast(dict[str, object] | None, data["cost"]),
                ),
            )
        )
        return "\n\n".join(parts) + "\n"
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError("Invalid evaluation report input") from None
