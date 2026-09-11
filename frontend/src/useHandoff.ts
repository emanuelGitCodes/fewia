import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError } from "./api";
import { SHAPE_ERROR } from "./apiTypes";
import { createHandoff, retryHandoff } from "./handoffApi";
import type { HandoffView } from "./handoffTypes";

const HTTP_FALLBACK =
  "The shopping link request failed. Check the plan, then retry.";

function failureMessage(caught: unknown): string {
  return caught instanceof Error && caught.message === SHAPE_ERROR ? SHAPE_ERROR : HTTP_FALLBACK;
}

export function useHandoff(): {
  view: HandoffView | null;
  error: string | null;
  pending: boolean;
  start: (jobId: string) => Promise<void>;
  retry: () => Promise<void>;
  clear: () => void;
} {
  const [view, setView] = useState<HandoffView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const attemptRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);

  const abortActive = useCallback((): void => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    attemptRef.current += 1;
  }, []);

  useEffect(() => {
    return () => {
      abortActive();
    };
  }, [abortActive]);

  const clear = useCallback((): void => {
    abortActive();
    setView(null);
    setError(null);
    setPending(false);
  }, [abortActive]);

  const start = useCallback(
    async (jobId: string): Promise<void> => {
      abortActive();
      const controller = new AbortController();
      controllerRef.current = controller;
      const attempt = attemptRef.current;
      const live = (): boolean => attempt === attemptRef.current;
      setView(null);
      setError(null);
      setPending(true);
      try {
        const next = await createHandoff(jobId, controller.signal);
        if (!live()) {
          return;
        }
        setView(next);
        setError(null);
        setPending(false);
      } catch (caught) {
        if (!live() || isAbortError(caught)) {
          return;
        }
        setView(null);
        setError(failureMessage(caught));
        setPending(false);
      }
    },
    [abortActive],
  );

  const retry = useCallback(async (): Promise<void> => {
    if (view === null || !view.retry_allowed) {
      return;
    }
    const id = view.id;
    const attempts = view.attempts;
    abortActive();
    const controller = new AbortController();
    controllerRef.current = controller;
    const attempt = attemptRef.current;
    const live = (): boolean => attempt === attemptRef.current;
    setPending(true);
    try {
      const next = await retryHandoff(id, attempts, controller.signal);
      if (!live()) {
        return;
      }
      setView(next);
      setError(null);
      setPending(false);
    } catch (caught) {
      if (!live() || isAbortError(caught)) {
        return;
      }
      setError(failureMessage(caught));
      setPending(false);
    }
  }, [abortActive, view]);

  return { view, error, pending, start, retry, clear };
}
