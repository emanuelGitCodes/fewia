import { useCallback, useEffect, useState } from "react";
import { isAbortError } from "./api";
import type { ProviderCapabilities } from "./apiTypes";
import { fetchProviders } from "./providerApi";

const PROVIDER_MS = 20_000;
const PROVIDER_UNAVAILABLE =
  "The provider configuration is unavailable. Retry the provider request.";

export function useProviderCapabilities(): {
  capabilities: ProviderCapabilities | null;
  pending: boolean;
  error: string | null;
  retry: () => void;
} {
  const [capabilities, setCapabilities] = useState<ProviderCapabilities | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const retry = useCallback((): void => {
    setRetryTick((tick) => tick + 1);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    let timedOut = false;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, PROVIDER_MS);
    setPending(true);
    setError(null);
    void fetchProviders(controller.signal)
      .then(
        (value) => {
          if (!cancelled) {
            setCapabilities(value);
            setError(null);
            setPending(false);
          }
        },
        (caught: unknown) => {
          if (!cancelled && !(isAbortError(caught) && !timedOut)) {
            setCapabilities(null);
            setError(PROVIDER_UNAVAILABLE);
            setPending(false);
          }
        },
      )
      .finally(() => window.clearTimeout(timeoutId));
    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [retryTick]);

  return { capabilities, pending, error, retry };
}

export type ProviderCapabilitiesState = ReturnType<typeof useProviderCapabilities>;
