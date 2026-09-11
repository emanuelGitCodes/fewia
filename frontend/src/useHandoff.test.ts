/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestRenderer } from "react-test-renderer";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SHAPE_ERROR } from "./apiTypes";
import { parseHandoffView } from "./handoffTypes";
import { useHandoff } from "./useHandoff";

const JOB_ID = "00000000-0000-0000-0000-00000000000a";
const ID = "00000000-0000-0000-0000-000000000001";
const SUCCESS_URL = "https://www.instacart.com/store/lists/demo?retailer_key=abc";
const UNSAFE_URL = "https://example.com/store/lists/demo";
const STAMP = "2026-09-06T15:00:00+00:00";
const RAW = "do-not-echo-this";
const HTTP_FALLBACK =
  "The shopping link request failed. Check the plan, then retry.";

type HookValue = ReturnType<typeof useHandoff>;

function view(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: ID,
    state: "prepared",
    attempts: 0,
    url: null,
    error_code: null,
    expires_at: null,
    retry_allowed: false,
    ...overrides,
  };
}

const succeeded = view({
  state: "succeeded",
  attempts: 1,
  url: SUCCESS_URL,
  expires_at: STAMP,
  retry_allowed: false,
});

const recovery = view({
  state: "uncertain",
  attempts: 1,
  url: null,
  error_code: "invalid_cached_url",
  expires_at: STAMP,
  retry_allowed: true,
});

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    json: () => Promise.resolve(payload),
  } as Response;
}

function HookHost(props: { bucket: { current: HookValue | null } }): null {
  props.bucket.current = useHandoff();
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

describe("useHandoff", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("starts one create and stores the parsed view", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(succeeded),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).start(JOB_ID);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [path, init] = fetchMock.mock.calls[0] as [RequestInfo | URL, RequestInit];
    expect(path).toBe("/api/grocery/handoffs");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ job_id: JOB_ID }));
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(hookOf(bucket).view).toEqual(parseHandoffView(succeeded));
    expect(hookOf(bucket).error).toBeNull();
    expect(hookOf(bucket).pending).toBe(false);
    renderer.unmount();
  });

  it("does not call retry after an uncertain create", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(recovery),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).start(JOB_ID);
    });

    expect(hookOf(bucket).view).toEqual(parseHandoffView(recovery));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/grocery/handoffs");
    renderer.unmount();
  });

  it("retries with expected_attempt from the stored view", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () => jsonResponse(recovery))
      .mockImplementationOnce(async () => jsonResponse(succeeded));
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).start(JOB_ID);
    });
    const stored = hookOf(bucket).view;
    if (stored === null) {
      throw new Error("expected a stored view");
    }
    await act(async () => {
      await hookOf(bucket).retry();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [path, init] = fetchMock.mock.calls[1] as [RequestInfo | URL, RequestInit];
    expect(path).toBe(`/api/grocery/handoffs/${ID}/retry`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ expected_attempt: stored.attempts }));
    expect(hookOf(bucket).view).toEqual(parseHandoffView(succeeded));
    renderer.unmount();
  });

  it("does not fetch when retry_allowed is false", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(succeeded),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).start(JOB_ID);
    });
    await act(async () => {
      await hookOf(bucket).retry();
    });

    expect(hookOf(bucket).view?.retry_allowed).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    renderer.unmount();
  });

  it("does not fetch when view is null", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(succeeded),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).retry();
    });

    expect(hookOf(bucket).view).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    renderer.unmount();
  });

  it("aborts on unmount and ignores a late response", async () => {
    let seenSignal: AbortSignal | undefined;
    let resolvePost: ((value: Response) => void) | undefined;
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      seenSignal = init?.signal ?? undefined;
      return new Promise<Response>((resolve) => {
        resolvePost = resolve;
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    let startResult: Promise<void> | undefined;
    await act(async () => {
      startResult = hookOf(bucket).start(JOB_ID);
    });
    expect(hookOf(bucket).pending).toBe(true);

    act(() => {
      renderer.unmount();
    });
    expect(seenSignal?.aborted).toBe(true);

    await act(async () => {
      resolvePost?.(jsonResponse(succeeded));
      await startResult;
    });
  });

  it("stores SHAPE_ERROR for an unsafe URL and hides the URL", async () => {
    const unsafe = view({
      state: "succeeded",
      attempts: 1,
      url: UNSAFE_URL,
      expires_at: STAMP,
      retry_allowed: false,
    });
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse(unsafe),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).start(JOB_ID);
    });

    expect(hookOf(bucket).view).toBeNull();
    expect(hookOf(bucket).error).toBe(SHAPE_ERROR);
    expect(hookOf(bucket).error).not.toContain(UNSAFE_URL);
    expect(hookOf(bucket).pending).toBe(false);
    renderer.unmount();
  });

  it("stores the static fallback for HTTP failure and hides the body", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      jsonResponse({ detail: RAW }, false),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).start(JOB_ID);
    });

    expect(hookOf(bucket).view).toBeNull();
    expect(hookOf(bucket).error).toBe(HTTP_FALLBACK);
    expect(hookOf(bucket).error).not.toContain(RAW);
    expect(hookOf(bucket).pending).toBe(false);
    renderer.unmount();
  });

  it("clear drops view, error, and pending", async () => {
    const hung = new Promise<Response>(() => undefined);
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () => jsonResponse(recovery))
      .mockImplementationOnce(async () => jsonResponse({ detail: RAW }, false))
      .mockImplementation(() => hung);
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();

    await act(async () => {
      await hookOf(bucket).start(JOB_ID);
    });
    await act(async () => {
      await hookOf(bucket).retry();
    });
    expect(hookOf(bucket).view).toEqual(parseHandoffView(recovery));
    expect(hookOf(bucket).error).toBe(HTTP_FALLBACK);

    let pendingRetry: Promise<void> | undefined;
    await act(async () => {
      pendingRetry = hookOf(bucket).retry();
    });
    expect(hookOf(bucket).pending).toBe(true);

    act(() => {
      hookOf(bucket).clear();
    });
    expect(hookOf(bucket).view).toBeNull();
    expect(hookOf(bucket).error).toBeNull();
    expect(hookOf(bucket).pending).toBe(false);

    await act(async () => {
      await pendingRetry;
    });
    renderer.unmount();
  });
});
