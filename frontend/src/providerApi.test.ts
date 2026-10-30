/** @vitest-environment node */

import { afterEach, describe, expect, it, type Mock, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR } from "./apiTypes";
import { fetchProviders, parseProviders } from "./providerApi";

const RAW = "do-not-echo-this";

function capabilities(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    chat_configured: true,
    plaid_configured: false,
    spending_source: "fixture",
    ...overrides,
  };
}

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    json: () => Promise.resolve(payload),
  } as Response;
}

type FetchMock = Mock<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>;

function lastInit(fetchMock: FetchMock): RequestInit {
  const init = fetchMock.mock.calls[0]?.[1];
  if (init === undefined) {
    throw new Error("fetch was not called");
  }
  return init;
}

async function expectStaticError(action: () => Promise<unknown>, message: string): Promise<void> {
  try {
    await action();
    throw new Error("expected a static error");
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(message);
    expect((error as Error).message).not.toContain(RAW);
  }
}

describe("parseProviders", () => {
  it("accepts configured flags and a known spending source", () => {
    expect(parseProviders(capabilities())).toEqual({
      chat_configured: true,
      plaid_configured: false,
      spending_source: "fixture",
    });
    expect(parseProviders(capabilities({ spending_source: "plaid_sandbox" })).spending_source).toBe(
      "plaid_sandbox",
    );
  });

  it("rejects unknown sources, nonbooleans, extra keys, and missing keys", () => {
    expect(() => parseProviders(capabilities({ spending_source: "bedrock" }))).toThrow(SHAPE_ERROR);
    expect(() => parseProviders(capabilities({ spending_source: "plaid" }))).toThrow(SHAPE_ERROR);
    expect(() => parseProviders(capabilities({ chat_configured: 1 }))).toThrow(SHAPE_ERROR);
    expect(() => parseProviders(capabilities({ plaid_configured: "true" }))).toThrow(SHAPE_ERROR);
    expect(() => parseProviders(capabilities({ instacart_configured: true }))).toThrow(SHAPE_ERROR);
    expect(() => parseProviders(capabilities({ client_id: RAW }))).toThrow(SHAPE_ERROR);
    const missing = capabilities();
    delete missing.plaid_configured;
    expect(() => parseProviders(missing)).toThrow(SHAPE_ERROR);
  });
});

describe("fetchProviders", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("gets provider capabilities from GET /api/grocery/providers", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(capabilities()),
    );
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    await expect(fetchProviders(signal)).resolves.toEqual(parseProviders(capabilities()));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/grocery/providers");
    const init = lastInit(fetchMock);
    expect(init.method).toBe("GET");
    expect(init.signal).toBe(signal);
  });

  it("throws HTTP_ERROR for failed and network fetches and hides raw payloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: RAW }, false)));
    await expectStaticError(() => fetchProviders(), HTTP_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error(RAW);
      }),
    );
    await expectStaticError(() => fetchProviders(), HTTP_ERROR);
  });

  it("throws SHAPE_ERROR for invalid JSON and invalid bodies and hides raw text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => Promise.reject(new SyntaxError(RAW)),
      })),
    );
    await expectStaticError(() => fetchProviders(), SHAPE_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ spending_source: RAW })));
    await expectStaticError(() => fetchProviders(), SHAPE_ERROR);
  });

  it("cancels a hung fetch when the caller signal aborts", async () => {
    let markFetchStart: (() => void) | undefined;
    const fetchStarted = new Promise<void>((resolve) => {
      markFetchStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise(() => {
            if (markFetchStart === undefined) {
              throw new Error("fetch start is not armed");
            }
            markFetchStart();
          }),
      ),
    );
    const controller = new AbortController();
    const pending = fetchProviders(controller.signal);
    await fetchStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
