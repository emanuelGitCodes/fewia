import {
  HTTP_ERROR,
  SHAPE_ERROR,
  type GroceryConfig,
  type GroceryJob,
  type GroceryJobAck,
  type GroceryJobCreate,
} from "./apiTypes";
import { parseAck, parseConfig, parseJob } from "./apiValidation";

export type {
  CatalogItem,
  Diet,
  GroceryBudget,
  GroceryConfig,
  GroceryJob,
  GroceryJobAck,
  GroceryJobCreate,
  GroceryJobResult,
  GroceryPlan,
  GroceryRequest,
  JobStatus,
  MealRequest,
  PlanLine,
} from "./apiTypes";
export { HTTP_ERROR, SAMPLE_ESTIMATE_NOTICE, SHAPE_ERROR } from "./apiTypes";
export { parseAck, parseConfig, parseJob } from "./apiValidation";

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function abortable<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (signal === undefined) {
    return promise;
  }
  if (signal.aborted) {
    return Promise.reject(new DOMException("Aborted", "AbortError"));
  }
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort);
    promise.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

async function readJson(path: string, init: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await abortable(fetch(path, init), init.signal ?? undefined);
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new Error(HTTP_ERROR);
  }
  if (!response.ok) {
    throw new Error(HTTP_ERROR);
  }
  try {
    return (await abortable(response.json() as Promise<unknown>, init.signal ?? undefined)) as unknown;
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new Error(SHAPE_ERROR);
  }
}

export async function fetchConfig(signal?: AbortSignal): Promise<GroceryConfig> {
  return parseConfig(await readJson("/api/grocery/config", { method: "GET", signal }));
}

export async function submitJob(
  body: GroceryJobCreate,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<GroceryJobAck> {
  return parseAck(
    await readJson("/api/grocery/jobs", {
      method: "POST",
      signal,
      body: JSON.stringify(body),
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
    }),
  );
}

export async function fetchJob(jobId: string, signal?: AbortSignal): Promise<GroceryJob> {
  return parseJob(
    await readJson(`/api/grocery/jobs/${encodeURIComponent(jobId)}`, {
      method: "GET",
      signal,
    }),
  );
}
