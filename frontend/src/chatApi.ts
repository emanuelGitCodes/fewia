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

export async function fetchChatJob(id: string, signal?: AbortSignal): Promise<ChatJob> {
  return parseChatJob(
    await readJson(`/api/grocery/chat/jobs/${encodeURIComponent(id)}`, {
      method: "GET",
      signal,
    }),
  );
}
