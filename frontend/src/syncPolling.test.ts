/** @vitest-environment node */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR } from "./apiTypes";
import { fetchSyncJob, type SyncJob } from "./syncApi";
import { pollSyncJob } from "./syncPolling";

vi.mock("./syncApi", () => ({
  fetchSyncJob: vi.fn(),
}));

const POLL_MS = 2000;
const BUDGET_MS = 6 * 60 * 1000;
const TIMEOUT_ERROR =
  "The sync request is still processing and may continue. Retry checks the same request.";
const JOB_ID = "00000000-0000-0000-0000-000000000001";
const RAW = "do-not-echo-this";
const mockedFetch = vi.mocked(fetchSyncJob);

function job(status: SyncJob["status"]): SyncJob {
  return {
    id: JOB_ID,
    status,
    result: status === "succeeded" ? { source: "plaid_sandbox", changed_count: 2 } : null,
    error_code: status === "failed" ? RAW : null,
  };
}

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
  }
}

function hang(signal: AbortSignal): Promise<SyncJob> {
  return new Promise((_resolve, reject) => {
    const fail = (): void => {
      reject(new DOMException("Aborted", "AbortError"));
    };
    if (signal.aborted) {
      fail();
      return;
    }
    signal.addEventListener("abort", fail, { once: true });
  });
}

describe("pollSyncJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedFetch.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("polls queued then running until succeeded", async () => {
    const queued = job("queued");
    const running = job("running");
    const succeeded = job("succeeded");
    mockedFetch
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce(running)
      .mockResolvedValueOnce(succeeded);
    const updates: SyncJob[] = [];
    const pending = pollSyncJob(JOB_ID, new AbortController().signal, (current) => {
      updates.push(current);
    });
    await flush();
    expect(updates).toEqual([queued]);
    await vi.advanceTimersByTimeAsync(POLL_MS);
    await flush();
    expect(updates).toEqual([queued, running]);
    await vi.advanceTimersByTimeAsync(POLL_MS);
    await flush();
    await expect(pending).resolves.toEqual(succeeded);
    expect(updates).toEqual([queued, running, succeeded]);
    expect(mockedFetch).toHaveBeenCalledTimes(3);
    expect(mockedFetch).toHaveBeenCalledWith(JOB_ID, expect.any(AbortSignal));
  });

  it("returns a failed terminal job without further polls", async () => {
    const failed = job("failed");
    mockedFetch.mockResolvedValueOnce(failed);
    const updates: SyncJob[] = [];
    const result = await pollSyncJob(JOB_ID, new AbortController().signal, (current) => {
      updates.push(current);
    });
    expect(result).toEqual(failed);
    expect(updates).toEqual([failed]);
    expect(result.error_code).toBe(RAW);
    await vi.advanceTimersByTimeAsync(BUDGET_MS);
    await flush();
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("propagates a transport failure and skips updates", async () => {
    mockedFetch.mockRejectedValueOnce(new Error(HTTP_ERROR));
    const updates: SyncJob[] = [];
    await expect(
      pollSyncJob(JOB_ID, new AbortController().signal, (current) => {
        updates.push(current);
      }),
    ).rejects.toThrow(HTTP_ERROR);
    expect(updates).toEqual([]);
  });

  it("aborts during the poll wait and skips later fetches", async () => {
    mockedFetch.mockResolvedValue(job("queued"));
    const controller = new AbortController();
    const updates: SyncJob[] = [];
    const pending = pollSyncJob(JOB_ID, controller.signal, (current) => {
      updates.push(current);
    });
    await flush();
    expect(updates).toHaveLength(1);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    await vi.advanceTimersByTimeAsync(POLL_MS);
    await flush();
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(updates).toHaveLength(1);
  });

  it("aborts a hanging fetch through the internal signal", async () => {
    let seen: AbortSignal | undefined;
    mockedFetch.mockImplementation((_id, signal) => {
      seen = signal;
      return hang(signal ?? new AbortController().signal);
    });
    const controller = new AbortController();
    const updates: SyncJob[] = [];
    const pending = pollSyncJob(JOB_ID, controller.signal, (current) => {
      updates.push(current);
    });
    await flush();
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(seen?.aborted).toBe(true);
    expect(updates).toEqual([]);
  });

  it("times out a hanging fetch with a static error", async () => {
    let seen: AbortSignal | undefined;
    mockedFetch.mockImplementation((_id, signal) => {
      seen = signal;
      return hang(signal ?? new AbortController().signal);
    });
    const updates: SyncJob[] = [];
    const pending = pollSyncJob(JOB_ID, new AbortController().signal, (current) => {
      updates.push(current);
    });
    await flush();
    const timeoutAssertion = expect(pending).rejects.toThrow(TIMEOUT_ERROR);
    await vi.advanceTimersByTimeAsync(BUDGET_MS);
    await timeoutAssertion;
    try {
      await pending;
    } catch (error) {
      expect(error).toBeInstanceOf(Error);
      expect((error as Error).name).toBe("Error");
      expect((error as Error).message).toBe(TIMEOUT_ERROR);
      expect((error as Error).message).not.toContain(RAW);
    }
    expect(seen?.aborted).toBe(true);
    expect(updates).toEqual([]);
  });

  it("ignores a late fetch after caller abort", async () => {
    let resolveJob: ((value: SyncJob) => void) | undefined;
    mockedFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveJob = resolve;
        }),
    );
    const controller = new AbortController();
    const updates: SyncJob[] = [];
    const pending = pollSyncJob(JOB_ID, controller.signal, (current) => {
      updates.push(current);
    });
    await flush();
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    resolveJob?.(job("succeeded"));
    await flush();
    expect(updates).toEqual([]);
  });
});
