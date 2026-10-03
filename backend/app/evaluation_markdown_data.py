from datetime import datetime
from typing import cast

from app.evaluation_cost import estimate_cost
from app.evaluation_manifest import _MODEL_ID
from app.evaluation_markdown_manifest import prepare_manifest
from app.evaluation_markdown_values import as_map as _map
from app.evaluation_markdown_values import pick as _pick
from app.evaluation_markdown_values import require as _require
from app.evaluation_markdown_values import slots as _slots
from app.evaluation_markdown_values import text as _text
from app.evaluation_summary import summarize_evaluation
from app.evaluation_summary_task_validation import classify_slot
from app.evaluation_telemetry import summarize_telemetry

_ERROR = "Invalid evaluation report input"
_UTC = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|\+00:00)"
)


def prepare_report(
    report: dict[str, object], *, rates: dict[str, object] | None = None
) -> dict[str, object]:
    try:
        report = _map(report)
        primary = _slots(report.get("slots"))
        failures: list[object] = []
        summary: dict[str, object] | None = None
        telemetry: dict[str, object] | None = None
        cost: dict[str, object] | None = None
        if "mode" not in report:
            mode = "legacy_coverage"
            counts = {"slot_count": len(primary)}
            repeats = report.get("repeats")
            _require(type(repeats) is int and repeats > 0)
            _text(report.get("metrics_status"), "unassessed")
            metadata: dict[str, object] = {
                "version": _text(report.get("version"), r"[A-Za-z0-9._-]{1,128}"),
                "repeats": repeats,
                "metrics_status": "unassessed",
            }
            for slot in primary:
                _text(slot.get("status"), "scored|unassessed|failed")
            baseline: list[dict[str, object]] = []
            scored = sum(slot["status"] == "scored" for slot in primary)
            unassessed = sum(slot["status"] == "unassessed" for slot in primary)
            failed = sum(slot["status"] == "failed" for slot in primary)
        else:
            mode = _text(report.get("mode"), "complete_evaluation")
            baseline = _slots(report.get("baseline_slots"))
            slots = primary + baseline
            counts = {
                "primary_slot_count": len(primary),
                "total_slot_count": len(slots),
            }
            manifest = prepare_manifest(report.get("manifest"))
            metadata = {"manifest": manifest, "mode": mode}
            metadata["revision"] = _text(report.get("revision"), r"[0-9a-f]{40}")
            timestamps: list[datetime] = []
            for key in ("started_at", "finished_at"):
                value = _text(report.get(key), _UTC)
                timestamps.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
                metadata[key] = value
            _require(timestamps[0] <= timestamps[1])
            summary = summarize_evaluation(slots)
            facts = [classify_slot(slot) for slot in slots]
            safe_slots: list[dict[str, object]] = []
            for slot, fact in zip(slots, facts, strict=True):
                observation = _map(slot["observation"])
                if observation.get("model_id") is not None:
                    _text(observation["model_id"], _MODEL_ID.pattern)
                safe = _pick(slot, "case_id repeat condition elapsed_seconds")
                public = _pick(observation, "model_id status turns")
                public["evidence_class"] = fact.evidence_class
                safe_slots.append({**safe, "observation": public})
            telemetry = summarize_telemetry(safe_slots)
            cost = estimate_cost(
                telemetry,
                rates,
                model_id=cast(str, manifest["model_id"]),
                region=cast(str, manifest["region"]),
            )
            scored = sum(fact.quality_status in ("passed", "failed") for fact in facts)
            unassessed = len(slots) - scored
            failed = sum(fact.execution_status == "failed" for fact in facts)
            for group in cast(list[dict[str, object]], summary["groups"]):
                failures += cast(list[object], _map(group["metrics"])["known_failures"])
        for key, expected in counts.items():
            _require(type(report.get(key)) is int and report[key] == expected)
        return {
            "mode": mode,
            "metadata": metadata,
            "summary": summary,
            "telemetry": telemetry,
            "cost": cost,
            "failures": failures,
            "coverage": {
                "primary_slots": len(primary),
                "baseline_slots": len(baseline),
                "total_slots": len(primary) + len(baseline),
                "scored_slots": scored,
                "unassessed_slots": unassessed,
                "failed_slots": failed,
            },
        }
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError(_ERROR) from None
