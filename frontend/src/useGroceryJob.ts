import { fetchJob, submitJob } from "./api";
import type { GroceryJob, GroceryJobCreate } from "./api";
import { modelJobFailureText } from "./apiTypes";
import { usePolledJob } from "./usePolledJob";
import type { PolledJobState } from "./usePolledJob";

const HTTP_FALLBACK =
  "The grocery request failed. Check meals, servings, and budget, then retry.";

export function useGroceryJob(): PolledJobState<GroceryJob, GroceryJobCreate> {
  return usePolledJob<GroceryJob, GroceryJobCreate>({
    submitRequest: submitJob,
    fetchRequest: fetchJob,
    budgetMs: 6 * 60 * 1000,
    timeoutText:
      "The grocery request is still processing. Retry checks the same request.",
    failedText: (job) =>
      modelJobFailureText(job) ?? "The grocery request failed. Try again.",
    fallbackText: HTTP_FALLBACK,
    mapError: (caught, fallbackText) =>
      caught instanceof Error ? caught.message : fallbackText,
  });
}
