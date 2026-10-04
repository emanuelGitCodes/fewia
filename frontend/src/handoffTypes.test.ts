/** @vitest-environment node */

import { describe, expect, it } from "vitest";
import { SHAPE_ERROR } from "./apiTypes";
import { isSafeHandoffUrl, parseHandoffView, type HandoffView } from "./handoffTypes";

const ID = "00000000-0000-0000-0000-000000000001";
const STAMP = "2026-09-06T15:00:00+00:00";
const SUCCESS_URL = "https://www.instacart.com/store/lists/demo?retailer_key=abc";
const RAW = "do-not-echo-this";
const KEYS = ["attempts", "error_code", "expires_at", "id", "retry_allowed", "state", "url"];
const MAX_URL = `https://www.instacart.com/${"a".repeat(2048 - 26)}`;

const VALID_URLS = [
  SUCCESS_URL,
  "https://instacart.com/path",
  "https://www.instacart.ca/foo?bar=1&baz=2",
  "https://instacart.ca/",
  "https://WWW.INSTACART.COM/Path",
  "https://www.instacart.com:443/path?q=1",
  MAX_URL,
];

const UNSAFE_URLS: string[] = [
  "",
  "   ",
  "https://example.com/store/lists/demo",
  "http://www.instacart.com/store/lists/demo",
  "https://www.instacart.com.evil.com/list",
  "https://www.instacart.com./list",
  "https://instacart.com.attacker/list",
  "https://evil-instacart.com/list",
  "https://notinstacart.com/list",
  "https://www.instacart.com:8443/list",
  "https://www.instacart.com:80/list",
  "https://user@www.instacart.com/list",
  "https://user:pass@www.instacart.com/list",
  "https://@www.instacart.com/list",
  "https://www.instacart.com/list#frag",
  "https://www.instacart.com/list#",
  "https://www.instacart.com/list with space",
  "https://www.instacart.com/list\t",
  "https://www.instacart.com/list\n",
  "https://www.instacart.com/a\\b",
  "https://127.0.0.1/list",
  "https://192.168.0.1/list",
  "https://[::1]/list",
  "https://localhost/list",
  "http://localhost/list",
  "file://www.instacart.com/list",
  "ftp://www.instacart.com/list",
  "javascript:alert(1)",
  "https://www.instacart.com/a%0d%0aSet-Cookie:x",
  "https://www.instacart.com/%0a",
  "https://www.instacart.com/%00",
  "https://www.instacart.com/%09",
  "https://www.instacart.com/list?q=%09",
  "https://www.instacart.com/%01",
  "https://www.instacart.com/%1f",
  "https://www.instacart.com/%1F",
  "https://www.instacart.com/%7f",
  "https://www.instacart.com/%7F",
  `https://www.instacart.com/${"a".repeat(2048)}`,
  "https://www.instacart.com:abc/list",
  " https://www.instacart.com/list",
  "https://www.instacart.com/list ",
  "https://www.instacart.com/list\u00a0",
  "https://www.instacart.com/\u0000",
  "https://www.instacart.com/\u007f",
  "https://www.instacart.com%2eevil.com/list",
  "https://www.inst\u0430cart.com/list",
  "https://www.instacart.com\\t.evil.com/list",
];

