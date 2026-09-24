/** @vitest-environment node */

import { afterEach, describe, expect, it, type Mock, vi } from "vitest";
import { HTTP_ERROR, SHAPE_ERROR } from "./apiTypes";
import {
  fetchSyncItems,
  fetchSyncJob,
  parseSyncItems,
  parseSyncJob,
  submitSyncJob,
} from "./syncApi";

const ITEM_ID = "item-1";
const JOB_ID = "00000000-0000-0000-0000-000000000001";
const ENCODED_ID = "aa/bb?cc";
const KEY = "sync-1";
const STAMP = "2026-09-06T15:00:00Z";
const OFFSET_STAMP = "2026-09-06T15:00:00+00:00";
const RAW = "do-not-echo-this";
const FORBIDDEN_ITEM = ["token", "account", "transaction", "access_token", "cursor", "credential_ref"] as const;
const FORBIDDEN_RESULT = ["token", "access_token", "cursor", "transactions", "account"] as const;

function item(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { id: ITEM_ID, last_synced_at: STAMP, ...overrides };
}

function result(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { source: "plaid_sandbox", changed_count: 0, ...overrides };
}

function job(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { id: JOB_ID, status: "succeeded", result: result(), error_code: null, ...overrides };
}

function ack(): Record<string, unknown> {
  return { job_id: JOB_ID, status: "queued" };
}

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

