import {
  HTTP_ERROR,
  SHAPE_ERROR,
  UUID,
  hasExactKeys,
  isRecord,
  type GrocerySession,
  type KrogerMode,
  type GroceryConfig,
  type GroceryJob,
  type GroceryJobAck,
  type GroceryJobCreate,
} from "./apiTypes";
import { parseAck, parseConfig, parseJob } from "./apiValidation";

export type {
  CatalogItem,
  Diet,
  GroceryBudget,
  GroceryConfig,
  GroceryJob,
  GroceryJobAck,
  GroceryJobCreate,
  GroceryJobResult,
  GroceryPlan,
  GroceryRequest,
  JobStatus,
  MealRequest,
  PlanLine,
} from "./apiTypes";
export { HTTP_ERROR, SAMPLE_ESTIMATE_NOTICE, SHAPE_ERROR } from "./apiTypes";
export { parseAck, parseConfig, parseJob } from "./apiValidation";

export const SESSION_LOSS_EVENT = "fewia:session-lost";
export const SESSION_CHANGE_EVENT = "fewia:session-changed";
export const SESSION_RECOVERY_EVENT = "fewia:session-recovery";
export const OWNER_PROOF_STORAGE = "fewia.kroger-owner.v1";
const WORKSPACE_KEY = "fewia.workspace.v1";
const PLAN_KEY = "fewia.plan-checkpoint.v1";
const STORE_KEY = "fewia.krogerStore.v1";
let session: GrocerySession | null = null;
let generation = 0;
let sessionLost = false;
let krogerMode: KrogerMode = "live";
let focusCheck: symbol | null = null;
let recoveryCheck: Promise<GrocerySession> | null = null;

export function currentSession(): GrocerySession | null {
  return session;
}

export function captureSessionGuard(): () => boolean {
  const mine = generation;
  return () => session !== null && mine === generation;
}

export function workspaceStorageKey(key: string): string {
  if (session === null) throw new Error(HTTP_ERROR);
  return `${key}:${session.workspace_id}`;
}

export function parseSession(value: unknown): GrocerySession {
  if (
    !isRecord(value) || !hasExactKeys(value, ["auth_mode", "workspace_id"]) ||
    (value.auth_mode !== "local_demo" && value.auth_mode !== "alb") ||
    typeof value.workspace_id !== "string" || !UUID.test(value.workspace_id)
  ) throw new Error(SHAPE_ERROR);
  return { auth_mode: value.auth_mode, workspace_id: value.workspace_id.toLowerCase() };
}

function clearWorkspace(workspace: string): void {
  for (const key of [PLAN_KEY, OWNER_PROOF_STORAGE, STORE_KEY]) {
    try { window.sessionStorage.removeItem(`${key}:${workspace}`); } catch { /* Storage can be denied. */ }
    try { window.localStorage.removeItem(`${key}:${workspace}`); } catch { /* Storage can be denied. */ }
  }
}

function dispatchSessionEvent(name: string): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(name));
}

export function acceptSession(value: unknown): GrocerySession {
  const next = parseSession(value);
  let previous = session?.workspace_id;
  try { previous ??= window.sessionStorage.getItem(WORKSPACE_KEY) ?? undefined; } catch { /* Storage can be denied. */ }
  const changed = session === null || session.workspace_id !== next.workspace_id || session.auth_mode !== next.auth_mode;
  if (session !== null && session.auth_mode !== next.auth_mode) clearWorkspace(session.workspace_id);
  if (previous !== undefined && previous !== next.workspace_id && UUID.test(previous)) clearWorkspace(previous);
  if (changed) generation += 1;
  session = next;
  sessionLost = false;
  for (const [key, kind] of [[PLAN_KEY, "sessionStorage"], [STORE_KEY, "localStorage"]] as const) {
    try {
      const storage = window[kind];
      const legacy = storage.getItem(key);
      if (next.auth_mode === "local_demo" && legacy !== null && storage.getItem(workspaceStorageKey(key)) === null) {
        storage.setItem(workspaceStorageKey(key), legacy);
      }
      storage.removeItem(key);
    } catch { /* The session works without saved choices. */ }
  }
  try { window.sessionStorage.setItem(WORKSPACE_KEY, next.workspace_id); } catch { /* Storage can be denied. */ }
  if (changed) dispatchSessionEvent(SESSION_CHANGE_EVENT);
  return next;
}

export function loseSession(): void {
  let previous = session?.workspace_id;
  try { previous ??= window.sessionStorage.getItem(WORKSPACE_KEY) ?? undefined; } catch { /* Storage can be denied. */ }
  if (previous !== undefined && UUID.test(previous)) clearWorkspace(previous);
  session = null;
  generation += 1;
  focusCheck = null;
  recoveryCheck = null;
  krogerMode = "live";
  try { window.sessionStorage.removeItem(WORKSPACE_KEY); } catch { /* Storage can be denied. */ }
  if (!sessionLost) {
    sessionLost = true;
    dispatchSessionEvent(SESSION_LOSS_EVENT);
  }
}

