import { useCallback, useEffect, useRef, useState } from "react";
import { isAbortError } from "./api";

const FAST_POLL_MS = 250;
const SLOW_POLL_MS = 750;
const FAST_POLL_WINDOW_MS = 10_000;

export function pollDelayMs(elapsedMs: number): number {
  return elapsedMs < FAST_POLL_WINDOW_MS ? FAST_POLL_MS : SLOW_POLL_MS;
}

type JobAck = { job_id: string };
type PolledJob = { status: string };

export type PolledJobState<Job, Body> = {
  job: Job | null;
  error: string | null;
  pending: boolean;
  submit: (body: Body) => Promise<void>;
  clear: () => void;
};

type PolledJobOptions<Job, Body> = {
  submitRequest: (body: Body, key: string, signal: AbortSignal) => Promise<JobAck>;
  fetchRequest: (jobId: string, signal: AbortSignal) => Promise<Job>;
  budgetMs: number;
  timeoutText: string;
  failedText: string | ((job: Job) => string);
  fallbackText: string;
  mapError: (caught: unknown, fallbackText: string) => string;
};

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

export function usePolledJob<Job extends PolledJob, Body>(
  options: PolledJobOptions<Job, Body>,
): PolledJobState<Job, Body> {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const attemptRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const keyRef = useRef<{ body: string; key: string } | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const abortActive = useCallback((): void => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    attemptRef.current += 1;
  }, []);

  useEffect(() => () => abortActive(), [abortActive]);

  const clear = useCallback((): void => {
    abortActive();
    keyRef.current = null;
    setJob(null);
    setError(null);
    setPending(false);
  }, [abortActive]);

  const submit = useCallback(
    async (body: Body): Promise<void> => {
      const options = optionsRef.current;
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
      }, options.budgetMs);
      try {
        const ack = await options.submitRequest(body, key, controller.signal);
        if (!live()) return;
        const ackedAt = Date.now();
        let current = await options.fetchRequest(ack.job_id, controller.signal);
        if (!live()) return;
        let lastSerialized = JSON.stringify(current);
        setJob(current);
        while (current.status === "queued" || current.status === "running") {
          await wait(pollDelayMs(Date.now() - ackedAt), controller.signal);
          if (!live()) return;
          current = await options.fetchRequest(ack.job_id, controller.signal);
          if (!live()) return;
          const serializedJob = JSON.stringify(current);
          if (serializedJob !== lastSerialized) {
            lastSerialized = serializedJob;
            setJob(current);
          }
        }
        if (!live()) return;
        const failed = current.status === "failed" || current.status === "rejected";
        if (failed) {
          keyRef.current = null;
        }
        setError(
          failed
            ? typeof options.failedText === "function"
              ? options.failedText(current)
              : options.failedText
            : null,
        );
        setPending(false);
      } catch (caught) {
        if (!live()) return;
        if (timedOut) {
          setError(options.timeoutText);
          setPending(false);
          return;
        }
        if (isAbortError(caught)) return;
        setError(options.mapError(caught, options.fallbackText));
        setPending(false);
      } finally {
        window.clearTimeout(timeoutId);
      }
    },
    [abortActive],
  );

  return { job, error, pending, submit, clear };
}
