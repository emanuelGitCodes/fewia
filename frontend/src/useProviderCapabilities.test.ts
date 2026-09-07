/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HTTP_ERROR, type ProviderCapabilities } from "./apiTypes";
import {
  useProviderCapabilities,
  type ProviderCapabilitiesState,
} from "./useProviderCapabilities";

const PROVIDER_MS = 20_000;
const PROVIDER_UNAVAILABLE =
  "The provider configuration is unavailable. Retry the provider request.";
const RAW = "do-not-echo-this";

const loaded: ProviderCapabilities = {
  chat_configured: true,
  plaid_configured: false,
  instacart_configured: true,
  spending_source: "fixture",
};

const stale: ProviderCapabilities = {
  chat_configured: false,
  plaid_configured: true,
  instacart_configured: false,
  spending_source: "plaid_sandbox",
};

function jsonOk(payload: unknown): Response {
  return { ok: true, json: () => Promise.resolve(payload) } as Response;
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

function HookHost(props: { bucket: { current: ProviderCapabilitiesState | null } }): null {
  props.bucket.current = useProviderCapabilities();
  return null;
}

function hookOf(bucket: { current: ProviderCapabilitiesState | null }): ProviderCapabilitiesState {
  if (bucket.current === null) {
    throw new Error("hook is not mounted");
  }
  return bucket.current;
}

function mount(): {
  bucket: { current: ProviderCapabilitiesState | null };
  renderer: ReactTestRenderer;
} {
  const bucket: { current: ProviderCapabilitiesState | null } = { current: null };
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(createElement(HookHost, { bucket }));
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return { bucket, renderer };
}

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}

describe("useProviderCapabilities", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      writable: true,
      value: globalThis,
    });
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(async () =>
        jsonOk(loaded),
      ),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads configured flags from GET /api/grocery/providers", async () => {
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonOk(loaded),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();
    expect(hookOf(bucket).pending).toBe(true);
    expect(hookOf(bucket).capabilities).toBeNull();
    expect(hookOf(bucket).error).toBeNull();
    await flush();
    expect(hookOf(bucket).capabilities).toEqual(loaded);
    expect(hookOf(bucket).pending).toBe(false);
    expect(hookOf(bucket).error).toBeNull();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/grocery/providers");
    renderer.unmount();
  });

  it("keeps capabilities null on failure and uses a static error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
        async () => ({ ok: false, json: async () => ({ detail: RAW }) }) as Response,
      ),
    );
    const { bucket, renderer } = mount();
    await flush();
    expect(hookOf(bucket).capabilities).toBeNull();
    expect(hookOf(bucket).error).toBe(PROVIDER_UNAVAILABLE);
    expect(hookOf(bucket).error).not.toBe(HTTP_ERROR);
    expect(hookOf(bucket).error).not.toContain(RAW);
    expect(hookOf(bucket).pending).toBe(false);
    renderer.unmount();
  });

  it("retries a failed provider fetch", async () => {
    const fetchMock = vi
      .fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValueOnce({ ok: false, json: async () => ({}) } as Response)
      .mockResolvedValueOnce(jsonOk(loaded));
    vi.stubGlobal("fetch", fetchMock);
    const { bucket, renderer } = mount();
    await flush();
    expect(hookOf(bucket).capabilities).toBeNull();
    expect(hookOf(bucket).error).toBe(PROVIDER_UNAVAILABLE);
    await act(async () => {
      hookOf(bucket).retry();
    });
    await flush();
    expect(hookOf(bucket).capabilities).toEqual(loaded);
    expect(hookOf(bucket).error).toBeNull();
    expect(hookOf(bucket).pending).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    renderer.unmount();
  });

  it("times out a hung JSON body after 20s with the static error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
        (_input: RequestInfo | URL, init?: RequestInit) => hungJson(init),
      ),
    );
    const { bucket, renderer } = mount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PROVIDER_MS);
      await Promise.resolve();
    });
    expect(hookOf(bucket).pending).toBe(false);
    expect(hookOf(bucket).capabilities).toBeNull();
    expect(hookOf(bucket).error).toBe(PROVIDER_UNAVAILABLE);
    renderer.unmount();
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
    const { bucket, renderer } = mount();
    await act(async () => {
      hookOf(bucket).retry();
    });
    await flush();
    expect(hookOf(bucket).capabilities).toEqual(loaded);
    await act(async () => {
      resolveFirst?.(jsonOk(stale));
    });
    expect(hookOf(bucket).capabilities).toEqual(loaded);
    renderer.unmount();
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
    const { bucket, renderer } = mount();
    expect(hookOf(bucket).pending).toBe(true);
    act(() => {
      renderer.unmount();
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
    const { bucket, renderer } = mount();
    await flush();
    expect(hookOf(bucket).capabilities).toEqual(loaded);
    expect(hookOf(bucket).error).toBeNull();
    await act(async () => {
      hookOf(bucket).retry();
    });
    await flush();
    expect(hookOf(bucket).capabilities).toBeNull();
    expect(hookOf(bucket).error).toBe(PROVIDER_UNAVAILABLE);
    expect(hookOf(bucket).error).not.toContain(RAW);
    expect(hookOf(bucket).pending).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    renderer.unmount();
  });
});
