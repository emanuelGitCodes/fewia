import re
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import cast

from app.evaluation_dispatch import EvaluationRuntime, run_slot
from app.evaluation_manifest import _copy_object, build_manifest
from app.evaluation_matrix import prepare_matrix
from app.evaluation_summary_task_validation import classify_slot


def _check_evidence(
    result: dict[str, object],
    manifest: dict[str, object],
    evidence_class: str,
) -> None:
    if result["driver"] not in ("model", "no_tool"):
        return
    observation = cast(dict[str, object], result["observation"])
    prompt_key = (
        "system_prompt_hash"
        if result["driver"] == "model"
        else "baseline_system_prompt_hash"
    )
    pinned = {
        "model_id": manifest["model_id"],
        "evidence_class": evidence_class,
        "catalog_version": manifest["catalog_version"],
        "system_prompt_hash": manifest[prompt_key],
    }
    if "catalog_hash" in observation:
        pinned["catalog_hash"] = manifest["catalog_hash"]
    if any(observation.get(key) != value for key, value in pinned.items()):
        result.update(status="failed", reason_code="evidence_contract_mismatch")


def run_evaluation_batch(
    corpus: dict[str, object],
    runtime: EvaluationRuntime,
    *,
    region: str,
    model_config: dict[str, object],
    revision: str,
    on_slot: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("revision MUST be a canonical 40-character hex SHA")
    if runtime.evidence_class not in ("real_bedrock", "deterministic_fake_provider"):
        raise ValueError("invalid evaluation evidence class")
    if on_slot is not None and not callable(on_slot):
        raise ValueError("invalid evaluation callback")
    frozen = _copy_object(corpus)
    matrix = prepare_matrix(frozen)
    keys = {(slot.case_id, slot.repeat, slot.condition) for slot in matrix}
    conditions = [slot.condition for slot in matrix]
    if (
        len(matrix) != 138
        or len(keys) != 138
        or any(value in ("no_tool", "deterministic") for value in conditions[:90])
        or conditions[90:123] != ["no_tool"] * 33
        or conditions[123:] != ["deterministic"] * 15
    ):
        raise ValueError("invalid evaluation matrix")
    manifest = build_manifest(
        frozen,
        model_id=runtime.model_id,
        region=region,
        model_config=model_config,
    )
    evidence_class = runtime.evidence_class
    started_at = datetime.now(UTC).isoformat()
    primary: list[dict[str, object]] = []
    baselines: list[dict[str, object]] = []
    quality: list[str] = []
    for slot in matrix:
        result = run_slot(slot, runtime)
        _check_evidence(result, manifest, evidence_class)
        quality.append(classify_slot(result).quality_status)
        target = (
            baselines if slot.condition in ("no_tool", "deterministic") else primary
        )
        target.append(result)
        if on_slot is not None:
            try:
                on_slot(deepcopy(result))
            except Exception:  # noqa: BLE001
                raise RuntimeError("evaluation slot callback failed") from None
    assessed = sum(status in ("passed", "failed") for status in quality)
    metrics_status = (
        "assessed"
        if assessed == len(quality)
        else "partial"
        if assessed
        else "unassessed"
    )
    return {
        "version": frozen["version"],
        "repeats": frozen["repeats"],
        "mode": "complete_evaluation",
        "manifest": manifest,
        "revision": revision,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "slot_count": len(primary),
        "primary_slot_count": len(primary),
        "total_slot_count": len(primary) + len(baselines),
        "slots": primary,
        "baseline_slots": baselines,
        "metrics_status": metrics_status,
    }
