/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SHAPE_ERROR } from "./apiTypes";
import { submitSyncJob, type SyncJob } from "./syncApi";
import { pollSyncJob } from "./syncPolling";
import { useSyncJob } from "./useSyncJob";

vi.mock("./syncApi", () => ({
  submitSyncJob: vi.fn(),
}));
vi.mock("./syncPolling", () => ({
  pollSyncJob: vi.fn(),
}));

const POST_MS = 15_000;
const ITEM = "item-1";
const JOB_ID = "00000000-0000-0000-0000-000000000001";
const KEY1 = "00000000-0000-4000-8000-000000000001";
const KEY2 = "00000000-0000-4000-8000-000000000002";
const RAW = "do-not-echo-this";
const EMPTY_ITEM = "Enter a sync item id.";
const SYNC_FAILURE = "The sync request failed. Retry checks the same request.";
const TIMEOUT_ERROR =
  "The sync request is still processing and may continue. Retry checks the same request.";
const HTTP_FALLBACK = "The sync request failed. Check the item, then retry.";

type HookValue = ReturnType<typeof useSyncJob>;
type Ack = { job_id: string; status: SyncJob["status"] };

const mockedSubmit = vi.mocked(submitSyncJob);
const mockedPoll = vi.mocked(pollSyncJob);
const ack: Ack = { job_id: JOB_ID, status: "queued" };

