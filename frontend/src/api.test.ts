/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  acceptSession, apiRequest, captureSessionGuard, currentSession, extractPairingTicket, fetchJob, fetchSession,
  isAbortError, loseSession, OWNER_PROOF_STORAGE, parseSession, readJson, recheckSession,
  redeemPairingTicket, SESSION_LOSS_EVENT,
  signOut, workspaceRecovery, workspaceStorageKey,
} from "./api";
import { SHAPE_ERROR } from "./apiTypes";
import { clearTestSession, seedKrogerOwnerProof, seedTestSession } from "./testSession";

const SESSION = { auth_mode: "local_demo", workspace_id: "12345678-1234-4234-8234-123456789abc" } as const;
const OTHER = "87654321-4321-4321-8321-cba987654321";
const PLAN = "fewia.plan-checkpoint.v1";
const STORE = "fewia.krogerStore.v1";

beforeEach(() => {
  seedTestSession();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  clearTestSession();
  window.history.replaceState(null, "", "/");
});

function reply(body: unknown): void {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => body })));
}

describe("session contract", () => {
  it("keeps a session guard valid through same-workspace validation", () => {
    const isCurrent = captureSessionGuard();
    acceptSession(SESSION);
    expect(isCurrent()).toBe(true);
  });

  it.each(["workspace", "auth", "loss"])("invalidates a session guard after %s changes and restoration", (change) => {
    const isCurrent = captureSessionGuard();
    if (change === "workspace") acceptSession({ ...SESSION, workspace_id: OTHER });
    else if (change === "auth") acceptSession({ ...SESSION, auth_mode: "alb" });
    else loseSession();
    expect(isCurrent()).toBe(false);
    acceptSession(SESSION);
    expect(isCurrent()).toBe(false);
  });

  it("does not activate a guard captured without a session", () => {
    loseSession();
    const isCurrent = captureSessionGuard();
    expect(isCurrent()).toBe(false);
    acceptSession(SESSION);
    expect(isCurrent()).toBe(false);
  });

  it("bootstraps only the exact session shape", async () => {
    loseSession();
    reply(SESSION);
    expect(await fetchSession()).toEqual(SESSION);
    expect(fetch).toHaveBeenCalledWith("/api/grocery/session", expect.objectContaining({
      method: "GET", credentials: "same-origin", redirect: "error",
    }));
    expect(new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).has("X-FEWIA-Workspace")).toBe(false);
  });

  it.each([null, {}, { ...SESSION, auth_mode: "hosted" }, { ...SESSION, workspace_id: "name" },
    { ...SESSION, token: "unexpected" }, { workspace_id: SESSION.workspace_id }])("rejects malformed sessions %#", (value) => {
    expect(() => parseSession(value)).toThrow(SHAPE_ERROR);
  });

  it("clears the previous workspace checkpoint, store, and proof on switch", () => {
    const planKey = workspaceStorageKey(PLAN);
    const proofKey = workspaceStorageKey(OWNER_PROOF_STORAGE);
    const storeKey = workspaceStorageKey(STORE);
    window.sessionStorage.setItem(planKey, "saved");
    window.sessionStorage.setItem(proofKey, "proof");
    window.localStorage.setItem(storeKey, "store");
    acceptSession({ ...SESSION, workspace_id: OTHER });
    expect(window.sessionStorage.getItem(planKey)).toBeNull();
    expect(window.sessionStorage.getItem(proofKey)).toBeNull();
    expect(window.localStorage.getItem(storeKey)).toBeNull();
    expect(workspaceStorageKey(PLAN)).toBe(`${PLAN}:${OTHER}`);
  });

  it("clears a workspace recorded by an earlier page load when bootstrap returns 401", async () => {
    loseSession();
    const key = `${PLAN}:${SESSION.workspace_id}`;
    const proof = `${OWNER_PROOF_STORAGE}:${SESSION.workspace_id}`;
    window.sessionStorage.setItem("fewia.workspace.v1", SESSION.workspace_id);
    window.sessionStorage.setItem(key, "saved");
    window.sessionStorage.setItem(proof, "proof");
    vi.stubGlobal("fetch", vi.fn(async () => ({ status: 401, ok: false })));
    await expect(fetchSession()).rejects.toThrow();
    expect(window.sessionStorage.getItem(key)).toBeNull();
    expect(window.sessionStorage.getItem(proof)).toBeNull();
  });

  it("ignores a late session failure from the previous workspace", async () => {
    let finish: (response: unknown) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => { finish = resolve; })));
    const pending = fetchSession();
    acceptSession({ ...SESSION, workspace_id: OTHER });
    finish({ status: 401, ok: false });
    await expect(pending).rejects.toThrow();
    expect(currentSession()?.workspace_id).toBe(OTHER);
  });

  it.each(["local_demo", "alb"])("handles legacy storage in %s", (auth_mode) => {
    window.sessionStorage.setItem(PLAN, "legacy-plan");
    window.localStorage.setItem(STORE, "legacy-store");
    acceptSession({ auth_mode, workspace_id: OTHER });
    expect(window.sessionStorage.getItem(workspaceStorageKey(PLAN))).toBe(auth_mode === "local_demo" ? "legacy-plan" : null);
    expect(window.localStorage.getItem(workspaceStorageKey(STORE))).toBe(auth_mode === "local_demo" ? "legacy-store" : null);
    expect(window.sessionStorage.getItem(PLAN)).toBeNull();
    expect(window.localStorage.getItem(STORE)).toBeNull();
  });

  it("dispatches one session-loss event, clears state, and never replays a mutation", async () => {
    const listener = vi.fn();
    window.addEventListener(SESSION_LOSS_EVENT, listener);
    const key = workspaceStorageKey(PLAN);
    const proof = workspaceStorageKey(OWNER_PROOF_STORAGE);
    window.sessionStorage.setItem(key, "saved");
    window.sessionStorage.setItem(proof, "proof");
    const fetchMock = vi.fn(async () => ({ status: 401, ok: false }));
    vi.stubGlobal("fetch", fetchMock);
    const results = await Promise.allSettled([
      apiRequest("/api/grocery/jobs", { method: "POST", body: "{}" }),
      apiRequest("/api/grocery/jobs", { method: "POST", body: "{}" }),
    ]);
    expect(results.every((result) => result.status === "rejected")).toBe(true);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(currentSession()).toBeNull();
    expect(window.sessionStorage.getItem(key)).toBeNull();
    expect(window.sessionStorage.getItem(proof)).toBeNull();
    await expect(apiRequest("/api/grocery/jobs", { method: "POST" })).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    window.removeEventListener(SESSION_LOSS_EVENT, listener);
  });

  it("rejects a request without a session before fetch", async () => {
    loseSession();
    vi.stubGlobal("fetch", vi.fn());
    await expect(apiRequest("/api/grocery/jobs", { method: "POST", body: "{}" })).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("clears browser state before signout and returns only the server URL", async () => {
    const key = workspaceStorageKey(PLAN);
    const proof = workspaceStorageKey(OWNER_PROOF_STORAGE);
    window.sessionStorage.setItem(key, "saved");
    window.sessionStorage.setItem(proof, "proof");
    vi.stubGlobal("fetch", vi.fn(async (path: string, init: RequestInit) => {
      expect(currentSession()).toBeNull();
      expect(window.sessionStorage.getItem(key)).toBeNull();
      expect(window.sessionStorage.getItem(proof)).toBeNull();
      expect(path).toBe("/api/grocery/signout");
      expect(init.body).toBeUndefined();
      expect(new Headers(init.headers).get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
      return { ok: true, json: async () => ({ logout_url: "https://identity.example/logout" }) };
    }));
    expect(await signOut()).toBe("https://identity.example/logout");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("supports local signout without navigation", async () => {
    reply({ logout_url: null });
    expect(await signOut()).toBeNull();
  });
});

describe("workspace fence", () => {
  const mismatch = (): Response => new Response(JSON.stringify({
    error: { code: "workspace_changed", message: "Your workspace changed. Reload before continuing." },
  }), { status: 409 });

  it.each([
    ["/api/grocery/config", "GET"],
    ["/api/grocery/jobs", "POST"],
    ["/api/grocery/kroger/pairing/redeem", "POST"],
  ])("sets the active UUID centrally for %s", async (path, method) => {
    reply({});
    await apiRequest(path, { method, headers: { "x-fewia-workspace": OTHER } });
    const headers = new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers);
    expect(headers.get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
  });

  it("removes a caller workspace header from bootstrap", async () => {
    reply(SESSION);
    await apiRequest("/api/grocery/session", { method: "GET", headers: { "X-FEWIA-Workspace": OTHER } });
    expect(new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).has("X-FEWIA-Workspace")).toBe(false);
  });

  it("clears the old workspace and revalidates concurrent mismatches once without replay", async () => {
    const key = workspaceStorageKey(PLAN);
    window.sessionStorage.setItem(key, "old plan");
    let finish: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn((path: string) => path === "/api/grocery/session"
      ? new Promise<Response>((resolve) => { finish = resolve; })
      : Promise.resolve(mismatch()));
    vi.stubGlobal("fetch", fetchMock);
    const results = await Promise.allSettled([
      apiRequest("/api/grocery/jobs", { method: "POST" }),
      apiRequest("/api/grocery/jobs", { method: "POST" }),
    ]);
    expect(results.every((result) => result.status === "rejected")).toBe(true);
    expect(currentSession()).toBeNull();
    expect(window.sessionStorage.getItem(key)).toBeNull();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/grocery/jobs", "/api/grocery/jobs", "/api/grocery/session",
    ]);
    const recovery = workspaceRecovery();
    expect(recovery).not.toBeNull();
    expect(recheckSession()).toBeNull();
    finish(new Response(JSON.stringify({ ...SESSION, workspace_id: OTHER })));
    await expect(recovery).resolves.toEqual({ ...SESSION, workspace_id: OTHER });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.each([
    [409, "Conflict"],
    [409, JSON.stringify({ error: { code: "kroger_disconnected" } })],
    [409, JSON.stringify({ error: { code: "idempotency_conflict" } })],
    [409, JSON.stringify({ code: "workspace_changed" })],
    [409, JSON.stringify({ error: { code: "workspace_changed" }, padding: "x".repeat(4096) })],
    [422, JSON.stringify({ error: { code: "workspace_changed" } })],
  ] as const)("preserves other errors and their response bodies (%s, %#)", async (status, body) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(body, { status })));
    const response = await apiRequest("/api/grocery/jobs", { method: "POST" });
    expect(response.status).toBe(status);
    expect(await response.text()).toBe(body);
    expect(currentSession()).toEqual(SESSION);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(workspaceRecovery()).toBeNull();
  });

  it("ignores a stale mismatch before reading its body", async () => {
    let finish: (response: Response) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const pending = apiRequest("/api/grocery/jobs", { method: "POST" });
    acceptSession({ ...SESSION, workspace_id: OTHER });
    const response = mismatch();
    const clone = vi.spyOn(response, "clone");
    finish(response);
    await expect(pending).rejects.toThrow();
    expect(clone).not.toHaveBeenCalled();
    expect(currentSession()?.workspace_id).toBe(OTHER);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("ignores a stale mismatch after asynchronous body parsing", async () => {
    let finish: (value: Uint8Array) => void = () => undefined;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        finish = (value): void => { controller.enqueue(value); controller.close(); };
      },
    });
    const response = new Response(body, { status: 409 });
    let started: () => void = () => undefined;
    const parsing = new Promise<void>((resolve) => { started = resolve; });
    const clone = response.clone.bind(response);
    vi.spyOn(response, "clone").mockImplementation(() => { started(); return clone(); });
    vi.stubGlobal("fetch", vi.fn(async () => response));
    const pending = apiRequest("/api/grocery/jobs", { method: "POST" });
    await parsing;
    acceptSession({ ...SESSION, workspace_id: OTHER });
    const key = workspaceStorageKey(PLAN);
    window.sessionStorage.setItem(key, "B plan");
    finish(new TextEncoder().encode(JSON.stringify({ error: { code: "workspace_changed" } })));
    await expect(pending).rejects.toThrow();
    expect(currentSession()?.workspace_id).toBe(OTHER);
    expect(window.sessionStorage.getItem(key)).toBe("B plan");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("revalidates a signout mismatch with its captured UUID without signing out the new workspace", async () => {
    let finish: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn((path: string, init: RequestInit) => {
      const headers = new Headers(init.headers);
      if (path === "/api/grocery/signout") {
        expect(currentSession()).toBeNull();
        expect(headers.get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
        return Promise.resolve(mismatch());
      }
      expect(headers.has("X-FEWIA-Workspace")).toBe(false);
      return new Promise<Response>((resolve) => { finish = resolve; });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(signOut()).rejects.toThrow();
    const recovery = workspaceRecovery();
    finish(new Response(JSON.stringify({ ...SESSION, workspace_id: OTHER })));
    await expect(recovery).resolves.toEqual({ ...SESSION, workspace_id: OTHER });
    expect(currentSession()?.workspace_id).toBe(OTHER);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/grocery/signout", "/api/grocery/session",
    ]);
  });

  it.each(["signout", "401"])("rejects a late bootstrap after %s ends the session", async (action) => {
    let finish: (response: Response) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn((path: string) => path === "/api/grocery/session"
      ? new Promise<Response>((resolve) => { finish = resolve; })
      : Promise.resolve(path.endsWith("signout")
        ? new Response(JSON.stringify({ logout_url: null })) : new Response(null, { status: 401 }))));
    const pending = fetchSession();
    if (action === "signout") await signOut();
    else await expect(apiRequest("/api/grocery/jobs/old", { method: "GET" })).rejects.toThrow();
    finish(new Response(JSON.stringify(SESSION)));
    await expect(pending).rejects.toThrow();
    expect(currentSession()).toBeNull();
  });
});