function base(overrides: Record<string, unknown> = {}): Record<string, unknown> {
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

function expectShapeError(value: unknown): void {
  expect(() => parseHandoffView(value)).toThrow(SHAPE_ERROR);
  try {
    parseHandoffView(value);
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(SHAPE_ERROR);
    expect((error as Error).message).not.toContain(RAW);
  }
}

describe("parseHandoffView", () => {
  it.each([null, undefined, 42, true, {}, []].map((value) => ({ value })))(
    "rejects a non-string URL without throwing: $value",
    ({ value }) => {
      expect(isSafeHandoffUrl(value)).toBe(false);
    },
  );

  it("accepts a prepared view and copies the seven known fields", () => {
    const parsed = parseHandoffView(base());
    expect(parsed).toEqual({
      id: ID,
      state: "prepared",
      attempts: 0,
      url: null,
      error_code: null,
      expires_at: null,
      retry_allowed: false,
    });
    expect(Object.keys(parsed).sort()).toEqual(KEYS);
  });

  it("accepts a dispatching view", () => {
    const parsed = parseHandoffView(base({ state: "dispatching", attempts: 1 }));
    expect(parsed.state).toBe("dispatching");
    expect(parsed.attempts).toBe(1);
    expect(parsed.url).toBeNull();
    expect(parsed.retry_allowed).toBe(false);
  });

  it("accepts a live succeeded view", () => {
    const parsed = parseHandoffView(
      base({
        state: "succeeded",
        attempts: 1,
        url: SUCCESS_URL,
        expires_at: STAMP,
        retry_allowed: false,
      }),
    );
    expect(parsed.state).toBe("succeeded");
    expect(parsed.url).toBe(SUCCESS_URL);
    expect(parsed.expires_at).toBe(STAMP);
    expect(parsed.retry_allowed).toBe(false);
  });

  it("accepts an expired succeeded view", () => {
    const parsed = parseHandoffView(
      base({ state: "succeeded", attempts: 1, url: null, expires_at: null, retry_allowed: true }),
    );
    expect(parsed.state).toBe("succeeded");
    expect(parsed.url).toBeNull();
    expect(parsed.expires_at).toBeNull();
    expect(parsed.retry_allowed).toBe(true);
  });

  it("accepts a failed view", () => {
    const parsed = parseHandoffView(
      base({ state: "failed", attempts: 1, error_code: "rejected", retry_allowed: true }),
    );
    expect(parsed.state).toBe("failed");
    expect(parsed.url).toBeNull();
    expect(parsed.retry_allowed).toBe(true);
    expect(parsed.error_code).toBe("rejected");
  });

  it("accepts an uncertain view", () => {
    const parsed = parseHandoffView(
      base({
        state: "uncertain",
        attempts: 1,
        error_code: "stale_dispatch",
        retry_allowed: true,
      }),
    );
    expect(parsed.state).toBe("uncertain");
    expect(parsed.url).toBeNull();
    expect(parsed.retry_allowed).toBe(true);
  });

  it("accepts the invalid_cached_url recovery view with retained expires_at", () => {
    const parsed = parseHandoffView({
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      state: "uncertain",
      attempts: 1,
      url: null,
      error_code: "invalid_cached_url",
      expires_at: "2026-09-13T15:00:00+00:00",
      retry_allowed: true,
    });
    expect(parsed).toEqual({
      id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      state: "uncertain",
      attempts: 1,
      url: null,
      error_code: "invalid_cached_url",
      expires_at: "2026-09-13T15:00:00+00:00",
      retry_allowed: true,
    });
  });

  it("rejects extra keys, missing keys, and non-objects", () => {
    expectShapeError(base({ request_payload: RAW }));
    expectShapeError(base({ attempt_token: RAW }));
    const missing = base();
    delete missing.url;
    expectShapeError(missing);
    expectShapeError(null);
    expectShapeError([]);
    expectShapeError("prepared");
    expectShapeError(1);
  });

  it("rejects malformed id, noninteger attempts, and nonboolean flags", () => {
    expectShapeError(base({ id: "" }));
    expectShapeError(base({ id: "abc" }));
    expectShapeError(base({ id: 1 }));
    expectShapeError(base({ id: "00000000-0000-0000-0000-00000000000" }));
    expectShapeError(base({ attempts: 1.5 }));
    expectShapeError(base({ attempts: "0" }));
    expectShapeError(base({ attempts: true }));
    expectShapeError(base({ attempts: -1 }));
    expectShapeError(base({ retry_allowed: "false" }));
    expectShapeError(base({ retry_allowed: 0 }));
    expectShapeError(base({ retry_allowed: null }));
    expectShapeError(base({ url: 1 }));
    expectShapeError(base({ error_code: true }));
  });

  it("rejects invalid timestamps and unknown states", () => {
    expectShapeError(base({ expires_at: "2026-09-06T15:00:00" }));
    expectShapeError(base({ expires_at: "not-a-date" }));
    expectShapeError(base({ expires_at: 1 }));
    expectShapeError(base({ expires_at: "" }));
    expectShapeError(base({ state: "pending" }));
    expectShapeError(base({ state: "running" }));
  });

  it("rejects inconsistent navigable state", () => {
    expectShapeError(base({ retry_allowed: true }));
    expectShapeError(base({ state: "dispatching", attempts: 1, retry_allowed: true }));
    expectShapeError(base({ state: "failed", retry_allowed: false }));
    expectShapeError(base({ state: "uncertain", retry_allowed: false }));
    expectShapeError(
      base({
        state: "uncertain",
        attempts: 1,
        retry_allowed: false,
        expires_at: STAMP,
      }),
    );
    expectShapeError(
      base({ state: "failed", retry_allowed: true, expires_at: STAMP }),
    );
    expectShapeError(
      base({
        state: "failed",
        retry_allowed: true,
        url: SUCCESS_URL,
        expires_at: STAMP,
      }),
    );
    expectShapeError(
      base({ state: "succeeded", attempts: 1, url: SUCCESS_URL, expires_at: STAMP, retry_allowed: true }),
    );
    expectShapeError(
      base({ state: "succeeded", attempts: 1, url: SUCCESS_URL, expires_at: null, retry_allowed: false }),
    );
    expectShapeError(
      base({ state: "succeeded", attempts: 1, url: null, expires_at: STAMP, retry_allowed: true }),
    );
    expectShapeError(
      base({ state: "succeeded", attempts: 1, url: null, expires_at: null, retry_allowed: false }),
    );
    expectShapeError(
      base({
        state: "dispatching",
        attempts: 1,
        url: SUCCESS_URL,
        expires_at: STAMP,
        retry_allowed: false,
      }),
    );
  });

  it("throws static SHAPE_ERROR and does not echo error_code", () => {
    expectShapeError(base({ error_code: RAW, extra: true }));
    expectShapeError(base({ state: "failed", retry_allowed: true, error_code: RAW, url: SUCCESS_URL }));
    expectShapeError(base({ id: RAW }));
  });

  it.each(VALID_URLS.map((url) => [url.slice(0, 40), url]))(
    "accepts a valid Instacart URL %s",
    (_label: string, url: string) => {
      expect(isSafeHandoffUrl(url)).toBe(true);
      const parsed: HandoffView = parseHandoffView(
        base({ state: "succeeded", attempts: 1, url, expires_at: STAMP, retry_allowed: false }),
      );
      expect(parsed.url).toBe(url);
      expect(parsed.state).toBe("succeeded");
    },
  );

  it.each(UNSAFE_URLS.map((url) => [url.slice(0, 48), url]))(
    "rejects an unsafe Instacart URL %s",
    (_label: string, url: string) => {
      expect(isSafeHandoffUrl(url)).toBe(false);
      expectShapeError(
        base({
          state: "succeeded",
          attempts: 1,
          url,
          error_code: RAW,
          expires_at: STAMP,
          retry_allowed: false,
        }),
      );
    },
  );
});