function job(status: SyncJob["status"]): SyncJob {
  return {
    id: JOB_ID,
    status,
    result: status === "succeeded" ? { source: "plaid_sandbox", changed_count: 2 } : null,
    error_code: status === "failed" ? RAW : null,
  };
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function hang<T>(signal: AbortSignal): Promise<T> {
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

function HookHost(props: { bucket: { current: HookValue | null } }): null {
  props.bucket.current = useSyncJob();
  return null;
}

function mount(): { bucket: { current: HookValue | null }; renderer: ReactTestRenderer } {
  const bucket: { current: HookValue | null } = { current: null };
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(createElement(HookHost, { bucket }));
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return { bucket, renderer };
}

function hookOf(bucket: { current: HookValue | null }): HookValue {
  if (bucket.current === null) {
    throw new Error("hook is not mounted");
  }
  return bucket.current;
}

async function flushMicrotasks(): Promise<void> {
  await act(async () => {
    for (let i = 0; i < 10; i += 1) {
      await Promise.resolve();
    }
  });
}

describe("useSyncJob", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      writable: true,
      value: globalThis,
    });
    vi.useFakeTimers();
    mockedSubmit.mockReset();
    mockedPoll.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("does not start a job on mount", () => {
    const { renderer } = mount();
    expect(mockedSubmit).not.toHaveBeenCalled();
    expect(mockedPoll).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("rejects an empty item id before the network", async () => {
    const uuid = vi.spyOn(crypto, "randomUUID");
    const { bucket, renderer } = mount();
    await act(async () => {
      await hookOf(bucket).start("");
      await hookOf(bucket).start("  ");
    });
    expect(hookOf(bucket).error).toBe(EMPTY_ITEM);
    expect(hookOf(bucket).pending).toBe(false);
    expect(hookOf(bucket).job).toBeNull();
    expect(mockedSubmit).not.toHaveBeenCalled();
    expect(mockedPoll).not.toHaveBeenCalled();
    expect(uuid).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("blocks a second start before pending renders", async () => {
    const uuid = vi.spyOn(crypto, "randomUUID").mockReturnValue(KEY1);
    const post = deferred<Ack>();
    mockedSubmit.mockReturnValueOnce(post.promise);
    mockedPoll.mockResolvedValue(job("succeeded"));
    const { bucket, renderer } = mount();
    let first: Promise<void> | undefined;
    let second: Promise<void> | undefined;
    await act(async () => {
      first = hookOf(bucket).start(ITEM);
      second = hookOf(bucket).start(ITEM);
    });
    expect(hookOf(bucket).pending).toBe(true);
    expect(mockedSubmit).toHaveBeenCalledTimes(1);
    expect(uuid).toHaveBeenCalledTimes(1);
    await act(async () => {
      post.resolve(ack);
      await first;
      await second;
    });
    expect(mockedSubmit).toHaveBeenCalledTimes(1);
    expect(mockedPoll).toHaveBeenCalledTimes(1);
    expect(hookOf(bucket).job).toEqual(job("succeeded"));
    renderer.unmount();
  });

  it("retries a POST timeout with the same item and key", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValueOnce(KEY1);
    mockedSubmit.mockImplementation((_item, _key, signal) =>
      hang(signal ?? new AbortController().signal),
    );
    const { bucket, renderer } = mount();
    let finished: Promise<void> | undefined;
    await act(async () => {
      finished = hookOf(bucket).start(ITEM);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POST_MS);
      await finished;
    });
    expect(hookOf(bucket).error).toBe(TIMEOUT_ERROR);
    expect(hookOf(bucket).pending).toBe(false);
    expect(mockedPoll).not.toHaveBeenCalled();
    expect(mockedSubmit.mock.calls[0]?.[2]?.aborted).toBe(true);
    mockedSubmit.mockReset();
    mockedSubmit.mockResolvedValue(ack);
    mockedPoll.mockResolvedValue(job("succeeded"));
    await act(async () => {
      await hookOf(bucket).retry();
    });
    expect(mockedSubmit).toHaveBeenCalledTimes(1);
    expect(mockedSubmit).toHaveBeenCalledWith(ITEM, KEY1, expect.any(AbortSignal));
    expect(mockedPoll).toHaveBeenCalledWith(JOB_ID, expect.any(AbortSignal), expect.any(Function));
    expect(hookOf(bucket).job).toEqual(job("succeeded"));
    expect(hookOf(bucket).error).toBeNull();
    renderer.unmount();
  });

  it("retries a known job id without another POST", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValueOnce(KEY1);
    mockedSubmit.mockResolvedValue(ack);
    mockedPoll.mockRejectedValueOnce(new Error(TIMEOUT_ERROR));
    const { bucket, renderer } = mount();
    await act(async () => {
      await hookOf(bucket).start(ITEM);
    });
    expect(hookOf(bucket).error).toBe(TIMEOUT_ERROR);
    expect(mockedSubmit).toHaveBeenCalledTimes(1);
    mockedPoll.mockImplementation(async (_id, _signal, onUpdate) => {
      const succeeded = job("succeeded");
      onUpdate(succeeded);
      return succeeded;
    });
    await act(async () => {
      await hookOf(bucket).retry();
    });
    expect(mockedSubmit).toHaveBeenCalledTimes(1);
    expect(mockedPoll).toHaveBeenCalledTimes(2);
    expect(hookOf(bucket).job?.status).toBe("succeeded");
    expect(hookOf(bucket).error).toBeNull();
    renderer.unmount();
  });

  it("ignores a late POST after clear and after unmount", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue(KEY1);
    const firstPost = deferred<Ack>();
    mockedSubmit.mockReturnValueOnce(firstPost.promise);
    const { bucket, renderer } = mount();
    let firstStart: Promise<void> | undefined;
    await act(async () => {
      firstStart = hookOf(bucket).start(ITEM);
    });
    act(() => {
      hookOf(bucket).clear();
    });
    expect(hookOf(bucket).job).toBeNull();
    expect(hookOf(bucket).error).toBeNull();
    expect(hookOf(bucket).pending).toBe(false);
    await act(async () => {
      firstPost.resolve(ack);
      await firstStart;
    });
    expect(hookOf(bucket).job).toBeNull();
    expect(mockedPoll).not.toHaveBeenCalled();

    const latePost = deferred<Ack>();
    mockedSubmit.mockReturnValueOnce(latePost.promise);
    let unmountedStart: Promise<void> | undefined;
    await act(async () => {
      unmountedStart = hookOf(bucket).start(ITEM);
    });
    expect(mockedSubmit.mock.calls[1]?.[2]?.aborted).toBe(false);
    act(() => {
      renderer.unmount();
    });
    expect(mockedSubmit.mock.calls[1]?.[2]?.aborted).toBe(true);
    await act(async () => {
      latePost.resolve({ job_id: "job-late", status: "queued" });
      await unmountedStart;
    });
  });

  it("ignores a late poll result after clear", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValueOnce(KEY1);
    const pollWait = deferred<SyncJob>();
    let onUpdate: ((current: SyncJob) => void) | undefined;
    mockedSubmit.mockResolvedValue(ack);
    mockedPoll.mockImplementation((_id, _signal, update) => {
      onUpdate = update;
      return pollWait.promise;
    });
    const { bucket, renderer } = mount();
    let started: Promise<void> | undefined;
    await act(async () => {
      started = hookOf(bucket).start(ITEM);
    });
    await flushMicrotasks();
    act(() => {
      hookOf(bucket).clear();
    });
    await act(async () => {
      onUpdate?.(job("succeeded"));
      pollWait.resolve(job("succeeded"));
      await started;
    });
    expect(hookOf(bucket).job).toBeNull();
    expect(hookOf(bucket).pending).toBe(false);
    renderer.unmount();
  });

  it("maps failures to static errors and hides raw codes", async () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValue(KEY1);
    mockedSubmit.mockRejectedValueOnce(new Error(RAW));
    const { bucket, renderer } = mount();
    await act(async () => {
      await hookOf(bucket).start(ITEM);
    });
    expect(hookOf(bucket).error).toBe(HTTP_FALLBACK);
    expect(hookOf(bucket).error).not.toContain(RAW);
    expect(hookOf(bucket).job).toBeNull();
    mockedSubmit.mockRejectedValueOnce(new Error(SHAPE_ERROR));
    await act(async () => {
      await hookOf(bucket).retry();
    });
    expect(hookOf(bucket).error).toBe(SHAPE_ERROR);
    expect(hookOf(bucket).error).not.toContain(RAW);
    renderer.unmount();
  });

  it("keeps a failed job failed and starts a new key on start", async () => {
    const uuid = vi.spyOn(crypto, "randomUUID");
    uuid.mockReturnValueOnce(KEY1).mockReturnValueOnce(KEY2);
    mockedSubmit.mockResolvedValue(ack);
    mockedPoll.mockResolvedValue(job("failed"));
    const { bucket, renderer } = mount();
    await act(async () => {
      await hookOf(bucket).start(ITEM);
    });
    expect(hookOf(bucket).job?.status).toBe("failed");
    expect(hookOf(bucket).job?.error_code).toBe(RAW);
    expect(hookOf(bucket).error).toBe(SYNC_FAILURE);
    expect(hookOf(bucket).error).not.toContain(RAW);
    expect(hookOf(bucket).pending).toBe(false);
    await act(async () => {
      await hookOf(bucket).retry();
    });
    expect(mockedSubmit).toHaveBeenCalledTimes(1);
    expect(mockedPoll).toHaveBeenCalledTimes(1);
    mockedPoll.mockResolvedValue(job("succeeded"));
    await act(async () => {
      await hookOf(bucket).start(ITEM);
    });
    expect(uuid).toHaveBeenCalledTimes(2);
    expect(mockedSubmit).toHaveBeenCalledTimes(2);
    expect(mockedSubmit).toHaveBeenNthCalledWith(1, ITEM, KEY1, expect.any(AbortSignal));
    expect(mockedSubmit).toHaveBeenNthCalledWith(2, ITEM, KEY2, expect.any(AbortSignal));
    expect(hookOf(bucket).job).toEqual(job("succeeded"));
    expect(hookOf(bucket).error).toBeNull();
    renderer.unmount();
  });
});
