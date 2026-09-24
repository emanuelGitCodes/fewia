import { readJson } from "./api";
import {
  SHAPE_ERROR,
  SPOONACULAR_COST_NOTICE,
  isRecord,
  isSafeInteger,
  type SupermarketEstimate,
} from "./apiTypes";

const ESTIMATE_KEYS: ReadonlySet<string> = new Set(["total_cents", "notice"]);

export function parseSupermarketEstimate(value: unknown): SupermarketEstimate {
  if (!isRecord(value)) {
    throw new Error(SHAPE_ERROR);
  }
  const keys = Object.keys(value);
  if (keys.length !== ESTIMATE_KEYS.size || keys.some((key) => !ESTIMATE_KEYS.has(key))) {
    throw new Error(SHAPE_ERROR);
  }
  const total = value.total_cents;
  if (total !== null && !(isSafeInteger(total) && total >= 0)) {
    throw new Error(SHAPE_ERROR);
  }
  if (value.notice !== SPOONACULAR_COST_NOTICE) {
    throw new Error(SHAPE_ERROR);
  }
  return { total_cents: total, notice: SPOONACULAR_COST_NOTICE };
}

export async function fetchSupermarketEstimate(
  jobId: string,
  signal?: AbortSignal,
): Promise<SupermarketEstimate> {
  return parseSupermarketEstimate(
    await readJson(`/api/grocery/jobs/${encodeURIComponent(jobId)}/supermarket-estimate`, {
      method: "GET",
      cache: "no-store",
      signal,
    }),
  );
}
