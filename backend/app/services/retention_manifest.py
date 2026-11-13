"""Build bounded, opaque retention manifests."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

VERSION = "0018:operator-retention:1"
MAX_ROWS = 10_000
MAX_ROW_BYTES = 262_144
MAX_SCAN_BYTES = 8_388_608
MAX_NODES = 100_000
TABLES = (
    "jobs",
    "job_outbox",
    "job_effects",
    "model_call_reservations",
    "plan_proposals",
    "plan_revisions",
    "grocery_evidence",
    "security_intents",
    "quota_counters",
)
DELETE_ORDER = (
    "model_call_reservations",
    "job_effects",
    "job_outbox",
    "plan_proposals",
    "security_intents",
    "quota_counters",
    "jobs",
    "plan_revisions",
    "grocery_evidence",
)
RETAINED = (
    "identity",
    "legacy_health_finance_environment",
    "plaid",
    "paused_handoffs",
    "credentials_and_pairing_generations",
)
EXTERNAL_RETAINED = (
    "backups",
    "file_artifacts",
    "queues",
    "provider_copies",
    "other_external_records",
)
_REFERENCE = re.compile(
    r"(?<![0-9a-z])(?:[0-9a-f]{64}|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?![0-9a-z])",
    re.IGNORECASE,
)
Row = dict[str, object]


class RetentionError(Exception):
    """Report a fixed failure without database or row details."""

    def __init__(self) -> None:
        super().__init__("Operator retention refused.")


def validate_owner(owner_id: int) -> None:
    if type(owner_id) is not int or not 0 < owner_id <= 9_223_372_036_854_775_807:
        raise RetentionError()


def validate_digest(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise RetentionError()


def utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise RetentionError()
    return value.astimezone(UTC)


def _normal(value: object, depth: int, budget: list[int]) -> object:
    budget[0] -= 1
    if depth > 24 or budget[0] < 0:
        raise RetentionError()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, datetime):
        return utc(value).isoformat()
    if isinstance(value, (date, UUID)):
        return str(value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RetentionError()
        return {key: _normal(item, depth + 1, budget) for key, item in value.items()}
    if isinstance(value, list):
        return [_normal(item, depth + 1, budget) for item in value]
    raise RetentionError()


def canonical(value: object) -> bytes:
    try:
        data = json.dumps(
            _normal(value, 0, [MAX_NODES]),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (ValueError, TypeError, RecursionError):
        raise RetentionError() from None
    if len(data) > MAX_SCAN_BYTES:
        raise RetentionError()
    return data


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _strings(value: object) -> list[str]:
    normalized = _normal(value, 0, [MAX_NODES])
    pending = [normalized]
    strings: list[str] = []
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            strings.append(item.lower())
        elif isinstance(item, dict):
            strings.extend(str(key).lower() for key in item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return strings


def references(value: object, identifiers: set[str]) -> bool:
    for text in _strings(value):
        if text in identifiers:
            return True
        if any(
            match.group().lower() in identifiers for match in _REFERENCE.finditer(text)
        ):
            return True
    return False


def _old(row: Row, column: str, cutoff: datetime) -> bool:
    return utc(row.get(column)) < cutoff


@dataclass(frozen=True)
class Manifest:
    digest: str
    counts: dict[str, int]
    blockers: tuple[str, ...]
    candidates: dict[str, list[Row]]
    database_id: str
    owner_id: int
    before: datetime

    def public(self) -> dict[str, object]:
        return {
            "version": VERSION,
            "digest": self.digest,
            "target_identity": self.database_id,
            "owner_id": self.owner_id,
            "before": self.before.isoformat(),
            "counts": self.counts,
            "blockers": list(self.blockers),
            "retained_database_categories": list(RETAINED),
            "outside_database_retained": list(EXTERNAL_RETAINED),
            "external_erasure": False,
        }


def build_manifest(
    rows: dict[str, list[Row]],
    *,
    owner_id: int,
    before: datetime,
    now: datetime,
    database_id: str,
    owner_status: str,
    context_digest: str | None = None,
) -> Manifest:
    validate_owner(owner_id)
    before, now = utc(before), utc(now)
    validate_digest(database_id)
    if context_digest is not None:
        validate_digest(context_digest)
    if before > now or set(rows) != set(TABLES):
        raise RetentionError()
    blockers: set[str] = set()
    if owner_status not in {"active", "disabled"}:
        blockers.add("owner_unavailable")
    scanned_bytes = 0
    if sum(len(group) for group in rows.values()) > MAX_ROWS:
        raise RetentionError()
    for group in rows.values():
        for row in group:
            size = len(canonical(row))
            if size > MAX_ROW_BYTES:
                raise RetentionError()
            scanned_bytes += size
            if scanned_bytes > MAX_SCAN_BYTES:
                raise RetentionError()
    for table, columns in {
        "jobs": ("payload", "result"),
        "plan_revisions": ("snapshot",),
        "grocery_evidence": ("snapshot",),
        "plan_proposals": ("apply_constraints",),
        "security_intents": ("details",),
    }.items():
        for row in rows[table]:
            for column in columns:
                value = row.get(column)
                if value is None and column in {"result", "apply_constraints"}:
                    continue
                if not isinstance(value, dict):
                    raise RetentionError()
    for row in rows["plan_proposals"]:
        if not isinstance(row.get("operations"), list):
            raise RetentionError()
    candidates: dict[str, list[Row]] = {name: [] for name in TABLES}
    owned_jobs = [row for row in rows["jobs"] if row["user_id"] == owner_id]
    for row in owned_jobs:
        leased = row.get("lease_expires_at") is not None or bool(
            row.get("has_lease_token")
        )
        if leased:
            blockers.add("job_lease")
        if row["status"] in {"queued", "running"}:
            blockers.add("active_jobs")
        elif row["status"] not in {"succeeded", "failed"}:
            blockers.add("unknown_job_state")
        elif _old(row, "created_at", before) and not leased:
            candidates["jobs"].append(row)
    job_ids = {str(row["id"]) for row in candidates["jobs"]}
    owner_job_ids = {str(row["id"]) for row in owned_jobs}
    for row in rows["job_outbox"]:
        if str(row["job_id"]) in owner_job_ids and row["published_at"] is None:
            blockers.add("unpublished_work")
        if str(row["job_id"]) in job_ids and row["published_at"] is not None:
            if _old(row, "published_at", before):
                candidates["job_outbox"].append(row)
    for row in rows["job_effects"]:
        if str(row["job_id"]) in job_ids and row["user_id"] == owner_id:
            if _old(row, "created_at", before):
                candidates["job_effects"].append(row)
    for row in rows["model_call_reservations"]:
        live = utc(row["slot_deadline"]) > now
        day = row["utc_day"]
        if row["user_id"] == owner_id and live:
            blockers.add("active_provider_reservation")
        if (
            str(row["job_id"]) in job_ids
            and row["user_id"] == owner_id
            and isinstance(day, date)
            and not isinstance(day, datetime)
            and day < now.date()
            and not live
            and _old(row, "started_at", before)
            and _old(row, "slot_deadline", before)
            and (row["finished_at"] is None or _old(row, "finished_at", before))
        ):
            candidates["model_call_reservations"].append(row)
    for table in ("plan_revisions", "grocery_evidence"):
        candidates[table] = [
            row
            for row in rows[table]
            if row["user_id"] == owner_id and _old(row, "created_at", before)
        ]
    candidates["plan_proposals"] = [
        row
        for row in rows["plan_proposals"]
        if row["user_id"] == owner_id
        and row["status"] in {"applied", "discarded"}
        and _old(row, "created_at", before)
        and _old(row, "updated_at", before)
    ]
    for row in rows["security_intents"]:
        if row["user_id"] != owner_id:
            continue
        ambiguous = row["state"] in {"claimed", "uncertain"} or any(
            value in {"claimed", "uncertain", "dispatching", "in_flight"}
            for value in _strings(row["details"])
        )
        if row["kind"] == "cart_confirmation" and ambiguous:
            blockers.add("ambiguous_cart_intent")
        if (
            not ambiguous
            and row["state"] in {"pending", "consumed", "succeeded", "failed"}
            and _old(row, "created_at", before)
            and _old(row, "updated_at", before)
            and _old(row, "expires_at", min(before, now))
        ):
            candidates["security_intents"].append(row)
    candidates["quota_counters"] = [
        row
        for row in rows["quota_counters"]
        if row["scope"] == "user"
        and row["scope_key"] == owner_id
        and _old(row, "minute_start", before)
        and _old(row, "expires_at", min(before, now))
    ]
    identifiers: set[str] = set()
    for table, group in candidates.items():
        for row in group:
            for key in ("id", "digest", "input_digest", "input_hash"):
                if isinstance(row.get(key), (str, UUID)):
                    identifiers.add(str(row[key]).lower())
            if table in {"grocery_evidence", "plan_revisions"}:
                identifiers.add(content_hash(row["snapshot"]))
    candidate_hashes = {
        table: {content_hash(row) for row in group}
        for table, group in candidates.items()
    }
    for table, group in rows.items():
        for row in group:
            if content_hash(row) not in candidate_hashes[table]:
                if references(row, identifiers):
                    blockers.add("retained_dependency")
    state = {
        "version": VERSION,
        "database": database_id,
        "context": context_digest,
        "owner": owner_id,
        "owner_status": owner_status,
        "before": before,
        "utc_day": now.date(),
        "candidates": {
            name: sorted(values) for name, values in candidate_hashes.items()
        },
        "scanned_state": {
            name: sorted(content_hash(row) for row in group)
            for name, group in rows.items()
        },
        "blockers": sorted(blockers),
    }
    return Manifest(
        content_hash(state),
        {name: len(group) for name, group in candidates.items()},
        tuple(sorted(blockers)),
        candidates,
        database_id,
        owner_id,
        before,
    )