export function setKrogerMode(mode: KrogerMode): void {
  krogerMode = mode;
}

function ownerProof(): string | null {
  try {
    const key = workspaceStorageKey(OWNER_PROOF_STORAGE);
    const raw = window.sessionStorage.getItem(key);
    const value: unknown = raw === null ? null : JSON.parse(raw);
    if (
      isRecord(value) && hasExactKeys(value, ["proof", "expiresAt"]) &&
      typeof value.proof === "string" && value.proof.length > 0 &&
      typeof value.expiresAt === "number" && value.expiresAt > Date.now()
    ) return value.proof;
    window.sessionStorage.removeItem(key);
  } catch { /* A missing proof leaves live calls unpaired. */ }
  return null;
}

export function hasKrogerOwnerProof(): boolean {
  return ownerProof() !== null;
}

export function extractPairingTicket(): string | null {
  const fragment = new URLSearchParams(window.location.hash.slice(1));
  const ticket = fragment.get("kroger-pair");
  if (fragment.has("kroger-pair")) {
    window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
  }
  return ticket;
}

export function apiRequest(path: string, init: RequestInit, mode = krogerMode): Promise<Response> {
  return requestWithWorkspace(path, init, mode, session?.workspace_id);
}

async function isWorkspaceChanged(response: Response, signal?: AbortSignal): Promise<boolean> {
  if (typeof response.clone !== "function") return false;
  const reader = response.clone().body?.getReader();
  if (reader === undefined) return false;
  const decoder = new TextDecoder();
  let text = "";
  let size = 0;
  try {
    while (true) {
      const part = await abortable(reader.read(), signal);
      if (part.done) break;
      size += part.value.byteLength;
      if (size > 4096) return false;
      text += decoder.decode(part.value, { stream: true });
    }
    const body: unknown = JSON.parse(text + decoder.decode());
    return isRecord(body) && isRecord(body.error) && body.error.code === "workspace_changed";
  } catch (error) {
    if (isAbortError(error)) throw error;
    return false;
  } finally {
    void reader.cancel().catch(() => undefined);
  }
}

export function workspaceRecovery(): Promise<GrocerySession> | null {
  return recoveryCheck;
}

function recoverWorkspace(): void {
  loseSession();
  const check = fetchSession();
  recoveryCheck = check;
  dispatchSessionEvent(SESSION_RECOVERY_EVENT);
  void check.catch(() => undefined).finally(() => {
    if (recoveryCheck === check) recoveryCheck = null;
  });
}

async function requestWithWorkspace(
  path: string, init: RequestInit, mode: KrogerMode, workspace: string | undefined,
): Promise<Response> {
  if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
  const target = new URL(path, "https://fewia.invalid");
  if (!/^\/api\/grocery\//.test(path) || /[\\\s]/.test(path) ||
      !target.pathname.startsWith("/api/grocery/")) {
    throw new Error(HTTP_ERROR);
  }
  const bootstrap = path === "/api/grocery/session" && (init.method ?? "GET").toUpperCase() === "GET";
  const signingOut = path === "/api/grocery/signout";
  if (!bootstrap && !signingOut && session === null) throw new Error(HTTP_ERROR);
  if (!bootstrap && !signingOut && focusCheck !== null && !["GET", "HEAD", "OPTIONS"].includes((init.method ?? "GET").toUpperCase())) {
    throw new Error(HTTP_ERROR);
  }
  const mine = generation;
  const headers = new Headers(init.headers);
  headers.delete("X-FEWIA-Workspace");
  if (!bootstrap && workspace !== undefined) headers.set("X-FEWIA-Workspace", workspace);
  headers.delete("X-FEWIA-Kroger-Owner");
  const krogerRoute = path.startsWith("/api/grocery/kroger/") && !path.endsWith("/pairing/redeem");
  const locations = target.searchParams.getAll("location_id");
  const chatQuote = (init.method ?? "GET").toUpperCase() === "GET" &&
    /^\/api\/grocery\/chat\/jobs\/[^/%]+$/.test(target.pathname) &&
    locations.length === 1 && /^[0-9A-Za-z]{8}$/.test(locations[0] ?? "");
  if ((krogerRoute || chatQuote) && mode === "live" && session?.auth_mode === "local_demo") {
    const proof = ownerProof();
    if (proof === null && krogerRoute) throw new Error("Open the operator pairing link to use live Kroger.");
    if (proof !== null) headers.set("X-FEWIA-Kroger-Owner", proof);
  }
  const response = await abortable(fetch(path, {
    ...init, headers, credentials: "same-origin", redirect: "error",
  }), init.signal ?? undefined);
  if (response.status === 401) {
    if (mine === generation) loseSession();
    throw new Error(HTTP_ERROR);
  }
  if (mine !== generation) throw new Error(HTTP_ERROR);
  if (response.status === 409) {
    const changed = await isWorkspaceChanged(response, init.signal ?? undefined);
    if (mine !== generation) throw new Error(HTTP_ERROR);
    if (changed && !bootstrap) {
      recoverWorkspace();
      throw new Error(HTTP_ERROR);
    }
  }
  return response;
}

