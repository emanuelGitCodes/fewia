/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR, type ProviderCapabilities } from "./apiTypes";
import { useProviderCapabilities } from "./useProviderCapabilities";

const PROVIDER_MS = 20_000;
const PROVIDER_UNAVAILABLE =
  "The provider configuration is unavailable. Retry the provider request.";
const RAW = "do-not-echo-this";

const loaded: ProviderCapabilities = {
  chat_configured: true,
  plaid_configured: false,
  spending_source: "fixture",
};

const stale: ProviderCapabilities = {
  chat_configured: false,
  plaid_configured: true,
  spending_source: "plaid_sandbox",
};

function jsonOk(payload: unknown): Response {
  return { ok: true, json: () => Promise.resolve(payload) } as Response;
}

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

function hungJson(init?: RequestInit): Promise<Response> {
  return Promise.resolve({
    ok: true,
    json: () =>
      new Promise<unknown>((_resolve, reject) => {
        const signal = init?.signal;
        const fail = (): void => {
          reject(new DOMException("Aborted", "AbortError"));
        };
        if (signal === undefined || signal === null) {
          return;
        }
        if (signal.aborted) {
          fail();
          return;
        }
        signal.addEventListener("abort", fail, { once: true });
      }),
  } as Response);
}

describe("useProviderCapabilities", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () =>
        jsonOk(loaded),
      ),
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads configured flags from GET /api/grocery/providers", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonOk(loaded),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useProviderCapabilities());
    expect(result.current.pending).toBe(true);
    expect(result.current.capabilities).toBeNull();
    expect(result.current.error).toBeNull();
    await flush();
    expect(result.current.capabilities).toEqual(loaded);
    expect(result.current.pending).toBe(false);
    expect(result.current.error).toBeNull();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/grocery/providers");
    unmount();
  });

  it("keeps capabilities null on failure and uses a static error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
        async () => ({ ok: false, json: async () => ({ detail: RAW }) }) as Response,
      ),
    );
    const { result, unmount } = renderHook(() => useProviderCapabilities());
    await flush();
    expect(result.current.capabilities).toBeNull();
    expect(result.current.error).toBe(PROVIDER_UNAVAILABLE);
    expect(result.current.error).not.toBe(HTTP_ERROR);
    expect(result.current.error).not.toContain(RAW);
    expect(result.current.pending).toBe(false);
    unmount();
  });

  it("retries a failed provider fetch", async () => {
    const fetchMock = vi
      .fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) } as Response)
      .mockResolvedValueOnce(jsonOk(loaded));
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useProviderCapabilities());
    await flush();
    expect(result.current.capabilities).toBeNull();
    expect(result.current.error).toBe(PROVIDER_UNAVAILABLE);
    await act(async () => {
      result.current.retry();
    });
    await flush();
    expect(result.current.capabilities).toEqual(loaded);
    expect(result.current.error).toBeNull();
    expect(result.current.pending).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    unmount();
  });

  it("times out a hung JSON body after 20s with the static error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
        (_input: RequestInfo | URL, init?: RequestInit) => hungJson(init),
      ),
    );
    const { result, unmount } = renderHook(() => useProviderCapabilities());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PROVIDER_MS);
      await Promise.resolve();
    });
    expect(result.current.pending).toBe(false);
    expect(result.current.capabilities).toBeNull();
    expect(result.current.error).toBe(PROVIDER_UNAVAILABLE);
    unmount();
  });

  it("ignores a stale response after retry starts", async () => {
    let resolveFirst: ((value: Response) => void) | undefined;
    const fetchMock = vi
      .fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveFirst = resolve;
          }),
      )
      .mockResolvedValue(jsonOk(loaded));
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useProviderCapabilities());
    await act(async () => {
      result.current.retry();
    });
    await flush();
    expect(result.current.capabilities).toEqual(loaded);
    await act(async () => {
      resolveFirst?.(jsonOk(stale));
    });
    expect(result.current.capabilities).toEqual(loaded);
    unmount();
  });

  it("aborts an in-flight fetch on unmount and ignores a late response", async () => {
    let seenSignal: AbortSignal | undefined;
    let resolvePost: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
        (_input: RequestInfo | URL, init?: RequestInit) => {
          seenSignal = init?.signal ?? undefined;
          return new Promise<Response>((resolve) => {
            resolvePost = resolve;
          });
        },
      ),
    );
    const { result, unmount } = renderHook(() => useProviderCapabilities());
    expect(result.current.pending).toBe(true);
    act(() => {
      unmount();
    });
    expect(seenSignal?.aborted).toBe(true);
    await act(async () => {
      resolvePost?.(jsonOk(loaded));
    });
  });

  it("clears capabilities after a later load failure", async () => {
    const fetchMock = vi
      .fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValueOnce(jsonOk(loaded))
      .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: RAW }) } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const { result, unmount } = renderHook(() => useProviderCapabilities());
    await flush();
    expect(result.current.capabilities).toEqual(loaded);
    expect(result.current.error).toBeNull();
    await act(async () => {
      result.current.retry();
    });
    await flush();
    expect(result.current.capabilities).toBeNull();
    expect(result.current.error).toBe(PROVIDER_UNAVAILABLE);
    expect(result.current.error).not.toContain(RAW);
    expect(result.current.pending).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    unmount();
  });
});
