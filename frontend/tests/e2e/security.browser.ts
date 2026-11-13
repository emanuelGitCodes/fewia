import { expect, test as base, type Page, type Route, type TestInfo } from "@playwright/test";

const ORIGIN = "http://127.0.0.1:49121";
const ATTACKER = "http://localhost:49122";
const WORKSPACE_A = "12345678-1234-4234-8234-123456789abc";
const WORKSPACE_B = "87654321-4321-4321-8321-cba987654321";
const PROOF = "synthetic-browser-owner-proof";
const TICKET = "synthetic+browser-pairing";
const CONFIRMATION = "synthetic-cart-confirmation";
const REVISION = "a".repeat(64);
const STORE = { locationId: "01400943", name: "Synthetic test store" };
const STORAGE_KEYS = ["fewia.plan-checkpoint.v1", "fewia.kroger-owner.v1", "fewia.krogerStore.v1"];
const NOTICE = "Estimated from the demo price catalog. Store prices, availability, taxes, delivery fees, and tips are not verified.";
const UNKNOWN = "Kroger did not confirm. Check your Kroger cart. This request will not be sent again.";
const TARGETS = [
  ["apply", "/grocery/proposals/synthetic-proposal/apply", { plan_cap_cents: 4000 }],
  ["discard", "/grocery/proposals/synthetic-proposal/discard", { confirm: true }],
  ["cart", "/grocery/kroger/cart/add", { confirmation_token: "synthetic-form-control" }],
  ["connect", "/grocery/kroger/connect", {}],
  ["signout", "/grocery/signout", {}],
] as const;

type Guard = { allowFailure: (path: string, status: number) => void };

const test = base.extend<{ guard: Guard; interceptNetwork: boolean }>({
  interceptNetwork: [true, { option: true }],
  guard: [async ({ page, context, interceptNetwork }, use) => {
    const allowed = new Set<string>();
    const errors: string[] = [];
    context.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin !== ORIGIN && url.origin !== ATTACKER) errors.push("Unexpected request outside the isolated servers.");
    });
    if (interceptNetwork) {
      await context.route("**/*", async (route) => {
        const url = new URL(route.request().url());
        if (url.origin === ORIGIN || url.origin === ATTACKER) {
          await route.continue();
        } else {
          await route.abort();
        }
      });
    }
    page.on("websocket", (socket) => {
      const url = new URL(socket.url());
      const allowedSocket = url.protocol === "ws:" &&
        (url.host === new URL(ORIGIN).host || url.host === new URL(ATTACKER).host);
      if (!allowedSocket) errors.push("Unexpected WebSocket outside the isolated servers.");
    });
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const status = /^Failed to load resource: the server responded with a status of (401|403|409|504) \([^)]*\)$/.exec(message.text())?.[1];
      let expected = false;
      try {
        const url = new URL(message.location().url);
        expected = url.origin === ORIGIN && allowed.has(`${url.pathname}:${status}`);
      } catch { /* Console messages can have no source URL. */ }
      if (!expected) errors.push("Unexpected browser console error.");
    });
    page.on("pageerror", () => { errors.push("Uncaught browser page error."); });
    await use({ allowFailure: (path, status) => { allowed.add(`${path}:${status}`); } });
    expect(errors, "browser errors and external requests").toEqual([]);
    if (["/", "/app", "/prototype"].includes(new URL(page.url()).pathname)) {
      await expectDocumentFits(page);
    }
  }, { auto: true }],
});

async function expectDocumentFits(page: Page): Promise<void> {
  const width = page.viewportSize()?.width;
  expect(width, "the project sets an explicit viewport").toBeDefined();
  const overflow = await page.evaluate((width) =>
    Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - width,
  width!);
  expect(overflow, "document horizontal overflow in pixels").toBeLessThanOrEqual(0);
}

function gate(): { wait: Promise<void>; release: () => void } {
  let release = (): void => undefined;
  const wait = new Promise<void>((resolve) => { release = resolve; });
  return { wait, release };
}

type ApiCall = {
  method: string;
  path: string;
  ownerMatches: boolean;
  ownerPresent: boolean;
  proofLeaked: boolean;
};
type Handler = (route: Route) => Promise<void>;

