/** @vitest-environment node */

import { afterEach, describe, expect, it, type Mock, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR } from "./apiTypes";
import { createHandoff, fetchHandoff, retryHandoff } from "./handoffApi";
import { parseHandoffView, type HandoffView } from "./handoffTypes";

const ID = "00000000-0000-0000-0000-000000000001";
const JOB_ID = "00000000-0000-0000-0000-00000000000a";
const ENCODED_ID = "aa/bb?cc";
const STAMP = "2026-09-06T15:00:00+00:00";
const SUCCESS_URL = "https://www.instacart.com/store/lists/demo?retailer_key=abc";
const UNSAFE_URL = "https://example.com/store/lists/demo";
const RAW = "do-not-echo-this";
const RECOVERY_EXPIRES = "2026-09-13T15:00:00+00:00";
const RECOVERY_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

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

const prepared = view();
const succeeded = view({
  state: "succeeded",
  attempts: 1,
  url: SUCCESS_URL,
  expires_at: STAMP,
  retry_allowed: false,
});
const recovery = view({
  id: RECOVERY_ID,
  state: "uncertain",
  attempts: 1,
  url: null,
  error_code: "invalid_cached_url",
  expires_at: RECOVERY_EXPIRES,
  retry_allowed: true,
});

function jsonResponse(payload: unknown, ok = true): Response {
  return {
    ok,
    json: () => Promise.resolve(payload),
  } as Response;
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
    expect((error as Error).message).not.toContain(UNSAFE_URL);
  }
}

describe("handoffApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("posts job_id JSON to POST /api/grocery/handoffs", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(prepared),
    );
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    const parsed: HandoffView = await createHandoff(JOB_ID, signal);
    const [path, init] = lastCall(fetchMock);
    expect(path).toBe("/api/grocery/handoffs");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ job_id: JOB_ID }));
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(init.signal).toBe(signal);
    expect(parsed).toEqual(parseHandoffView(prepared));
  });

  it("gets a handoff from the encoded path", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(prepared),
    );
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    const parsed = await fetchHandoff(ENCODED_ID, signal);
    const [path, init] = lastCall(fetchMock);
    expect(path).toBe(`/api/grocery/handoffs/${encodeURIComponent(ENCODED_ID)}`);
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    expect(init.signal).toBe(signal);
    expect(parsed).toEqual(parseHandoffView(prepared));
  });

  it("posts expected_attempt JSON to the encoded retry path", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(recovery),
    );
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    const parsed = await retryHandoff(ENCODED_ID, 1, signal);
    const [path, init] = lastCall(fetchMock);
    expect(path).toBe(`/api/grocery/handoffs/${encodeURIComponent(ENCODED_ID)}/retry`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ expected_attempt: 1 }));
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(init.signal).toBe(signal);
    expect(parsed).toEqual(parseHandoffView(recovery));
  });

  it("returns typed succeeded and recovery views from valid fixtures", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(succeeded),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expect(fetchHandoff(ID)).resolves.toEqual(parseHandoffView(succeeded));
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(recovery)),
    );
    await expect(createHandoff(JOB_ID)).resolves.toEqual(parseHandoffView(recovery));
  });

  it("throws HTTP_ERROR for failed and network fetches and hides raw payloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({ detail: RAW }, false)));
    await expectStaticError(() => createHandoff(JOB_ID), HTTP_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
        throw new Error(RAW);
      }),
    );
    await expectStaticError(() => fetchHandoff(ID), HTTP_ERROR);
  });

  it("throws SHAPE_ERROR for invalid JSON, invalid bodies, and unsafe URLs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
        ok: true,
        json: () => Promise.reject(new SyntaxError(RAW)),
      })),
    );
    await expectStaticError(() => createHandoff(JOB_ID), SHAPE_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({ id: RAW })),
    );
    await expectStaticError(() => fetchHandoff(ID), SHAPE_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
        jsonResponse(
          view({
            state: "succeeded",
            attempts: 1,
            url: UNSAFE_URL,
            error_code: RAW,
            expires_at: STAMP,
            retry_allowed: false,
          }),
        ),
      ),
    );
    await expectStaticError(() => retryHandoff(ID, 1), SHAPE_ERROR);
  });

  it("rejects unsafe attempts before fetch", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(prepared),
    );
    vi.stubGlobal("fetch", fetchMock);
    await expectStaticError(() => retryHandoff(ID, 0), SHAPE_ERROR);
    await expectStaticError(() => retryHandoff(ID, -1), SHAPE_ERROR);
    await expectStaticError(() => retryHandoff(ID, 1.5), SHAPE_ERROR);
    await expectStaticError(() => retryHandoff(ID, Number.NaN), SHAPE_ERROR);
    await expectStaticError(() => retryHandoff(ID, Number.MAX_SAFE_INTEGER + 1), SHAPE_ERROR);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("cancels a hung fetch when the caller signal aborts", async () => {
    let markFetchStart: (() => void) | undefined;
    const fetchStarted = new Promise<void>((resolve) => {
      markFetchStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => {
        return new Promise<Response>(() => {
          if (markFetchStart === undefined) {
            throw new Error("fetch start is not armed");
          }
          markFetchStart();
        });
      }),
    );
    const controller = new AbortController();
    const pending = fetchHandoff(ID, controller.signal);
    await fetchStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
