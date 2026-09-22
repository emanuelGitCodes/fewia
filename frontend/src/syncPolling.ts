import { fetchSyncJob, type SyncJob } from "./syncApi";

const POLL_MS = 2000;
const BUDGET_MS = 6 * 60 * 1000;
const TIMEOUT_ERROR =
  "The sync request is still processing and may continue. Retry checks the same request.";

function abortErr(): DOMException {
  return new DOMException("Aborted", "AbortError");
}

function abortable<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  if (signal.aborted) {
    void promise.then(
      () => undefined,
      () => undefined,
    );
    return Promise.reject(abortErr());
  }
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      signal.removeEventListener("abort", onAbort);
      reject(abortErr());
    };
    signal.addEventListener("abort", onAbort);
    promise.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) {
    return Promise.reject(abortErr());
  }
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      reject(abortErr());
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal.addEventListener("abort", onAbort);
  });
}

function stop(signal: AbortSignal): never {
  if (signal.aborted) {
    throw abortErr();
  }
  throw new Error(TIMEOUT_ERROR);
}

export async function pollSyncJob(
  jobId: string,
  signal: AbortSignal,
  onUpdate: (job: SyncJob) => void,
): Promise<SyncJob> {
  const internal = new AbortController();
  let timedOut = false;
  const onCallerAbort = (): void => {
    internal.abort();
  };
  const timeoutId = setTimeout(() => {
    timedOut = true;
    internal.abort();
  }, BUDGET_MS);
  signal.addEventListener("abort", onCallerAbort);
  if (signal.aborted) {
    internal.abort();
  }
  try {
    for (;;) {
      if (internal.signal.aborted) {
        stop(signal);
      }
      let job: SyncJob;
      try {
        job = await abortable(fetchSyncJob(jobId, internal.signal), internal.signal);
      } catch (error) {
        if (signal.aborted || timedOut) {
          stop(signal);
        }
        throw error;
      }
      if (signal.aborted || timedOut) {
        stop(signal);
      }
      onUpdate(job);
      if (job.status === "succeeded" || job.status === "failed") {
        return job;
      }
      try {
        await wait(POLL_MS, internal.signal);
      } catch (error) {
        if (signal.aborted || timedOut) {
          stop(signal);
        }
        throw error;
      }
    }
  } finally {
    clearTimeout(timeoutId);
    signal.removeEventListener("abort", onCallerAbort);
  }
}