function expectShapeError(value: unknown, parse: (input: unknown) => unknown): void {
  expect(() => parse(value)).toThrow(SHAPE_ERROR);
  try {
    parse(value);
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(SHAPE_ERROR);
    expect((error as Error).message).not.toContain(RAW);
  }
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

describe("parseSyncItems", () => {
  it("accepts owned public items and a null stamp", () => {
    expect(parseSyncItems([item(), item({ id: "item-2", last_synced_at: null })])).toEqual([
      { id: ITEM_ID, last_synced_at: STAMP },
      { id: "item-2", last_synced_at: null },
    ]);
    expect(parseSyncItems([])).toEqual([]);
    expect(parseSyncItems([item({ last_synced_at: OFFSET_STAMP })])[0]?.last_synced_at).toBe(OFFSET_STAMP);
  });

  it("rejects malformed timestamps and nonblank id bounds", () => {
    expectShapeError([item({ last_synced_at: "2026-09-06T15:00:00" })], parseSyncItems);
    expectShapeError([item({ last_synced_at: "not-a-date" })], parseSyncItems);
    expectShapeError([item({ last_synced_at: RAW })], parseSyncItems);
    expectShapeError([item({ id: "" })], parseSyncItems);
    expectShapeError([item({ id: " " })], parseSyncItems);
    expectShapeError([item({ id: " item " })], parseSyncItems);
    expectShapeError([item({ id: "x".repeat(257) })], parseSyncItems);
  });

  it("rejects forbidden item fields and non-arrays", () => {
    for (const field of FORBIDDEN_ITEM) {
      expectShapeError([item({ [field]: RAW })], parseSyncItems);
    }
    expectShapeError({ id: ITEM_ID, last_synced_at: null }, parseSyncItems);
    expectShapeError(null, parseSyncItems);
  });
});

describe("parseSyncJob", () => {
  it("accepts queued null results and succeeded public results", () => {
    expect(parseSyncJob(job({ status: "queued", result: null }))).toEqual({
      id: JOB_ID,
      status: "queued",
      result: null,
      error_code: null,
    });
    expect(parseSyncJob(job({ status: "running", result: null, error_code: null }))).toEqual({
      id: JOB_ID,
      status: "running",
      result: null,
      error_code: null,
    });
    expect(parseSyncJob(job({ result: result({ changed_count: 3 }) })).result).toEqual({
      source: "plaid_sandbox",
      changed_count: 3,
    });
    expect(
      parseSyncJob(job({ status: "failed", result: null, error_code: "attempts_exhausted" })),
    ).toEqual({
      id: JOB_ID,
      status: "failed",
      result: null,
      error_code: "attempts_exhausted",
    });
  });

  it("rejects succeeded jobs without a result and invalid status", () => {
    expectShapeError(job({ status: "succeeded", result: null }), parseSyncJob);
    expectShapeError(job({ status: "succeeded", error_code: "sync_failed" }), parseSyncJob);
    expectShapeError(job({ status: "done" }), parseSyncJob);
    expectShapeError(job({ status: RAW }), parseSyncJob);
  });

  it("rejects invalid result and error_code pairs for each status", () => {
    expectShapeError(job({ status: "queued", result: result() }), parseSyncJob);
    expectShapeError(job({ status: "running", result: result() }), parseSyncJob);
    expectShapeError(job({ status: "queued", result: null, error_code: "sync_failed" }), parseSyncJob);
    expectShapeError(job({ status: "running", result: null, error_code: "sync_failed" }), parseSyncJob);
    expectShapeError(job({ status: "failed", result: result(), error_code: "sync_failed" }), parseSyncJob);
    expectShapeError(job({ status: "failed", result: null, error_code: null }), parseSyncJob);
    expectShapeError(job({ status: "failed", result: null, error_code: "" }), parseSyncJob);
    expectShapeError(job({ status: "failed", result: null, error_code: " " }), parseSyncJob);
  });

  it("rejects malformed counts and grocery-shaped results", () => {
    expectShapeError(job({ result: result({ changed_count: -1 }) }), parseSyncJob);
    expectShapeError(job({ result: result({ changed_count: 1.5 }) }), parseSyncJob);
    expectShapeError(job({ result: result({ changed_count: Number.MAX_SAFE_INTEGER + 1 }) }), parseSyncJob);
    expectShapeError(job({ result: result({ source: "fixture" }) }), parseSyncJob);
    expectShapeError(
      job({
        result: {
          plan: { notice: RAW },
          budget: {},
          spending_source: "plaid_sandbox",
        },
      }),
      parseSyncJob,
    );
  });

  it("rejects forbidden result fields and extra job keys", () => {
    for (const field of FORBIDDEN_RESULT) {
      expectShapeError(job({ result: result({ [field]: RAW }) }), parseSyncJob);
    }
    expectShapeError(job({ payload: RAW }), parseSyncJob);
    expectShapeError(job({ access_token: RAW }), parseSyncJob);
    expectShapeError(job({ id: "x".repeat(257) }), parseSyncJob);
  });
});

describe("syncApi fetches", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("gets items from /api/grocery/sync/items with no-store", async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse([item({ last_synced_at: null })]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    const parsed = await fetchSyncItems(signal);
    const [path, init] = lastCall(fetchMock);
    expect(path).toBe("/api/grocery/sync/items");
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("no-store");
    expect(init.body).toBeUndefined();
    expect(init.signal).toBe(signal);
    expect(parsed).toEqual([{ id: ITEM_ID, last_synced_at: null }]);
  });

  it("posts item_id JSON and Idempotency-Key to /api/grocery/sync/jobs", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(ack()));
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    const parsed = await submitSyncJob(ITEM_ID, KEY, signal);
    const [path, init] = lastCall(fetchMock);
    expect(path).toBe("/api/grocery/sync/jobs");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ item_id: ITEM_ID }));
    expect(init.headers).toEqual({
      "Content-Type": "application/json",
      "Idempotency-Key": KEY,
    });
    expect(init.signal).toBe(signal);
    expect(parsed).toEqual({ job_id: JOB_ID, status: "queued" });
  });

  it("gets a job from the encoded path with no-store", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(job()));
    vi.stubGlobal("fetch", fetchMock);
    const signal = new AbortController().signal;
    const parsed = await fetchSyncJob(ENCODED_ID, signal);
    const [path, init] = lastCall(fetchMock);
    expect(path).toBe(`/api/grocery/sync/jobs/${encodeURIComponent(ENCODED_ID)}`);
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("no-store");
    expect(init.body).toBeUndefined();
    expect(init.signal).toBe(signal);
    expect(parsed.id).toBe(JOB_ID);
    expect(parsed.result?.source).toBe("plaid_sandbox");
  });

  it("throws HTTP_ERROR and SHAPE_ERROR without leaking payloads", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: RAW }, false)));
    await expectStaticError(() => fetchSyncItems(), HTTP_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error(RAW);
      }),
    );
    await expectStaticError(() => submitSyncJob(ITEM_ID, KEY), HTTP_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => Promise.reject(new SyntaxError(RAW)),
      })),
    );
    await expectStaticError(() => fetchSyncJob(JOB_ID), SHAPE_ERROR);
    vi.unstubAllGlobals();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(job({ result: result({ cursor: RAW }) }))));
    await expectStaticError(() => fetchSyncJob(JOB_ID), SHAPE_ERROR);
  });

  it("aborts hung fetch and JSON bodies when the caller signal aborts", async () => {
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
    const fetchController = new AbortController();
    const pendingFetch = fetchSyncItems(fetchController.signal);
    await fetchStarted;
    fetchController.abort();
    await expect(pendingFetch).rejects.toMatchObject({ name: "AbortError" });

    vi.unstubAllGlobals();
    let markJsonStart: (() => void) | undefined;
    const jsonStarted = new Promise<void>((resolve) => {
      markJsonStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: () => {
          if (markJsonStart === undefined) {
            throw new Error("JSON start is not armed");
          }
          markJsonStart();
          return new Promise(() => undefined);
        },
      })),
    );
    const jsonController = new AbortController();
    const pendingJson = fetchSyncJob(JOB_ID, jsonController.signal);
    await jsonStarted;
    jsonController.abort();
    await expect(pendingJson).rejects.toMatchObject({ name: "AbortError" });

    vi.unstubAllGlobals();
    let markPostStart: (() => void) | undefined;
    const postStarted = new Promise<void>((resolve) => {
      markPostStart = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => {
        return new Promise<Response>(() => {
          if (markPostStart === undefined) {
            throw new Error("post start is not armed");
          }
          markPostStart();
        });
      }),
    );
    const postController = new AbortController();
    const pendingPost = submitSyncJob(ITEM_ID, KEY, postController.signal);
    await postStarted;
    postController.abort();
    await expect(pendingPost).rejects.toMatchObject({ name: "AbortError" });
  });
});
