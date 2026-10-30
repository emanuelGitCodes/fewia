import { useRef } from "react";
import { fetchChatJob, submitChatJob } from "./chatApi";
import type { ChatJob, ChatJobCreate } from "./chatTypes";
import { usePolledJob } from "./usePolledJob";
import type { PolledJobState } from "./usePolledJob";

const HTTP_FALLBACK =
  "The chat request failed. Check the message and budget, then retry.";

export function useChatJob(
  locationId: string | null = null,
): PolledJobState<ChatJob, ChatJobCreate> {
  // Each read uses the latest store, so a store change does not restart a job.
  const locationRef = useRef(locationId);
  locationRef.current = locationId;
  return usePolledJob<ChatJob, ChatJobCreate>({
    submitRequest: submitChatJob,
    fetchRequest: (id, signal) => fetchChatJob(id, signal, locationRef.current),
    budgetMs: 8 * 60 * 1000,
    timeoutText:
      "The chat request is still processing and may continue. Retry checks the same request.",
    failedText: "The chat request failed. Retry checks the same request.",
    fallbackText: HTTP_FALLBACK,
    mapError: (_caught, fallbackText) => fallbackText,
  });
}
