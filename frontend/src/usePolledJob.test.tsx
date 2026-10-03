/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolledJob } from "./usePolledJob";

type Body = { message: string };
type Ack = { job_id: string };
type Job = { id: string; status: "queued" | "running" | "succeeded" | "failed" };

const POLL_MS = 750;
const BUDGET_MS = 3000;
const TIMEOUT_TEXT = "The configured request budget expired.";
const FAILED_TEXT = "The configured job failed.";
const FALLBACK_TEXT = "The configured request failed.";
const body: Body = { message: "First request" };
const otherBody: Body = { message: "Second request" };
const succeeded: Job = { id: "job-1", status: "succeeded" };
const queued: Job = { id: "job-1", status: "queued" };
const running: Job = { id: "job-1", status: "running" };

function options() {
  return {
    submitRequest: vi
      .fn<(body: Body, key: string, signal: AbortSignal) => Promise<Ack>>()
      .mockResolvedValue({ job_id: "job-1" }),
    fetchRequest: vi
      .fn<(jobId: string, signal: AbortSignal) => Promise<Job>>()
      .mockResolvedValue(succeeded),
    budgetMs: BUDGET_MS,
    timeoutText: TIMEOUT_TEXT,
    failedText: FAILED_TEXT,
    fallbackText: FALLBACK_TEXT,
    mapError: vi
      .fn<(caught: unknown, fallbackText: string) => string>()
      .mockReturnValue(FALLBACK_TEXT),
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function untilAborted<T>(signal: AbortSignal): Promise<T> {
  return new Promise<T>((_resolve, reject) => {
    const abort = (): void => reject(new DOMException("Aborted", "AbortError"));
    if (signal.aborted) {
      abort();
      return;
    }
    signal.addEventListener("abort", abort, { once: true });
  });
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("usePolledJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(crypto, "randomUUID")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000001")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000002")
      .mockReturnValueOnce("00000000-0000-4000-8000-000000000003");
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("publishes queued and running states at the polling cadence, then stops on success", async () => {
    const requests = options();
    requests.fetchRequest
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce(running);
    const { result } = renderHook(() => usePolledJob(requests));
    expect(result.current.job).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toBe(false);

    let finished: Promise<void> | undefined;
    await act(async () => {
      finished = result.current.submit(body);
    });
    expect(result.current.job).toEqual(queued);
    expect(result.current.pending).toBe(true);
    expect(result.current.error).toBeNull();
    expect(requests.fetchRequest).toHaveBeenCalledTimes(1);

    await advance(POLL_MS - 1);
    expect(requests.fetchRequest).toHaveBeenCalledTimes(1);
    expect(result.current.job).toEqual(queued);
    await advance(1);
    expect(requests.fetchRequest).toHaveBeenCalledTimes(2);
    expect(result.current.job).toEqual(running);
    expect(result.current.pending).toBe(true);
    expect(result.current.error).toBeNull();

    await advance(POLL_MS - 1);
    expect(requests.fetchRequest).toHaveBeenCalledTimes(2);
    await advance(1);
    await act(async () => {
      await finished;
    });
    expect(result.current.job).toEqual(succeeded);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    await advance(BUDGET_MS);
    expect(requests.fetchRequest).toHaveBeenCalledTimes(3);
    expect(result.current.job).toEqual(succeeded);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("publishes a failed terminal job and stops polling with the configured error", async () => {
    const requests = options();
    const failed: Job = { id: "job-1", status: "failed" };
    requests.fetchRequest.mockResolvedValueOnce(running).mockResolvedValue(failed);
    const { result } = renderHook(() => usePolledJob(requests));

    let finished: Promise<void> | undefined;
    await act(async () => {
      finished = result.current.submit(body);
    });
    expect(result.current.pending).toBe(true);
    expect(result.current.error).toBeNull();
    await advance(POLL_MS);
    await act(async () => {
      await finished;
    });
    expect(result.current.job).toEqual(failed);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBe(FAILED_TEXT);

    await advance(BUDGET_MS);
    expect(requests.fetchRequest).toHaveBeenCalledTimes(2);
    expect(result.current.job).toEqual(failed);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBe(FAILED_TEXT);
    act(() => result.current.clear());
    expect(result.current.job).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toBe(false);
  });

  it.each(["submit", "fetch", "polling"] as const)(
    "times out during %s at the configured budget with the configured text",
    async (stage) => {
      const requests = options();
      requests.budgetMs = BUDGET_MS + 123;
      if (stage === "submit") {
        requests.submitRequest.mockImplementation((_body, _key, signal) =>
          untilAborted<Ack>(signal),
        );
      } else if (stage === "fetch") {
        requests.fetchRequest.mockImplementation((_jobId, signal) =>
          untilAborted<Job>(signal),
        );
      } else {
        requests.fetchRequest.mockResolvedValue(queued);
      }
      const { result } = renderHook(() => usePolledJob(requests));

      let finished: Promise<void> | undefined;
      await act(async () => {
        finished = result.current.submit(body);
      });
      const signal = requests.submitRequest.mock.calls[0][2];
      await advance(requests.budgetMs - 1);
      expect(signal.aborted).toBe(false);
      expect(result.current.pending).toBe(true);
      expect(result.current.error).toBeNull();
      await advance(1);
      await act(async () => {
        await finished;
      });
      expect(signal.aborted).toBe(true);
      expect(result.current.pending).toBe(false);
      expect(result.current.error).toBe(TIMEOUT_TEXT);
      expect(result.current.job).toEqual(stage === "polling" ? queued : null);

      const polls = requests.fetchRequest.mock.calls.length;
      await advance(BUDGET_MS);
      expect(requests.fetchRequest).toHaveBeenCalledTimes(polls);
      expect(result.current.error).toBe(TIMEOUT_TEXT);
    },
  );

  it.each(["submit", "fetch"] as const)(
    "clear aborts an in-flight %s and keeps state empty after a late response",
    async (stage) => {
      const requests = options();
      const ack = deferred<Ack>();
      const job = deferred<Job>();
      if (stage === "submit") {
        requests.submitRequest.mockReturnValueOnce(ack.promise);
      } else {
        requests.fetchRequest
          .mockResolvedValueOnce(queued)
          .mockReturnValueOnce(job.promise);
      }
      const { result } = renderHook(() => usePolledJob(requests));

      let finished: Promise<void> | undefined;
      await act(async () => {
        finished = result.current.submit(body);
      });
      if (stage === "fetch") {
        expect(result.current.job).toEqual(queued);
        await advance(POLL_MS);
      }
      const signal =
        stage === "submit"
          ? requests.submitRequest.mock.calls[0][2]
          : requests.fetchRequest.mock.calls[1][1];
      expect(signal.aborted).toBe(false);
      expect(result.current.pending).toBe(true);
      act(() => result.current.clear());
      expect(signal.aborted).toBe(true);
      expect(result.current.job).toBeNull();
      expect(result.current.error).toBeNull();
      expect(result.current.pending).toBe(false);

      await act(async () => {
        ack.resolve({ job_id: "job-old" });
        job.resolve(succeeded);
        await finished;
      });
      await advance(BUDGET_MS);
      expect(result.current.job).toBeNull();
      expect(result.current.error).toBeNull();
      expect(result.current.pending).toBe(false);
      expect(requests.fetchRequest).toHaveBeenCalledTimes(stage === "submit" ? 0 : 2);
    },
  );

  it.each(["submit", "fetch"] as const)(
    "unmount aborts an in-flight %s and prevents further requests",
    async (stage) => {
      const requests = options();
      const ack = deferred<Ack>();
      const job = deferred<Job>();
      if (stage === "submit") {
        requests.submitRequest.mockReturnValueOnce(ack.promise);
      } else {
        requests.fetchRequest.mockReturnValueOnce(job.promise);
      }
      const { result, unmount } = renderHook(() => usePolledJob(requests));

      let finished: Promise<void> | undefined;
      await act(async () => {
        finished = result.current.submit(body);
      });
      const signal =
        stage === "submit"
          ? requests.submitRequest.mock.calls[0][2]
          : requests.fetchRequest.mock.calls[0][1];
      expect(signal.aborted).toBe(false);
      act(() => unmount());
      expect(signal.aborted).toBe(true);
      await act(async () => {
        ack.resolve({ job_id: "job-old" });
        job.resolve(queued);
        await finished;
      });
      await advance(BUDGET_MS);
      expect(requests.fetchRequest).toHaveBeenCalledTimes(stage === "submit" ? 0 : 1);
    },
  );

  it.each(["submit", "fetch"] as const)(
    "a late cancelled %s response cannot replace a newer result",
    async (stage) => {
      const requests = options();
      const ack = deferred<Ack>();
      const job = deferred<Job>();
      const newer: Job = { id: "job-new", status: "succeeded" };
      if (stage === "submit") {
        requests.submitRequest.mockReturnValueOnce(ack.promise);
      } else {
        requests.fetchRequest.mockReturnValueOnce(job.promise);
      }
      const { result } = renderHook(() => usePolledJob(requests));

      let first: Promise<void> | undefined;
      await act(async () => {
        first = result.current.submit(body);
      });
      const signal =
        stage === "submit"
          ? requests.submitRequest.mock.calls[0][2]
          : requests.fetchRequest.mock.calls[0][1];
      requests.submitRequest.mockResolvedValue({ job_id: "job-new" });
      requests.fetchRequest.mockResolvedValue(newer);
      await act(async () => {
        await result.current.submit(otherBody);
      });
      expect(signal.aborted).toBe(true);
      expect(result.current.job).toEqual(newer);
      await act(async () => {
        ack.resolve({ job_id: "job-old" });
        job.resolve({ id: "job-old", status: "failed" });
        await first;
      });
      await advance(BUDGET_MS);
      expect(result.current.job).toEqual(newer);
      expect(result.current.pending).toBe(false);
      expect(result.current.error).toBeNull();
      expect(requests.fetchRequest).toHaveBeenCalledTimes(stage === "submit" ? 1 : 2);
    },
  );

  it("reuses keys for identical bodies, changes keys for changed bodies, and resets on clear", async () => {
    const requests = options();
    const { result } = renderHook(() => usePolledJob(requests));

    for (const payload of [body, { ...body }, otherBody]) {
      await act(async () => {
        await result.current.submit(payload);
      });
    }
    act(() => result.current.clear());
    await act(async () => {
      await result.current.submit({ ...otherBody });
    });

    expect(requests.submitRequest.mock.calls.map((call) => call[1])).toEqual([
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000001",
      "00000000-0000-4000-8000-000000000002",
      "00000000-0000-4000-8000-000000000003",
    ]);
    expect(result.current.job).toEqual(succeeded);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
  });
});
