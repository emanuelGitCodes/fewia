import { readJson } from "./api";
import { SHAPE_ERROR, isSafeInteger } from "./apiTypes";
import { parseHandoffView, type HandoffView } from "./handoffTypes";

export async function createHandoff(
  jobId: string,
  signal?: AbortSignal,
): Promise<HandoffView> {
  return parseHandoffView(
    await readJson("/api/grocery/handoffs", {
      method: "POST",
      signal,
      body: JSON.stringify({ job_id: jobId }),
      headers: { "Content-Type": "application/json" },
    }),
  );
}

export async function fetchHandoff(id: string, signal?: AbortSignal): Promise<HandoffView> {
  return parseHandoffView(
    await readJson(`/api/grocery/handoffs/${encodeURIComponent(id)}`, {
      method: "GET",
      signal,
    }),
  );
}

export async function retryHandoff(
  id: string,
  expectedAttempt: number,
  signal?: AbortSignal,
): Promise<HandoffView> {
  if (!isSafeInteger(expectedAttempt) || expectedAttempt < 1) {
    throw new Error(SHAPE_ERROR);
  }
  return parseHandoffView(
    await readJson(`/api/grocery/handoffs/${encodeURIComponent(id)}/retry`, {
      method: "POST",
      signal,
      body: JSON.stringify({ expected_attempt: expectedAttempt }),
      headers: { "Content-Type": "application/json" },
    }),
  );
}
