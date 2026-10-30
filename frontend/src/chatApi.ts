import { parseAck, readJson, type GroceryJobAck } from "./api";
import type { ChatJob, ChatJobCreate } from "./chatTypes";
import { parseChatJob } from "./chatValidation";

export async function submitChatJob(
  body: ChatJobCreate,
  key: string,
  signal?: AbortSignal,
): Promise<GroceryJobAck> {
  return parseAck(
    await readJson("/api/grocery/chat/jobs", {
      method: "POST",
      signal,
      body: JSON.stringify(body),
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": key,
      },
    }),
  );
}

const LOCATION_ID = /^[0-9A-Za-z]{8}$/;

export async function fetchChatJob(
  id: string,
  signal?: AbortSignal,
  locationId?: string | null,
): Promise<ChatJob> {
  const query =
    locationId != null && LOCATION_ID.test(locationId)
      ? `?location_id=${encodeURIComponent(locationId)}`
      : "";
  return parseChatJob(
    await readJson(`/api/grocery/chat/jobs/${encodeURIComponent(id)}${query}`, {
      method: "GET",
      signal,
    }),
  );
}
