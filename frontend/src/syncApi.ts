import { parseAck, readJson } from "./api";
import {
  SHAPE_ERROR,
  isNonemptyString,
  isRecord,
  isSafeInteger,
  isStatus,
  isString,
  type GroceryJobAck,
  type JobStatus,
} from "./apiTypes";

export type SyncItem = {
  id: string;
  last_synced_at: string | null;
};

export type SyncJob = {
  id: string;
  status: JobStatus;
  result: { source: "plaid_sandbox"; changed_count: number } | null;
  error_code: string | null;
};

const ITEM_KEYS: ReadonlySet<string> = new Set(["id", "last_synced_at"]);
const JOB_KEYS: ReadonlySet<string> = new Set(["id", "status", "result", "error_code"]);
const RESULT_KEYS: ReadonlySet<string> = new Set(["source", "changed_count"]);
const STAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const ID_MAX = 256;
const ITEMS_PATH = "/api/grocery/sync/items";
const JOBS_PATH = "/api/grocery/sync/jobs";

function fail(): never {
  throw new Error(SHAPE_ERROR);
}

function exactKeys(value: Record<string, unknown>, keys: ReadonlySet<string>): boolean {
  const actual = Object.keys(value);
  return actual.length === keys.size && actual.every((key) => keys.has(key));
}

function isPublicId(value: unknown): value is string {
  return isNonemptyString(value) && value.trim() === value && value.length <= ID_MAX;
}

function isStamp(value: unknown): value is string {
  return isString(value) && STAMP.test(value) && !Number.isNaN(Date.parse(value));
}

function parseItem(value: unknown): SyncItem {
  if (!isRecord(value) || !exactKeys(value, ITEM_KEYS) || !isPublicId(value.id)) {
    fail();
  }
  const stamp = value.last_synced_at;
  if (stamp !== null && !isStamp(stamp)) {
    fail();
  }
  return { id: value.id, last_synced_at: stamp };
}

function parseResult(value: unknown): SyncJob["result"] {
  if (value === null) {
    return null;
  }
  if (
    !isRecord(value) ||
    !exactKeys(value, RESULT_KEYS) ||
    value.source !== "plaid_sandbox" ||
    !isSafeInteger(value.changed_count) ||
    value.changed_count < 0
  ) {
    fail();
  }
  return { source: "plaid_sandbox", changed_count: value.changed_count };
}

export function parseSyncItems(value: unknown): SyncItem[] {
  if (!Array.isArray(value)) {
    fail();
  }
  return value.map(parseItem);
}

export function parseSyncJob(value: unknown): SyncJob {
  if (!isRecord(value) || !exactKeys(value, JOB_KEYS) || !isPublicId(value.id) || !isStatus(value.status)) {
    fail();
  }
  if (value.error_code !== null && !isString(value.error_code)) {
    fail();
  }
  const result = parseResult(value.result);
  if (value.status === "succeeded" && result === null) {
    fail();
  }
  return { id: value.id, status: value.status, result, error_code: value.error_code };
}

export async function fetchSyncItems(signal?: AbortSignal): Promise<SyncItem[]> {
  return parseSyncItems(await readJson(ITEMS_PATH, { method: "GET", cache: "no-store", signal }));
}

export async function submitSyncJob(
  itemId: string,
  key: string,
  signal?: AbortSignal,
): Promise<GroceryJobAck> {
  return parseAck(
    await readJson(JOBS_PATH, {
      method: "POST",
      signal,
      body: JSON.stringify({ item_id: itemId }),
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": key,
      },
    }),
  );
}

export async function fetchSyncJob(jobId: string, signal?: AbortSignal): Promise<SyncJob> {
  return parseSyncJob(
    await readJson(`${JOBS_PATH}/${encodeURIComponent(jobId)}`, {
      method: "GET",
      cache: "no-store",
      signal,
    }),
  );
}
