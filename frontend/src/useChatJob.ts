import { fetchChatJob, submitChatJob } from "./chatApi";
import type { ChatJob, ChatJobCreate } from "./chatTypes";
import { usePolledJob } from "./usePolledJob";
import type { PolledJobState } from "./usePolledJob";

const HTTP_FALLBACK =
  "The chat request failed. Check the message and budget, then retry.";

export function useChatJob(): PolledJobState<ChatJob, ChatJobCreate> {
  return usePolledJob<ChatJob, ChatJobCreate>({
    submitRequest: submitChatJob,
    fetchRequest: fetchChatJob,
    budgetMs: 8 * 60 * 1000,
    timeoutText:
      "The chat request is still processing and may continue. Retry checks the same request.",
    failedText: "The chat request failed. Retry checks the same request.",
    fallbackText: HTTP_FALLBACK,
    mapError: (_caught, fallbackText) => fallbackText,
  });
}
