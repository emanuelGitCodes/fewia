/** @vitest-environment jsdom */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiRequest, currentSession, loseSession, OWNER_PROOF_STORAGE, signOut, workspaceStorageKey } from "./api";
import { canonicalPath, selectRoot } from "./rootView";
import { clearTestSession, installTestStorage } from "./testSession";
import { useGroceryJob } from "./useGroceryJob";

vi.mock("./App", () => {
  function AppStub({ onSignOut }: { onSignOut?: () => void }) {
    const job = useGroceryJob();
    return <>
      <header><p>App stub</p><button type="button" onClick={onSignOut}>Sign out</button></header>
      <input aria-label="Draft" defaultValue="" />
      <button type="button" onClick={() => { void job.submit({
        request: {
          meals: [{ recipe_id: "bean_tacos", servings: 2 }], budget_period: "2026-11-01",
          plan_cap_cents: null, pantry_ingredients: [], ingredient_exclusions: [], diet: "omnivore",
        },
        monthly_limit_cents: 20000,
      }); }}>Start work</button>
      <p aria-label="Request progress">{job.job?.status ?? "idle"}</p>
    </>;
  }
  return { default: AppStub };
});
vi.mock("./prototype/TonightPrototype", () => ({
  TonightPrototype: ({ onSignOut }: { onSignOut?: () => void }) => <>
    <header><h1>Your plan</h1><button type="button" onClick={onSignOut}>Sign out</button></header>
  </>,
}));

const SESSION = { auth_mode: "local_demo", workspace_id: "12345678-1234-4234-8234-123456789abc" } as const;

beforeEach(() => {
  installTestStorage();
  loseSession();
  window.sessionStorage.clear();
  window.localStorage.clear();
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => SESSION })));
});

// A cold import of the lazy Tonight chunk can exceed the 1000 ms findBy default.
const LAZY_LOAD_WAIT = { timeout: 10_000 };