async function mockApi(page: Page): Promise<{
  state: {
    workspace: string;
    mode: "fixture" | "live";
    connected: boolean;
    sessionGate: ReturnType<typeof gate> | null;
    terminal: boolean;
    sessionReads: number;
    polls: number;
  };
  calls: ApiCall[];
  handlers: Map<string, Handler>;
  unexpected: string[];
}> {
  const state = {
    workspace: WORKSPACE_A,
    mode: "fixture" as "fixture" | "live",
    connected: false,
    sessionGate: null as ReturnType<typeof gate> | null,
    terminal: false,
    sessionReads: 0,
    polls: 0,
  };
  const calls: ApiCall[] = [];
  const handlers = new Map<string, Handler>();
  const unexpected: string[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    if (url.origin !== ORIGIN) {
      unexpected.push("API request outside the isolated origin");
      await route.abort();
      return;
    }
    const headers = await request.allHeaders();
    if (method === "GET" && path === "/api/grocery/session") {
      expect(headers["x-fewia-workspace"], "session bootstrap never sends a workspace header").toBeUndefined();
    } else if (path !== "/api/grocery/providers" || headers["x-fewia-workspace"] !== undefined) {
      expect(headers["x-fewia-workspace"] === state.workspace, "personalized request uses the active workspace").toBe(true);
    }
    const owner = headers["x-fewia-kroger-owner"];
    const proofLeaked = request.url().includes(PROOF) || (request.postData() ?? "").includes(PROOF) ||
      Object.entries(headers).some(([name, value]) => name !== "x-fewia-kroger-owner" && value.includes(PROOF));
    calls.push({ method, path, ownerMatches: owner === PROOF, ownerPresent: owner !== undefined, proofLeaked });
    const custom = handlers.get(`${method} ${path}`);
    if (custom !== undefined) {
      await custom(route);
      return;
    }
    if (method === "GET" && path === "/api/grocery/session") {
      state.sessionReads += 1;
      await state.sessionGate?.wait;
      await route.fulfill({ json: { auth_mode: "local_demo", workspace_id: state.workspace } });
    } else if (method === "GET" && path === "/api/grocery/providers") {
      await route.fulfill({ json: {
        chat_configured: true, plaid_configured: false,
        spending_source: "manual", kroger_mode: state.mode,
      } });
    } else if (method === "GET" && path === "/api/grocery/kroger/connection") {
      await route.fulfill({ json: { connected: state.connected } });
    } else if (method === "POST" && path === "/api/grocery/plans") {
      await route.fulfill({ json: { plan_revision_id: REVISION } });
    } else if (method === "POST" && path === "/api/grocery/chat/jobs") {
      await route.fulfill({ json: { job_id: "synthetic-chat-job", status: "queued" } });
    } else if (method === "GET" && path === "/api/grocery/chat/jobs/synthetic-chat-job") {
      state.polls += 1;
      await route.fulfill({ json: {
        id: "synthetic-chat-job", status: state.terminal ? "failed" : "queued",
        result: null, error_code: state.terminal ? "synthetic_failure" : null,
      } });
    } else if (method === "POST" && path === "/api/grocery/signout") {
      await route.fulfill({ json: { logout_url: null } });
    } else {
      unexpected.push(`${method} ${path}`);
      await route.abort();
    }
  });
  return { state, calls, handlers, unexpected };
}

async function openChat(page: Page): Promise<void> {
  const dock = page.getByRole("button", { name: "Ask FEWIA for a meal idea", exact: true });
  if (await dock.isVisible()) {
    await dock.focus();
    await page.keyboard.press("Enter");
  }
  await expect(page.getByRole("textbox", { name: "Ask for a meal", exact: true })).toBeVisible();
}

async function closeChat(page: Page): Promise<void> {
  const hide = page.getByRole("button", { name: "Hide chat", exact: true });
  if (await hide.isVisible()) await hide.click();
}

async function seedWorkspace(page: Page, workspace: string): Promise<void> {
  await page.evaluate(({ workspace, keys }) => {
    for (const key of keys) {
      sessionStorage.setItem(`${key}:${workspace}`, "synthetic workspace state");
      localStorage.setItem(`${key}:${workspace}`, "synthetic workspace state");
    }
  }, { workspace, keys: STORAGE_KEYS });
}

