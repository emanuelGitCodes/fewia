/** @vitest-environment node */

import { afterEach, describe, expect, it, type Mock, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR, SPOONACULAR_COST_NOTICE } from "./apiTypes";
import { fetchSupermarketEstimate, parseSupermarketEstimate } from "./supermarketApi";

const RAW = "do-not-echo-this";
const JOB_ID = "aa/bb?cc";

function overlay(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { total_cents: 1299, notice: SPOONACULAR_COST_NOTICE, ...overrides };
}

function jsonResponse(payload: unknown, ok = true): Response {
  return { ok, json: () => Promise.resolve(payload) } as Response;
}

type FetchMock = Mock<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>;

function lastCall(fetchMock: FetchMock): [RequestInfo | URL, RequestInit] {
  const call = fetchMock.mock.calls[0];
  const init = call?.[1];
  if (call === undefined || init === undefined) {
    throw new Error("fetch was not called");
  }
  return [call[0], init];
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

describe("parseSupermarketEstimate", () => {
  it("accepts a null or non-negative total with the fixed notice", () => {
    expect(parseSupermarketEstimate(overlay())).toEqual({
      total_cents: 1299,
      notice: SPOONACULAR_COST_NOTICE,
    });
    expect(parseSupermarketEstimate(overlay({ total_cents: null }))).toEqual({
      total_cents: null,
      notice: SPOONACULAR_COST_NOTICE,
    });
    expect(parseSupermarketEstimate(overlay({ total_cents: 0 })).total_cents).toBe(0);
  });

  it("rejects extra keys, missing keys, a wrong notice, and unsafe totals", () => {
    expect(() => parseSupermarketEstimate(overlay({ provider: RAW }))).toThrow(SHAPE_ERROR);
    expect(() => parseSupermarketEstimate({ notice: SPOONACULAR_COST_NOTICE })).toThrow(SHAPE_ERROR);
    expect(() => parseSupermarketEstimate(overlay({ notice: "store price" }))).toThrow(SHAPE_ERROR);
    expect(() => parseSupermarketEstimate(overlay({ total_cents: -1 }))).toThrow(SHAPE_ERROR);
    expect(() => parseSupermarketEstimate(overlay({ total_cents: 1.5 }))).toThrow(SHAPE_ERROR);
    expect(() =>
      parseSupermarketEstimate(overlay({ total_cents: Number.MAX_SAFE_INTEGER + 1 })),
    ).toThrow(SHAPE_ERROR);
  });
});

describe("fetchSupermarketEstimate", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("gets the encoded job path with cache no-store and the caller signal", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(overlay()),
    );
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    await expect(fetchSupermarketEstimate(JOB_ID, signal)).resolves.toEqual(
      parseSupermarketEstimate(overlay()),
    );
    const [path, init] = lastCall(fetchMock);
    expect(path).toBe(`/api/grocery/jobs/${encodeURIComponent(JOB_ID)}/supermarket-estimate`);
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("no-store");
    expect(init.signal).toBe(signal);
  });

  it("throws HTTP_ERROR for failed fetches including 503 and hides raw payloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: RAW }, false)));
    await expectStaticError(() => fetchSupermarketEstimate(JOB_ID), HTTP_ERROR);
  });

  it("throws SHAPE_ERROR for malformed payloads and hides raw text", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ total_cents: 1299, notice: RAW })));
    await expectStaticError(() => fetchSupermarketEstimate(JOB_ID), SHAPE_ERROR);
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
    const pending = fetchSupermarketEstimate(JOB_ID, controller.signal);
    await fetchStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