export async function fetchSession(signal?: AbortSignal): Promise<GrocerySession> {
  const mine = generation;
  try {
    const value = await readJson("/api/grocery/session", { method: "GET", signal });
    if (mine !== generation) throw new Error(HTTP_ERROR);
    return acceptSession(value);
  } catch (error) {
    if (!isAbortError(error) && mine === generation) loseSession();
    throw error;
  }
}

export function recheckSession(): Promise<GrocerySession> | null {
  if (focusCheck !== null || session === null) return null;
  const check = Symbol();
  const mine = generation;
  focusCheck = check;
  return fetchSession().catch((error: unknown) => {
    if (focusCheck === check && mine === generation) loseSession();
    throw error;
  }).finally(() => {
    if (focusCheck === check) focusCheck = null;
  });
}

export async function redeemPairingTicket(ticket: string): Promise<void> {
  const mine = generation;
  const body = await readJson("/api/grocery/kroger/pairing/redeem", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticket }),
  });
  if (
    !isRecord(body) || !hasExactKeys(body, ["proof", "expires_in_seconds"]) ||
    typeof body.proof !== "string" || body.proof.length === 0 || body.proof.length > 8192 ||
    body.expires_in_seconds !== 28800 || mine !== generation
  ) throw new Error(SHAPE_ERROR);
  try {
    window.sessionStorage.setItem(workspaceStorageKey(OWNER_PROOF_STORAGE), JSON.stringify({
      proof: body.proof, expiresAt: Date.now() + body.expires_in_seconds * 1000,
    }));
  } catch { throw new Error("Kroger pairing could not be saved. Open the operator link again."); }
}

export async function signOut(): Promise<string | null> {
  const workspace = session?.workspace_id;
  loseSession();
  const body = await readWorkspaceJson("/api/grocery/signout", { method: "POST" }, krogerMode, workspace);
  if (!isRecord(body) || !hasExactKeys(body, ["logout_url"]) ||
      (body.logout_url !== null && (typeof body.logout_url !== "string" || body.logout_url.length === 0))) {
    throw new Error(SHAPE_ERROR);
  }
  if (typeof body.logout_url === "string") {
    const target = new URL(body.logout_url, window.location.origin);
    if (target.protocol !== "https:" && target.origin !== window.location.origin) throw new Error(SHAPE_ERROR);
  }
  return body.logout_url;
}

export function isAbortError(error: unknown): boolean {
  try {
    if (error instanceof Error && error.name === "AbortError") return true;
    const name = Object.getOwnPropertyDescriptor(DOMException.prototype, "name")?.get;
    return name?.call(error) === "AbortError";
  } catch {
    return false;
  }
}

function abortable<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (signal === undefined) {
    return promise;
  }
  if (signal.aborted) {
    return Promise.reject(new DOMException("Aborted", "AbortError"));
  }
  return new Promise((resolve, reject) => {
    const onAbort = (): void => {
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort);
    promise.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

export async function readJson(path: string, init: RequestInit, mode?: KrogerMode): Promise<unknown> {
  return readWorkspaceJson(path, init, mode ?? krogerMode, session?.workspace_id);
}

async function readWorkspaceJson(
  path: string, init: RequestInit, mode: KrogerMode, workspace: string | undefined,
): Promise<unknown> {
  const mine = generation;
  let response: Response;
  try {
    response = await requestWithWorkspace(path, init, mode, workspace);
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new Error(HTTP_ERROR, { cause: error });
  }
  if (!response.ok) {
    throw new Error(HTTP_ERROR);
  }
  try {
    const body: unknown = await abortable(response.json() as Promise<unknown>, init.signal ?? undefined);
    if (mine !== generation) throw new Error(HTTP_ERROR);
    if (path === "/api/grocery/providers" && isRecord(body) &&
        (body.kroger_mode === "fixture" || body.kroger_mode === "live" || body.kroger_mode === "off")) {
      setKrogerMode(body.kroger_mode);
    }
    return body;
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new Error(SHAPE_ERROR, { cause: error });
  }
}

export async function fetchConfig(signal?: AbortSignal): Promise<GroceryConfig> {
  return parseConfig(await readJson("/api/grocery/config", { method: "GET", signal }));
}

export async function submitJob(
  body: GroceryJobCreate,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<GroceryJobAck> {
  return parseAck(
    await readJson("/api/grocery/jobs", {
      method: "POST",
      signal,
      body: JSON.stringify(body),
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
    }),
  );
}

export async function fetchJob(jobId: string, signal?: AbortSignal): Promise<GroceryJob> {
  return parseJob(
    await readJson(`/api/grocery/jobs/${encodeURIComponent(jobId)}`, {
      method: "GET",
      signal,
    }),
  );
}