async function expectWorkspaceCleared(page: Page, workspace: string): Promise<void> {
  expect(await page.evaluate(({ workspace, keys }) => keys.every((key) =>
    sessionStorage.getItem(`${key}:${workspace}`) === null &&
    localStorage.getItem(`${key}:${workspace}`) === null,
  ), { workspace, keys: STORAGE_KEYS }), "workspace plan, owner, and store state cleared").toBe(true);
}

async function expectNoSensitiveDisplay(page: Page): Promise<void> {
  expect(await page.evaluate((values) => values.every((value) =>
    !location.href.includes(value) && !document.documentElement.outerHTML.includes(value) &&
    !JSON.stringify(localStorage).includes(value),
  ), [PROOF, TICKET, CONFIRMATION]), "sensitive fixture values absent from URL, DOM, and localStorage").toBe(true);
  expect(await page.evaluate((ticket) => !JSON.stringify(sessionStorage).includes(ticket), TICKET), "redeemed ticket is never stored").toBe(true);
}

async function capturePlan(page: Page, info: TestInfo, name: string): Promise<void> {
  await expect(page).toHaveTitle(/FEWIA/i);
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeAttached();
  await expect(page.locator("vite-error-overlay")).toHaveCount(0);
  await expectNoSensitiveDisplay(page);
  expect(await page.evaluate((width) =>
    Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) <= width,
  page.viewportSize()!.width), "verified state fits the viewport").toBe(true);
  await page.screenshot({ path: info.outputPath(`${name}.png`), fullPage: true });
}