describe("CLI pairing", () => {
  it.each(["missing", "expired"])("blocks live local calls with %s proof before fetch", async (proof) => {
    const key = workspaceStorageKey(OWNER_PROOF_STORAGE);
    if (proof === "expired") {
      window.sessionStorage.setItem(key, JSON.stringify({ proof: "expired-test-proof", expiresAt: Date.now() - 1 }));
    } else {
      window.sessionStorage.removeItem(key);
    }
    vi.stubGlobal("fetch", vi.fn());
    await expect(apiRequest("/api/grocery/kroger/connection", { method: "GET" }, "live"))
      .rejects.toThrow("Open the operator pairing link to use live Kroger.");
    expect(fetch).not.toHaveBeenCalled();
    expect(currentSession()).toEqual(SESSION);
    expect(window.sessionStorage.getItem(key)).toBeNull();
  });

  it("strips the fragment before any fetch and redeems without an owner header", async () => {
    window.history.replaceState(null, "", "/prototype?view=plan#kroger-pair=operator%2Bticket");
    const ticket = extractPairingTicket();
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("?view=plan");
    vi.stubGlobal("fetch", vi.fn(async (_path: string, init: RequestInit) => {
      expect(window.location.hash).toBe("");
      expect(new Headers(init.headers).has("X-FEWIA-Kroger-Owner")).toBe(false);
      expect(JSON.parse(String(init.body))).toEqual({ ticket: "operator+ticket" });
      return { ok: true, json: async () => ({ proof: "owner-proof", expires_in_seconds: 28800 }) };
    }));
    await redeemPairingTicket(ticket ?? "");
    expect(globalThis.sessionStorage).toBe(window.sessionStorage);
    expect(globalThis.localStorage).toBe(window.localStorage);
    expect(window.localStorage).not.toBe(window.sessionStorage);
    expect(JSON.parse(window.sessionStorage.getItem(workspaceStorageKey(OWNER_PROOF_STORAGE)) ?? "null"))
      .toMatchObject({ proof: "owner-proof" });
    expect(JSON.stringify(window.sessionStorage)).toContain("owner-proof");
    expect(JSON.stringify(window.sessionStorage)).not.toContain("operator+ticket");
    expect(JSON.stringify(window.localStorage)).not.toContain("owner-proof");
  });

  it.each(["live", "fixture"] as const)("attaches proof only for live local calls: %s", async (mode) => {
    reply({ proof: "owner-proof", expires_in_seconds: 28800 });
    await redeemPairingTicket("ticket");
    reply({ connected: false });
    await apiRequest("/api/grocery/kroger/connection", { method: "GET" }, mode);
    const init = vi.mocked(fetch).mock.calls[0]?.[1];
    expect(new Headers(init?.headers).get("X-FEWIA-Kroger-Owner")).toBe(mode === "live" ? "owner-proof" : null);
  });

  it("does not attach a local proof to a hosted request", async () => {
    acceptSession({ ...SESSION, auth_mode: "alb" });
    window.sessionStorage.setItem(workspaceStorageKey(OWNER_PROOF_STORAGE), JSON.stringify({ proof: "owner-proof", expiresAt: Date.now() + 1000 }));
    reply({ connected: false });
    await apiRequest("/api/grocery/kroger/connection", { method: "GET" }, "live");
    expect(new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers).has("X-FEWIA-Kroger-Owner")).toBe(false);
  });

  it.each(["https://foreign.example/api/grocery/jobs", "//foreign.example/api/grocery/jobs", "/api/grocery/\\evil", "/api/grocery/../../logout"])("rejects non-API or unsafe paths %s", async (path) => {
    vi.stubGlobal("fetch", vi.fn());
    await expect(apiRequest(path, { method: "POST" })).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("chat quote owner transport", () => {
  const quote = "/api/grocery/chat/jobs/job-1?location_id=Ab123456";

  it("attaches existing live local proof and preserves the workspace header", async () => {
    seedKrogerOwnerProof();
    reply({});
    await apiRequest(quote, { method: "GET", headers: {
      "X-FEWIA-Kroger-Owner": "caller-proof", "X-FEWIA-Workspace": OTHER,
    } });
    const headers = new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers);
    expect(headers.get("X-FEWIA-Kroger-Owner")).toBe("synthetic-test-owner-proof");
    expect(headers.get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(["missing", "expired"])("allows a stored or degraded quote with %s proof", async (state) => {
    const key = workspaceStorageKey(OWNER_PROOF_STORAGE);
    if (state === "expired") {
      window.sessionStorage.setItem(key, JSON.stringify({ proof: "expired-test-proof", expiresAt: Date.now() - 1 }));
    }
    reply({});
    await apiRequest(quote, { method: "GET", headers: { "X-FEWIA-Kroger-Owner": "caller-proof" } }, "live");
    const headers = new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers);
    expect(headers.has("X-FEWIA-Kroger-Owner")).toBe(false);
    expect(headers.get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
    expect(window.sessionStorage.getItem(key)).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(["fixture", "hosted"])("omits proof for a %s quote", async (state) => {
    if (state === "hosted") acceptSession({ ...SESSION, auth_mode: "alb" });
    seedKrogerOwnerProof();
    reply({});
    await apiRequest(quote, { method: "GET", headers: { "X-FEWIA-Kroger-Owner": "caller-proof" } }, state === "fixture" ? "fixture" : "live");
    const headers = new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers);
    expect(headers.has("X-FEWIA-Kroger-Owner")).toBe(false);
    expect(headers.get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
  });

  it.each([
    ["/api/grocery/chat/jobs/job-1", "GET"],
    ["/api/grocery/chat/jobs/job-1?location_id=short", "GET"],
    ["/api/grocery/chat/jobs/job-1?location_id=123456789", "GET"],
    ["/api/grocery/chat/jobs/job-1?location_id=1234567%21", "GET"],
    ["/api/grocery/chat/jobs/job-1?location_id=Ab123456&location_id=12345678", "GET"],
    ["/api/grocery/chat/jobs/job-1/?location_id=Ab123456", "GET"],
    ["/api/grocery/chat/jobs/job-1/events?location_id=Ab123456", "GET"],
    ["/api/grocery/chat/jobs/job-1%2Fevents?location_id=Ab123456", "GET"],
    ["/api/grocery/chat/jobs/../jobs?location_id=Ab123456", "GET"],
    ["/api/grocery/chat/jobs?location_id=Ab123456", "GET"],
    ["/api/grocery/chat/jobs", "POST"],
    [quote, "POST"],
    [quote, "HEAD"],
    ["/api/grocery/jobs/job-1?location_id=Ab123456", "GET"],
    ["/api/grocery/config?location_id=Ab123456", "GET"],
    ["/api/grocery/session", "GET"],
  ])("strips proof from nonquote route %s %s", async (path, method) => {
    seedKrogerOwnerProof();
    reply({});
    await apiRequest(path, { method, headers: { "X-FEWIA-Kroger-Owner": "caller-proof" } });
    const headers = new Headers(vi.mocked(fetch).mock.calls[0]?.[1]?.headers);
    expect(headers.has("X-FEWIA-Kroger-Owner")).toBe(false);
    expect(headers.get("X-FEWIA-Workspace")).toBe(path === "/api/grocery/session" ? null : SESSION.workspace_id);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe("focus session check", () => {
  it("blocks unsafe requests without transport and does not replay them after a same-workspace check", async () => {
    let finish: (response: unknown) => void = () => undefined;
    const fetchMock = vi.fn((path: string) => path === "/api/grocery/session"
      ? new Promise((resolve) => { finish = resolve; })
      : Promise.resolve({ ok: true, status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const check = recheckSession();
    expect(check).not.toBeNull();
    expect(recheckSession()).toBeNull();
    for (const method of ["POST", "PUT", "PATCH", "DELETE", "post"]) {
      await expect(apiRequest("/api/grocery/jobs", { method })).rejects.toThrow();
    }
    await expect(apiRequest("/api/grocery/kroger/pairing/redeem", { method: "POST" })).rejects.toThrow();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await apiRequest("/api/grocery/jobs/job-1", { method: "GET" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    finish({ ok: true, status: 200, json: async () => SESSION });
    await expect(check).resolves.toEqual(SESSION);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await apiRequest("/api/grocery/jobs", { method: "POST" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("allows bootstrap and signout while a check is pending and rejects its late result", async () => {
    let finish: (response: unknown) => void = () => undefined;
    const fetchMock = vi.fn((path: string) => path === "/api/grocery/signout"
      ? Promise.resolve({ ok: true, status: 200, json: async () => ({ logout_url: null }) })
      : new Promise((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    const check = recheckSession();
    await signOut();
    expect(currentSession()).toBeNull();
    finish({ ok: true, status: 200, json: async () => SESSION });
    await expect(check).rejects.toThrow();
    expect(currentSession()).toBeNull();
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/grocery/session", "/api/grocery/signout",
    ]);
  });
});

describe("abort errors", () => {
  it("recognizes DOMException and Error aborts", () => {
    expect(isAbortError(new DOMException("Aborted", "AbortError"))).toBe(true);
    expect(isAbortError(Object.assign(new Error("Aborted"), { name: "AbortError" }))).toBe(true);
  });

  it("recognizes a DOMException from another browser realm", () => {
    const frame = document.createElement("iframe");
    document.body.append(frame);
    try {
      const realm = frame.contentWindow as Window & typeof globalThis;
      expect(isAbortError(new realm.DOMException("Aborted", "AbortError"))).toBe(true);
    } finally {
      frame.remove();
    }
  });

  it.each([
    null, undefined, "AbortError", {}, { name: "AbortError" },
    { name: "AbortError", [Symbol.toStringTag]: "DOMException" },
    new Error("AbortError"), new DOMException("Aborted", "TimeoutError"),
    Object.create(DOMException.prototype) as unknown,
    { get name(): string { throw new Error("Malformed error"); } },
  ])("rejects generic or malformed errors %#", (error) => {
    expect(isAbortError(error)).toBe(false);
  });

  it.each(["request", "json", "job", "session"])("does not start fetch for a pre-aborted %s call", async (kind) => {
    vi.stubGlobal("fetch", vi.fn());
    const controller = new AbortController();
    controller.abort();
    const pending = kind === "request"
      ? apiRequest("/api/grocery/jobs", { method: "POST", signal: controller.signal })
      : kind === "json"
        ? readJson("/api/grocery/jobs", { method: "POST", signal: controller.signal })
        : kind === "job" ? fetchJob("job-1", controller.signal) : fetchSession(controller.signal);
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(fetch).not.toHaveBeenCalled();
    expect(currentSession()).toEqual(SESSION);
  });
});

describe("fetchJob JSON abort", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("aborts a hung JSON body when the caller signal aborts", async () => {
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
    const controller = new AbortController();
    const pending = fetchJob("job-1", controller.signal);
    await jsonStarted;
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });
});