afterEach(() => {
  cleanup();
  clearTestSession();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("selectRoot", () => {
  it("suspends then resolves the lazy Tonight prototype at /prototype", async () => {
    render(selectRoot("/prototype"));
    expect(screen.queryByRole("heading", { name: "Your plan" })).toBeNull();
    expect(
      await screen.findByRole("heading", { name: "Your plan" }, LAZY_LOAD_WAIT),
    ).toBeTruthy();
    expect(screen.queryByText("App stub")).toBeNull();
  }, 15_000);

  it("ignores a trailing slash on /prototype/", async () => {
    render(selectRoot("/prototype/"));
    expect(
      await screen.findByRole("heading", { name: "Your plan" }, LAZY_LOAD_WAIT),
    ).toBeTruthy();
  }, 15_000);

  it("renders the App at /app after session validation", async () => {
    render(selectRoot("/app"));
    expect(await screen.findByText("App stub")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Your plan" })).toBeNull();
    expect(fetch).toHaveBeenCalledWith("/api/grocery/session", expect.objectContaining({ method: "GET" }));
  });

  it("does not mount authenticated views before the session resolves", async () => {
    let finish: (response: unknown) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => { finish = resolve; })));
    render(selectRoot("/app"));
    expect(screen.queryByText("App stub")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Loading your session.");
    await act(async () => { finish({ ok: true, json: async () => SESSION }); });
    expect(await screen.findByText("App stub")).toBeTruthy();
  });

  it("refuses to render malformed session responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ ...SESSION, extra: true }) })));
    render(selectRoot("/app"));
    await screen.findByText(/Your session could not be opened/);
    expect(screen.queryByText("App stub")).toBeNull();
  });

  it("refetches on focus, remounts workspace state, and clears the previous workspace storage", async () => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    const oldDraft = screen.getByRole("textbox", { name: "Draft" });
    fireEvent.change(oldDraft, { target: { value: "old workspace" } });
    const checkpoint = workspaceStorageKey("fewia.plan-checkpoint.v1");
    const proof = workspaceStorageKey(OWNER_PROOF_STORAGE);
    const store = workspaceStorageKey("fewia.krogerStore.v1");
    window.sessionStorage.setItem(checkpoint, "saved");
    window.sessionStorage.setItem(proof, "owner-proof");
    window.localStorage.setItem(store, "chosen store");
    const next = { ...SESSION, workspace_id: "87654321-4321-4321-8321-cba987654321" };
    let finish: (response: unknown) => void = () => undefined;
    const refetch = vi.fn(() => new Promise((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", refetch);
    fireEvent.focus(window);
    const hiddenView = oldDraft.closest("[hidden]");
    expect(hiddenView).not.toBeNull();
    expect(hiddenView?.hasAttribute("inert")).toBe(true);
    expect(oldDraft.isConnected).toBe(true);
    expect(screen.queryByRole("textbox", { name: "Draft" })).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Checking your session.");
    fireEvent.focus(window);
    await expect(apiRequest("/api/grocery/jobs", { method: "POST" })).rejects.toThrow();
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(refetch).toHaveBeenCalledWith("/api/grocery/session", expect.objectContaining({ method: "GET" }));
    await act(async () => { finish({ ok: true, status: 200, json: async () => next }); });
    expect(currentSession()).toEqual(next);
    expect(oldDraft.isConnected).toBe(false);
    expect((screen.getByLabelText("Draft") as HTMLInputElement).value).toBe("");
    expect(window.sessionStorage.getItem(checkpoint)).toBeNull();
    expect(window.sessionStorage.getItem(proof)).toBeNull();
    expect(window.localStorage.getItem(store)).toBeNull();
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("keeps the same workspace draft and outstanding job through a deferred focus check", async () => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    const draft = screen.getByRole("textbox", { name: "Draft" }) as HTMLInputElement;
    fireEvent.change(draft, { target: { value: "Dinner draft" } });
    let finishSession: (response: unknown) => void = () => undefined;
    let finishJob: (response: unknown) => void = () => undefined;
    let jobSignal: AbortSignal | null | undefined;
    const fetchMock = vi.fn((path: string, init: RequestInit) => {
      if (path === "/api/grocery/session") {
        return new Promise((resolve) => { finishSession = resolve; });
      }
      if (init.method === "POST") {
        return Promise.resolve({ ok: true, status: 200, json: async () => ({ job_id: "job-1", status: "queued" }) });
      }
      jobSignal = init.signal;
      return new Promise((resolve) => { finishJob = resolve; });
    });
    vi.stubGlobal("fetch", fetchMock);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Start work" })); });
    expect(jobSignal?.aborted).toBe(false);
    fireEvent.focus(window);
    expect(draft.closest("[hidden]")?.hasAttribute("inert")).toBe(true);
    await act(async () => { finishJob({ ok: true, status: 200, json: async () => ({
      id: "job-1", status: "running", result: null, error_code: null,
    }) }); });
    expect(jobSignal?.aborted).toBe(false);
    await act(async () => { finishSession({ ok: true, status: 200, json: async () => SESSION }); });
    expect(screen.getByRole("textbox", { name: "Draft" })).toBe(draft);
    expect(draft.value).toBe("Dinner draft");
    expect(draft.closest("[hidden], [inert]")).toBeNull();
    expect(screen.getByLabelText("Request progress").textContent).toBe("running");
    expect(jobSignal?.aborted).toBe(false);
    expect(fetchMock.mock.calls.filter((call) => call[1].method === "POST")).toHaveLength(1);
  });

  it.each(["401", "500", "malformed", "network", "abort"])("ends the session after a %s focus check failure", async (failure) => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    const draft = screen.getByRole("textbox", { name: "Draft" });
    vi.stubGlobal("fetch", vi.fn(async () => {
      if (failure === "network") throw new Error("Synthetic network failure");
      if (failure === "abort") throw new DOMException("Aborted", "AbortError");
      return failure === "malformed"
        ? { ok: true, status: 200, json: async () => ({ ...SESSION, extra: true }) }
        : { ok: false, status: Number(failure) };
    }));
    await act(async () => { fireEvent.focus(window); });
    expect(screen.getByRole("status").textContent).toContain("Your session ended.");
    expect(draft.isConnected).toBe(false);
    expect(currentSession()).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(["signout", "401"])("ignores a late successful focus check after %s", async (action) => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    let finish: (response: unknown) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn((path: string) => {
      if (path === "/api/grocery/session") return new Promise((resolve) => { finish = resolve; });
      return Promise.resolve(path === "/api/grocery/signout"
        ? { ok: true, status: 200, json: async () => ({ logout_url: null }) }
        : { ok: false, status: 401 });
    }));
    const existingRead = action === "401" ? apiRequest("/api/grocery/jobs/job-1", { method: "GET" }) : null;
    fireEvent.focus(window);
    await act(async () => {
      if (existingRead !== null) await expect(existingRead).rejects.toThrow();
      else await signOut();
    });
    await act(async () => { finish({ ok: true, status: 200, json: async () => SESSION }); });
    expect(currentSession()).toBeNull();
    expect(screen.queryByText("App stub")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Your session ended.");
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("unmounts views on 401 without replaying the mutation", async () => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    const checkpoint = workspaceStorageKey("fewia.plan-checkpoint.v1");
    const proof = workspaceStorageKey(OWNER_PROOF_STORAGE);
    const store = workspaceStorageKey("fewia.krogerStore.v1");
    window.sessionStorage.setItem(checkpoint, "saved");
    window.sessionStorage.setItem(proof, "owner-proof");
    window.localStorage.setItem(store, "chosen store");
    vi.stubGlobal("fetch", vi.fn(async () => ({ status: 401, ok: false })));
    await act(async () => {
      await expect(apiRequest("/api/grocery/jobs", { method: "POST" })).rejects.toThrow();
    });
    expect(screen.queryByText("App stub")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Your session ended");
    expect(currentSession()).toBeNull();
    expect(window.sessionStorage.getItem(checkpoint)).toBeNull();
    expect(window.sessionStorage.getItem(proof)).toBeNull();
    expect(window.localStorage.getItem(store)).toBeNull();
    await act(async () => { fireEvent.focus(window); });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each([SESSION.workspace_id, "87654321-4321-4321-8321-cba987654321"])(
    "unmounts a mismatched workspace and mounts a fresh validated %s view without replay",
    async (workspace_id) => {
      render(selectRoot("/app"));
      await screen.findByText("App stub");
      const draft = screen.getByRole("textbox", { name: "Draft" });
      fireEvent.change(draft, { target: { value: "private draft" } });
      const checkpoint = workspaceStorageKey("fewia.plan-checkpoint.v1");
      const proof = workspaceStorageKey(OWNER_PROOF_STORAGE);
      const store = workspaceStorageKey("fewia.krogerStore.v1");
      window.sessionStorage.setItem(checkpoint, "saved");
      window.sessionStorage.setItem(proof, "owner-proof");
      window.localStorage.setItem(store, "chosen store");
      let finish: (response: Response) => void = () => undefined;
      const fetchMock = vi.fn((path: string) => path.endsWith("/session")
        ? new Promise<Response>((resolve) => { finish = resolve; })
        : Promise.resolve(new Response(JSON.stringify({ error: { code: "workspace_changed" } }), { status: 409 })));
      vi.stubGlobal("fetch", fetchMock);
      await act(async () => {
        await expect(apiRequest("/api/grocery/jobs", { method: "POST" })).rejects.toThrow();
      });
      expect(draft.isConnected).toBe(false);
      expect(screen.queryByText("App stub")).toBeNull();
      expect(screen.getByRole("status").textContent).toBe("Checking your session.");
      expect(window.sessionStorage.getItem(checkpoint)).toBeNull();
      expect(window.sessionStorage.getItem(proof)).toBeNull();
      expect(window.localStorage.getItem(store)).toBeNull();
      fireEvent.focus(window);
      fireEvent.focus(window);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      await act(async () => { finish(new Response(JSON.stringify({ ...SESSION, workspace_id }))); });
      expect((screen.getByRole("textbox", { name: "Draft" }) as HTMLInputElement).value).toBe("");
      expect(currentSession()?.workspace_id).toBe(workspace_id);
      expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
        "/api/grocery/jobs", "/api/grocery/session",
      ]);
    },
  );

  it.each([401, 500, "malformed", "network"] as const)("stays signed out when mismatch recovery fails with %s", async (failure) => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    vi.stubGlobal("fetch", vi.fn(async (path: string) => {
      if (!path.endsWith("/session")) {
        return new Response(JSON.stringify({ error: { code: "workspace_changed" } }), { status: 409 });
      }
      if (failure === "network") throw new Error("Synthetic network failure");
      return failure === "malformed" ? new Response("{}") : new Response(null, { status: failure });
    }));
    await act(async () => {
      await expect(apiRequest("/api/grocery/jobs", { method: "POST" })).rejects.toThrow();
    });
    expect(currentSession()).toBeNull();
    expect(screen.queryByText("App stub")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Your session ended. Reload to sign in again.");
    fireEvent.focus(window);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("ignores the superseded focus check while mismatch recovery is pending", async () => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    const draft = screen.getByRole("textbox", { name: "Draft" });
    const checks: ((response: Response) => void)[] = [];
    const fetchMock = vi.fn((path: string) => path.endsWith("/session")
      ? new Promise<Response>((resolve) => { checks.push(resolve); })
      : Promise.resolve(new Response(JSON.stringify({ error: { code: "workspace_changed" } }), { status: 409 })));
    vi.stubGlobal("fetch", fetchMock);
    await act(async () => {
      const pending = apiRequest("/api/grocery/jobs", { method: "POST" });
      fireEvent.focus(window);
      await expect(pending).rejects.toThrow();
    });
    expect(checks).toHaveLength(2);
    expect(draft.isConnected).toBe(false);
    fireEvent.focus(window);
    await act(async () => { checks[0]?.(new Response(JSON.stringify(SESSION))); });
    expect(currentSession()).toBeNull();
    expect(screen.queryByText("App stub")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Checking your session.");
    const next = { ...SESSION, workspace_id: "87654321-4321-4321-8321-cba987654321" };
    await act(async () => { checks[1]?.(new Response(JSON.stringify(next))); });
    expect(screen.getByText("App stub")).toBeTruthy();
    expect(currentSession()).toEqual(next);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("restores the new workspace after signout mismatch without another signout", async () => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    const next = { ...SESSION, workspace_id: "87654321-4321-4321-8321-cba987654321" };
    let finish: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn((path: string, init: RequestInit) => {
      if (path.endsWith("/signout")) {
        expect(new Headers(init.headers).get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
        return Promise.resolve(new Response(JSON.stringify({ error: { code: "workspace_changed" } }), { status: 409 }));
      }
      return new Promise<Response>((resolve) => { finish = resolve; });
    });
    vi.stubGlobal("fetch", fetchMock);
    expect(screen.getByRole("button", { name: "Sign out" }).closest("header")).not.toBeNull();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Sign out" })); });
    expect(screen.queryByText("App stub")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Checking your session.");
    await act(async () => { finish(new Response(JSON.stringify(next))); });
    expect(screen.getByText("App stub")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" }).closest("header")).not.toBeNull();
    expect(currentSession()).toEqual(next);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual(["/api/grocery/signout", "/api/grocery/session"]);
  });

  it("strips and redeems the CLI fragment once under StrictMode before views mount", async () => {
    window.history.replaceState(null, "", "/app#kroger-pair=encoded%2Bticket");
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (path: string, init: RequestInit) => {
      expect(window.location.hash).toBe("");
      expect(screen.queryByText("App stub")).toBeNull();
      calls.push(path);
      if (path.endsWith("/pairing/redeem")) {
        expect(init.method).toBe("POST");
        expect(JSON.parse(String(init.body))).toEqual({ ticket: "encoded+ticket" });
        expect(new Headers(init.headers).has("X-FEWIA-Kroger-Owner")).toBe(false);
        expect(new Headers(init.headers).get("X-FEWIA-Workspace")).toBe(SESSION.workspace_id);
      } else {
        expect(new Headers(init.headers).has("X-FEWIA-Workspace")).toBe(false);
      }
      return { ok: true, json: async () => path.endsWith("/session")
        ? SESSION : { proof: "owner-proof", expires_in_seconds: 28800 } };
    }));
    render(<StrictMode>{selectRoot("/app")}</StrictMode>);
    expect(await screen.findByText("App stub")).toBeTruthy();
    expect(calls).toEqual(["/api/grocery/session", "/api/grocery/kroger/pairing/redeem"]);
    expect(JSON.stringify(window.sessionStorage)).not.toContain("encoded+ticket");
    expect(JSON.stringify(window.localStorage)).not.toContain("owner-proof");
  });

  it("clears views and browser state as signout begins", async () => {
    render(selectRoot("/app"));
    await screen.findByText("App stub");
    const checkpoint = workspaceStorageKey("fewia.plan-checkpoint.v1");
    const proof = workspaceStorageKey(OWNER_PROOF_STORAGE);
    const store = workspaceStorageKey("fewia.krogerStore.v1");
    window.sessionStorage.setItem(checkpoint, "saved");
    window.sessionStorage.setItem(proof, "owner-proof");
    window.localStorage.setItem(store, "chosen store");
    let finish: (response: unknown) => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => { finish = resolve; })));
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(screen.queryByText("App stub")).toBeNull();
    expect(window.sessionStorage.getItem(checkpoint)).toBeNull();
    expect(window.sessionStorage.getItem(proof)).toBeNull();
    expect(window.localStorage.getItem(store)).toBeNull();
    expect(currentSession()).toBeNull();
    expect(fetch).toHaveBeenCalledWith("/api/grocery/signout", expect.objectContaining({ method: "POST" }));
    await act(async () => { fireEvent.focus(window); });
    expect(fetch).toHaveBeenCalledTimes(1);
    await act(async () => { finish({ ok: true, status: 200, json: async () => ({ logout_url: null }) }); });
    expect(await screen.findByText("You are signed out.")).toBeTruthy();
  });
});

describe("canonicalPath", () => {
  it.each(["/", ""])("sends %j to /prototype", (pathname) => {
    expect(canonicalPath(pathname)).toBe("/prototype");
  });

  it.each(["/prototype", "/prototype/", "/app"])(
    "leaves %s unchanged",
    (pathname) => {
      expect(canonicalPath(pathname)).toBe(pathname);
    },
  );
});