test("session gates real views, switches workspaces, and clears signout state", async ({ page }, info) => {
  const api = await mockApi(page);
  const session = gate();
  api.state.sessionGate = session;
  await page.goto("/prototype");
  await expect.poll(() => api.state.sessionReads).toBe(1);
  await expect(page.getByRole("status")).toHaveText("Loading your session.");
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Meals that fit your budget" })).toHaveCount(0);
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  session.release();
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Plan cap", exact: true }).fill("73");
  await openChat(page);
  await page.getByRole("textbox", { name: "Ask for a meal", exact: true }).fill("Workspace A draft");
  await seedWorkspace(page, WORKSPACE_A);

  const revalidation = gate();
  api.state.sessionGate = revalidation;
  api.state.workspace = WORKSPACE_B;
  await page.evaluate(() => { window.dispatchEvent(new Event("focus")); });
  await expect.poll(() => api.state.sessionReads).toBe(2);
  await expect(page.getByRole("status").filter({ hasText: /^Checking your session\.$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toHaveCount(0);
  await expect(page.getByRole("textbox", { name: "Ask for a meal", exact: true })).toHaveCount(0);
  revalidation.release();
  await expect(page.getByRole("textbox", { name: "Plan cap", exact: true })).toHaveValue("40");
  await expectWorkspaceCleared(page, WORKSPACE_A);
  expect(await page.evaluate(() => sessionStorage.getItem("fewia.workspace.v1") === "87654321-4321-4321-8321-cba987654321"), "workspace B is active").toBe(true);
  await openChat(page);
  const draft = page.getByRole("textbox", { name: "Ask for a meal", exact: true });
  await expect(draft).toHaveValue("");
  await draft.fill("A fresh workspace B request");
  await draft.press("Enter");
  await expect(page.locator(".tonight-ask-status")).toHaveText("Queued");
  await expect(draft).toHaveAttribute("readonly", "");
  await expect.poll(() => api.state.polls).toBeGreaterThanOrEqual(2);
  api.state.terminal = true;
  await expect(page.locator(".tonight-ask-status")).toHaveText("FEWIA did not answer. Your plan did not change.");
  expect(api.calls.filter((call) => call.path === "/api/grocery/chat/jobs" && call.method === "POST")).toHaveLength(1);
  await closeChat(page);
  await expect(page.getByText(NOTICE, { exact: true })).toBeVisible();
  await capturePlan(page, info, "workspace-b");

  await seedWorkspace(page, WORKSPACE_B);
  const signout = gate();
  api.handlers.set("POST /api/grocery/signout", async (route) => {
    await signout.wait;
    await route.fulfill({ json: { logout_url: null } });
  });
  await page.getByRole("button", { name: "Sign out", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toHaveCount(0);
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expectWorkspaceCleared(page, WORKSPACE_B);
  expect(await page.evaluate(() => sessionStorage.getItem("fewia.workspace.v1")), "no active workspace after signout").toBeNull();
  signout.release();
  await expect(page.getByRole("status")).toHaveText("You are signed out.");
  expect(api.calls.filter((call) => call.path === "/api/grocery/signout")).toHaveLength(1);
  expect(api.unexpected, "unhandled API calls").toEqual([]);
});

test("401 from a real mutation removes private state without replay", async ({ page, guard }) => {
  const api = await mockApi(page);
  api.state.connected = true;
  guard.allowFailure("/api/grocery/kroger/connection", 401);
  api.handlers.set("DELETE /api/grocery/kroger/connection", async (route) => {
    await route.fulfill({ status: 401, json: { error: { code: "unauthorized", message: "Session expired." } } });
  });
  await page.goto("/prototype");
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Plan cap", exact: true }).fill("71");
  await openChat(page);
  await page.getByRole("textbox", { name: "Ask for a meal", exact: true }).fill("Private draft");
  await seedWorkspace(page, WORKSPACE_A);
  await page.getByRole("button", { name: "Disconnect", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: /^Your session ended\. Reload to sign in again\.$/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toHaveCount(0);
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Kroger account", exact: true })).toHaveCount(0);
  await expectWorkspaceCleared(page, WORKSPACE_A);
  await page.evaluate(() => { window.dispatchEvent(new Event("focus")); });
  expect(api.calls.filter((call) => call.method === "DELETE")).toHaveLength(1);
  expect(api.state.sessionReads, "expired UI cannot revalidate or replay on focus").toBe(1);
  expect(api.unexpected, "unhandled API calls").toEqual([]);
});

test("409 from a real mutation clears workspace A before revalidation loads B without replay", async ({ page, guard }, info) => {
  const api = await mockApi(page);
  api.state.connected = true;
  guard.allowFailure("/api/grocery/kroger/connection", 409);
  api.handlers.set("DELETE /api/grocery/kroger/connection", async (route) => {
    api.state.workspace = WORKSPACE_B;
    await route.fulfill({ status: 409, json: { error: { code: "workspace_changed", message: "The workspace changed." } } });
  });
  await page.goto("/prototype");
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Plan cap", exact: true }).fill("71");
  await openChat(page);
  await page.getByRole("textbox", { name: "Ask for a meal", exact: true }).fill("Workspace A private draft");
  await seedWorkspace(page, WORKSPACE_A);

  const revalidation = gate();
  api.state.sessionGate = revalidation;
  await page.getByRole("button", { name: "Disconnect", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => api.state.sessionReads).toBe(2);
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Meals that fit your budget" })).toHaveCount(0);
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Kroger account", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sign out", exact: true })).toHaveCount(0);
  await expectWorkspaceCleared(page, WORKSPACE_A);
  expect(await page.evaluate(() => sessionStorage.getItem("fewia.workspace.v1")), "no active workspace while the changed session is unresolved").toBeNull();
  expect(api.calls.filter((call) => call.method === "DELETE"), "workspace conflict does not replay the mutation while revalidating").toHaveLength(1);

  revalidation.release();
  await expect(page.getByRole("textbox", { name: "Plan cap", exact: true })).toHaveValue("40");
  expect(await page.evaluate(() => sessionStorage.getItem("fewia.workspace.v1")), "workspace B becomes active after session resolution").toBe(WORKSPACE_B);
  await openChat(page);
  const draft = page.getByRole("textbox", { name: "Ask for a meal", exact: true });
  await expect(draft).toHaveValue("");
  await draft.fill("Workspace B can send a fresh request");
  await draft.press("Enter");
  await expect(page.locator(".tonight-ask-status")).toHaveText("Queued");
  await expect.poll(() => api.calls.filter((call) => call.method === "POST" && call.path === "/api/grocery/chat/jobs")).toHaveLength(1);
  await expect.poll(() => api.state.polls).toBeGreaterThanOrEqual(1);
  await closeChat(page);
  await capturePlan(page, info, "workspace-conflict-b");
  expect(api.calls.filter((call) => call.method === "DELETE"), "workspace conflict never replays the rejected mutation in B").toHaveLength(1);
  expect(api.calls.filter((call) => call.method === "POST" && call.path === "/api/grocery/chat/jobs")).toHaveLength(1);
  expect(api.unexpected, "unhandled API calls").toEqual([]);
});

test("pairing strips the fragment before fetching and keeps proof in the tab", async ({ page }, info) => {
  const api = await mockApi(page);
  api.state.mode = "live";
  let redeemMatches = false;
  const strippedBeforeFetch: boolean[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) {
      strippedBeforeFetch.push(!request.url().includes(TICKET));
    }
  });
  api.handlers.set("GET /api/grocery/session", async (route) => {
    api.state.sessionReads += 1;
    strippedBeforeFetch.push(await page.evaluate(() => location.hash === ""));
    await route.fulfill({ json: { auth_mode: "local_demo", workspace_id: WORKSPACE_A } });
  });
  api.handlers.set("POST /api/grocery/kroger/pairing/redeem", async (route) => {
    strippedBeforeFetch.push(await page.evaluate(() => location.hash === ""));
    const request = route.request();
    const body = request.postDataJSON() as Record<string, unknown>;
    redeemMatches = JSON.stringify(body) === JSON.stringify({ ticket: TICKET }) &&
      (await request.allHeaders())["content-type"] === "application/json";
    await route.fulfill({ json: { proof: PROOF, expires_in_seconds: 28800 } });
  });
  await page.goto(`/prototype#kroger-pair=${encodeURIComponent(TICKET)}`);
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeVisible();
  await openChat(page);
  await expect(page.getByRole("link", { name: "Connect Kroger", exact: true })).toHaveAttribute("href", "#");
  expect(redeemMatches, "one-use ticket sent as the exact JSON redeem body").toBe(true);
  expect(strippedBeforeFetch.every(Boolean), "fragment stripped before session and redeem fetches").toBe(true);
  expect(api.calls.filter((call) => call.path.endsWith("/pairing/redeem"))).toHaveLength(1);
  expect(api.calls.filter((call) => call.path.endsWith("/connection")).every((call) => call.ownerMatches), "live connection requests carry only the tab owner proof").toBe(true);
  expect(api.calls.filter((call) => !call.path.endsWith("/connection")).every((call) => !call.ownerPresent), "session, providers, and redeem requests carry no owner header").toBe(true);
  expect(await page.evaluate(({ workspace, proof }) => {
    const raw = sessionStorage.getItem(`fewia.kroger-owner.v1:${workspace}`);
    const owner = raw === null ? null : JSON.parse(raw) as { proof: string; expiresAt: number };
    return owner?.proof === proof && owner.expiresAt > Date.now() &&
      Object.keys(sessionStorage).filter((key) => sessionStorage.getItem(key)?.includes(proof)).length === 1;
  }, { workspace: WORKSPACE_A, proof: PROOF }), "proof exists only in workspace-scoped sessionStorage").toBe(true);
  await expectNoSensitiveDisplay(page);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeVisible();
  await openChat(page);
  await expect(page.getByRole("link", { name: "Connect Kroger", exact: true })).toBeVisible();
  expect(api.calls.filter((call) => call.path.endsWith("/pairing/redeem")), "reload does not redeem again").toHaveLength(1);
  expect(api.calls.every((call) => !call.proofLeaked), "proof never appears in URLs, bodies, or other headers").toBe(true);
  expect(api.calls.filter((call) => call.path.endsWith("/connection")).every((call) => call.ownerMatches), "reload uses the saved tab proof").toBe(true);
  await closeChat(page);
  await capturePlan(page, info, "paired-plan");
  expect(api.unexpected, "unhandled API calls").toEqual([]);
});

test("cart confirmation sends once and never replays an unknown outcome", async ({ page, guard }, info) => {
  const api = await mockApi(page);
  api.state.mode = "live";
  api.state.connected = true;
  await page.addInitScript(({ workspace, proof, store }) => {
    sessionStorage.setItem(`fewia.kroger-owner.v1:${workspace}`, JSON.stringify({ proof, expiresAt: Date.now() + 28_800_000 }));
    localStorage.setItem(`fewia.krogerStore.v1:${workspace}`, JSON.stringify(store));
  }, { workspace: WORKSPACE_A, proof: PROOF, store: STORE });
  const send = gate();
  let revisionBody: unknown;
  let previewMatches = false;
  let addMatches = false;
  api.handlers.set("POST /api/grocery/plans", async (route) => {
    revisionBody = route.request().postDataJSON();
    await route.fulfill({ json: { plan_revision_id: REVISION } });
  });
  api.handlers.set("POST /api/grocery/kroger/cart/preview", async (route) => {
    previewMatches = JSON.stringify(route.request().postDataJSON()) === JSON.stringify({
      plan_revision_id: REVISION, location_id: STORE.locationId,
    });
    await route.fulfill({ json: {
      items: [{ ingredient_id: "black_beans", name: "Black beans", upc: "0001111041600",
        description: "Synthetic black beans", size: "15 oz", quantity: 2 }],
      unmatched: [], source: "live", confirmation_token: CONFIRMATION, expires_in_seconds: 300,
    } });
  });
  guard.allowFailure("/api/grocery/kroger/cart/add", 504);
  api.handlers.set("POST /api/grocery/kroger/cart/add", async (route) => {
    addMatches = JSON.stringify(route.request().postDataJSON()) === JSON.stringify({ confirmation_token: CONFIRMATION }) &&
      (await route.request().allHeaders())["content-type"] === "application/json";
    await send.wait;
    await route.fulfill({ status: 504, json: { error: { code: "unknown", message: "No confirmation." } } });
  });
  await page.goto("/prototype");
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Plan cap", exact: true }).fill("30");
  await page.getByRole("button", { name: /Increase servings for Bean tacos/i }).click();
  await openChat(page);
  const cart = page.getByRole("group", { name: "Kroger cart", exact: true });
  const preview = cart.getByRole("button", { name: "Preview Kroger cart", exact: true });
  await preview.focus();
  await page.keyboard.press("Enter");
  await expect(cart.getByRole("list", { name: "Kroger cart preview", exact: true })).toContainText("Synthetic black beans");
  await expect(cart.getByRole("status")).toHaveText("Kroger cart preview ready: 1 item.");
  expect(revisionBody, "preview saves the rendered plan and budget").toMatchObject({
    meals: [{ recipe_id: "bean_tacos", servings: 3 }], plan_cap_cents: 3000,
  });
  expect(previewMatches, "preview uses the saved revision and chosen store").toBe(true);
  const sendButton = cart.getByRole("button", { name: "Send 1 item to Kroger cart", exact: true });
  await sendButton.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => api.calls.filter((call) => call.path.endsWith("/cart/add")).length).toBe(1);
  await expect(sendButton).toHaveAttribute("aria-disabled", "true");
  await expect(preview).toHaveAttribute("aria-disabled", "true");
  await expect(cart.getByRole("status")).toHaveText("Sending items to Kroger cart.");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  expect(api.calls.filter((call) => call.path.endsWith("/cart/add")), "duplicate keyboard actions do not send twice").toHaveLength(1);
  expect(addMatches, "cart add sends JSON containing only confirmation_token").toBe(true);
  send.release();
  await expect(cart.getByRole("status")).toHaveText(UNKNOWN);
  await expect(sendButton).toHaveCount(0);
  await expect(preview).toHaveAttribute("aria-disabled", "true");
  await page.evaluate(() => { window.dispatchEvent(new Event("focus")); });
  await expect.poll(() => api.state.sessionReads).toBe(2);
  await expect(cart.getByRole("status")).toHaveText(UNKNOWN);
  await expectNoSensitiveDisplay(page);
  await capturePlan(page, info, "cart-unknown");
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your plan", exact: true })).toBeVisible();
  await openChat(page);
  await expect(cart.getByRole("button", { name: "Preview Kroger cart", exact: true })).toBeVisible();
  await expect(cart.getByRole("list", { name: "Kroger cart preview", exact: true })).toHaveCount(0);
  await expect(sendButton).toHaveCount(0);
  expect(api.calls.filter((call) => call.path.endsWith("/cart/add")), "focus and reload never replay a cart add").toHaveLength(1);
  expect(api.calls.filter((call) => call.path.endsWith("/cart/preview")), "reload never previews automatically").toHaveLength(1);
  expect(api.calls.filter((call) => call.path.startsWith("/api/grocery/kroger/")).every((call) => call.ownerMatches), "all live Kroger requests use the tab proof").toBe(true);
  expect(api.calls.filter((call) => !call.path.startsWith("/api/grocery/kroger/")).every((call) => !call.ownerPresent), "proof never reaches other API routes").toBe(true);
  expect(api.calls.every((call) => !call.proofLeaked), "proof never appears in URLs, bodies, or other headers").toBe(true);
  expect(api.unexpected, "no checkout, payment, or unhandled API calls").toEqual([]);
});

test.describe("isolated browser forms", () => {
  test.use({ interceptNetwork: false });

  for (const [name, path, body] of TARGETS) {
    test(`browser form ${name} is rejected while same-origin JSON reaches the sentinel`, async ({ page, guard }) => {
      const apiPath = `/api${path}`;
      guard.allowFailure(apiPath, 403);
      await page.goto(`${ATTACKER}/attacker?target=${name}`);
      await expect(page).toHaveTitle("FEWIA form probe");
      await expectDocumentFits(page);
      const responsePromise = page.waitForResponse((response) =>
        response.url() === `${ORIGIN}${apiPath}` && response.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Submit form", exact: true }).click();
      const response = await responsePromise;
      const attackHeaders = await response.allHeaders();
      expect(attackHeaders["x-fewia-test-origin"], "backend observes browser-generated attacker Origin").toBe(ATTACKER);
      expect(attackHeaders["x-fewia-test-sec-fetch-site"]).toBe("cross-site");
      expect(attackHeaders["x-fewia-test-sec-fetch-mode"]).toBe("navigate");
      expect(attackHeaders["x-fewia-test-sec-fetch-dest"]).toBe("document");
      expect(response.status(), "production middleware rejects the browser form").toBe(403);
      expect(response.headers()["cache-control"]).toBe("private, no-store");
      expect(await response.json()).toEqual({ error: { code: "forbidden", message: "The browser request is not allowed." } });

      await page.goto(`/api/grocery/security/document?target=${name}`);
      await expect(page).toHaveTitle("FEWIA form probe");
      await expectDocumentFits(page);
      const positiveResponse = page.waitForResponse((response) => response.url() === `${ORIGIN}${apiPath}` && response.request().method() === "POST");
      const result = await page.evaluate(async ({ apiPath, body }) => {
        const response = await fetch(apiPath, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        return { status: response.status, cache: response.headers.get("cache-control"), body: await response.json() as unknown };
      }, { apiPath, body });
      const positiveHeaders = await (await positiveResponse).allHeaders();
      expect(positiveHeaders["x-fewia-test-origin"]).toBe(ORIGIN);
      expect(positiveHeaders["x-fewia-test-sec-fetch-site"]).toBe("same-origin");
      expect(positiveHeaders["x-fewia-test-sec-fetch-mode"]).toBe("cors");
      expect(positiveHeaders["x-fewia-test-sec-fetch-dest"]).toBe("empty");
      expect(result, "legitimate JSON reaches the synthetic route through the same middleware").toEqual({
        status: 200, cache: "private, no-store", body: { sentinel: "accepted", path },
      });
    });
  }

  test("same-origin form navigation cannot apply a proposal", async ({ page, guard }) => {
    const path = "/api/grocery/proposals/synthetic-proposal/apply";
    guard.allowFailure(path, 403);
    await page.goto("/api/grocery/security/document?target=apply");
    await expect(page).toHaveTitle("FEWIA form probe");
    await expectDocumentFits(page);
    const pending = page.waitForResponse((response) => response.url() === `${ORIGIN}${path}`);
    await page.getByRole("button", { name: "Submit form", exact: true }).click();
    const response = await pending;
    const headers = await response.allHeaders();
    expect(headers["x-fewia-test-origin"]).toBe(ORIGIN);
    expect(headers["x-fewia-test-sec-fetch-site"]).toBe("same-origin");
    expect(headers["x-fewia-test-sec-fetch-mode"]).toBe("navigate");
    expect(headers["x-fewia-test-sec-fetch-dest"]).toBe("document");
    expect(response.status()).toBe(403);
    expect(response.headers()["cache-control"]).toBe("private, no-store");
    expect(await response.json()).toEqual({ error: { code: "forbidden", message: "The browser request is not allowed." } });
    await page.goto("/api/grocery/security/document?target=apply");
    await expect(page).toHaveTitle("FEWIA form probe");
    await expectDocumentFits(page);
  });
});
