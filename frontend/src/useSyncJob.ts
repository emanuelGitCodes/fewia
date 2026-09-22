import { useCallback, useEffect, useRef, useState } from "react";
import { SHAPE_ERROR } from "./apiTypes";
import { submitSyncJob, type SyncJob } from "./syncApi";
import { pollSyncJob } from "./syncPolling";

const POST_MS = 15_000;
const EMPTY_ITEM = "Enter a sync item id.";
const SYNC_FAILURE = "The sync request failed. Start a new refresh.";
const TIMEOUT_ERROR =
  "The sync request is still processing and may continue. Retry checks the same request.";
const HTTP_FALLBACK = "The sync request failed. Check the item, then retry.";

type Request = { itemId: string; key: string; jobId: string | null };

function userError(caught: unknown): string {
  if (caught instanceof Error && (caught.message === TIMEOUT_ERROR || caught.message === SHAPE_ERROR)) {
    return caught.message;
  }
  return HTTP_FALLBACK;
}

export function useSyncJob(): {
  job: SyncJob | null;
  error: string | null;
  pending: boolean;
  start: (itemId: string) => Promise<void>;
  retry: () => Promise<void>;
  clear: () => void;
} {
  const [job, setJob] = useState<SyncJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const genRef = useRef(0);
  const controllerRef = useRef<AbortController | null>(null);
  const busyRef = useRef(false);
  const requestRef = useRef<Request | null>(null);
  const jobRef = useRef<SyncJob | null>(null);

  const abortActive = useCallback((): void => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    genRef.current += 1;
  }, []);

  useEffect(() => () => abortActive(), [abortActive]);

  const clear = useCallback((): void => {
    abortActive();
    busyRef.current = false;
    requestRef.current = null;
    jobRef.current = null;
    setJob(null);
    setError(null);
    setPending(false);
  }, [abortActive]);

  const run = useCallback(async (): Promise<void> => {
    abortActive();
    const controller = new AbortController();
    controllerRef.current = controller;
    const gen = genRef.current;
    const live = (): boolean => gen === genRef.current;
    const done = (nextError: string | null, nextJob?: SyncJob): void => {
      if (!live()) return;
      if (nextJob !== undefined) {
        jobRef.current = nextJob;
        setJob(nextJob);
      }
      setError(nextError);
      setPending(false);
      busyRef.current = false;
    };
    jobRef.current = null;
    setJob(null);
    setError(null);
    setPending(true);
    const snapshot = requestRef.current;
    if (snapshot === null) {
      done(HTTP_FALLBACK);
      return;
    }
    try {
      let jobId = snapshot.jobId;
      if (jobId === null) {
        const postController = new AbortController();
        const onAbort = (): void => postController.abort();
        let postTimedOut = false;
        const timer = setTimeout(() => {
          postTimedOut = true;
          postController.abort();
        }, POST_MS);
        controller.signal.addEventListener("abort", onAbort);
        if (controller.signal.aborted) postController.abort();
        try {
          const ack = await submitSyncJob(snapshot.itemId, snapshot.key, postController.signal);
          if (!live()) return;
          jobId = ack.job_id;
          requestRef.current = { ...snapshot, jobId };
        } catch (caught) {
          if (!live()) return;
          if (postTimedOut) {
            done(TIMEOUT_ERROR);
            return;
          }
          done(userError(caught));
          return;
        } finally {
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", onAbort);
        }
      }
      if (!live() || jobId === null) return;
      const current = await pollSyncJob(jobId, controller.signal, (update) => {
        if (!live()) return;
        jobRef.current = update;
        setJob(update);
      });
      if (!live()) return;
      done(current.status === "failed" ? SYNC_FAILURE : null, current);
    } catch (caught) {
      if (!live()) return;
      done(userError(caught));
    }
  }, [abortActive]);

  const start = useCallback(async (itemId: string): Promise<void> => {
    if (busyRef.current) return;
    if (itemId.trim().length === 0) {
      setError(EMPTY_ITEM);
      return;
    }
    busyRef.current = true;
    requestRef.current = { itemId, key: crypto.randomUUID(), jobId: null };
    await run();
  }, [run]);

  const retry = useCallback(async (): Promise<void> => {
    if (busyRef.current) return;
    const current = jobRef.current;
    if (requestRef.current === null || current?.status === "failed" || current?.status === "succeeded") {
      return;
    }
    busyRef.current = true;
    await run();
  }, [run]);

  return { job, error, pending, start, retry, clear };
}
