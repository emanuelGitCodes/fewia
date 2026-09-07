import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchJob,
  isAbortError,
  submitJob,
  type GroceryJob,
  type GroceryJobCreate,
} from "./api";

const POLL_MS = 750;
const BUDGET_MS = 6 * 60 * 1000;
const TIMEOUT_ERROR =
  "The grocery request is still processing. Retry checks the same request.";
const HTTP_FALLBACK =
  "The grocery request failed. Check meals, servings, and budget, then retry.";

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    if (signal.aborted) {
      onAbort();
      return;
    }
    signal.addEventListener("abort", onAbort);
  });
}

export function useGroceryJob(): {
  job: GroceryJob | null;
  error: string | null;
  pending: boolean;
  submit: (body: GroceryJobCreate) => Promise<void>;
  clear: () => void;
} {
  const [job, setJob] = useState<GroceryJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const attemptRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const keyRef = useRef<{ body: string; key: string } | null>(null);

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
    keyRef.current = null;
    setJob(null);
    setError(null);
    setPending(false);
  }, [abortActive]);

  const submit = useCallback(
    async (body: GroceryJobCreate): Promise<void> => {
      const serialized = JSON.stringify(body);
      const prior = keyRef.current;
      const key =
        prior !== null && prior.body === serialized ? prior.key : crypto.randomUUID();
      keyRef.current = { body: serialized, key };
      abortActive();
      const controller = new AbortController();
      controllerRef.current = controller;
      const attempt = attemptRef.current;
      const live = (): boolean => attempt === attemptRef.current;
      setJob(null);
      setError(null);
      setPending(true);
      let timedOut = false;
      const timeoutId = window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, BUDGET_MS);
      try {
        const ack = await submitJob(body, key, controller.signal);
        if (!live()) {
          return;
        }
        let current = await fetchJob(ack.job_id, controller.signal);
        if (!live()) {
          return;
        }
        setJob(current);
        while (current.status === "queued" || current.status === "running") {
          await wait(POLL_MS, controller.signal);
          if (!live()) {
            return;
          }
          current = await fetchJob(ack.job_id, controller.signal);
          if (!live()) {
            return;
          }
          setJob(current);
        }
        if (!live()) {
          return;
        }
        if (current.status === "failed") {
          setError("The grocery request failed. Retry checks the same request.");
        } else {
          setError(null);
        }
        setPending(false);
      } catch (caught) {
        if (!live()) {
          return;
        }
        if (timedOut) {
          setError(TIMEOUT_ERROR);
          setPending(false);
          return;
        }
        if (isAbortError(caught)) {
          return;
        }
        const message = caught instanceof Error ? caught.message : HTTP_FALLBACK;
        setError(message);
        setPending(false);
      } finally {
        window.clearTimeout(timeoutId);
      }
    },
    [abortActive],
  );

  return { job, error, pending, submit, clear };
}
