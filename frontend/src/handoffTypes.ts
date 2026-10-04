import { SHAPE_ERROR, isBool, isNonemptyString, isRecord, isSafeInteger, isString } from "./apiTypes";

export type HandoffState = "prepared" | "dispatching" | "succeeded" | "failed" | "uncertain";

export type HandoffView = {
  id: string;
  state: HandoffState;
  attempts: number;
  url: string | null;
  error_code: string | null;
  expires_at: string | null;
  retry_allowed: boolean;
};

const VIEW_KEYS: ReadonlySet<string> = new Set([
  "id",
  "state",
  "attempts",
  "url",
  "error_code",
  "expires_at",
  "retry_allowed",
]);
const HOSTS = new Set(["www.instacart.com", "instacart.com", "www.instacart.ca", "instacart.ca"]);
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
const ENCODED_CONTROL = /%(?:[01][0-9a-f]|7f)/i;
const HOST_CHARS = /^[a-z0-9.-]+$/i;
const RAW_UNSAFE = /[\s\\#]/u;

function hasControlChar(value: string): boolean {
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0;
    if (code <= 0x1f || (code >= 0x7f && code <= 0x9f)) {
      return true;
    }
  }
  return false;
}

function fail(): never {
  throw new Error(SHAPE_ERROR);
}

function isState(value: unknown): value is HandoffState {
  return (
    value === "prepared" ||
    value === "dispatching" ||
    value === "succeeded" ||
    value === "failed" ||
    value === "uncertain"
  );
}

function isStamp(value: unknown): value is string {
  return isString(value) && STAMP.test(value) && !Number.isNaN(Date.parse(value));
}

function optionalString(value: unknown): string | null {
  if (value === null) {
    return null;
  }
  if (!isString(value)) {
    fail();
  }
  return value;
}

function rawAuthority(value: string): { host: string; port: string } | null {
  if (!value.toLowerCase().startsWith("https://")) {
    return null;
  }
  const authority = value.slice(8).split(/[/?#]/, 1)[0] ?? "";
  if (authority.includes("@") || authority.startsWith("[")) {
    return null;
  }
  const colon = authority.lastIndexOf(":");
  return colon === -1
    ? { host: authority, port: "" }
    : { host: authority.slice(0, colon), port: authority.slice(colon + 1) };
}

export function isSafeHandoffUrl(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 2048 ||
    RAW_UNSAFE.test(value) ||
    hasControlChar(value) ||
    ENCODED_CONTROL.test(value)
  ) {
    return false;
  }
  const parts = rawAuthority(value);
  if (parts === null || !HOST_CHARS.test(parts.host)) {
    return false;
  }
  const host = parts.host.toLowerCase();
  if (!HOSTS.has(host) || (parts.port !== "" && parts.port !== "443")) {
    return false;
  }
  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === "https:" &&
      parsed.username === "" &&
      parsed.password === "" &&
      parsed.hash === "" &&
      parsed.hostname.toLowerCase() === host &&
      (parsed.port === "" || parsed.port === "443")
    );
  } catch {
    return false;
  }
}

function navigableOk(
  state: HandoffState,
  url: string | null,
  expires: string | null,
  retry: boolean,
): boolean {
  if (url !== null) {
    return state === "succeeded" && !retry && expires !== null && isSafeHandoffUrl(url);
  }
  if (expires !== null) {
    return state === "uncertain" && retry;
  }
  return state === "prepared" || state === "dispatching" ? !retry : retry;
}

export function parseHandoffView(value: unknown): HandoffView {
  if (!isRecord(value)) {
    fail();
  }
  const keys = Object.keys(value);
  if (keys.length !== VIEW_KEYS.size || keys.some((key) => !VIEW_KEYS.has(key))) {
    fail();
  }
  const url = optionalString(value.url);
  const code = optionalString(value.error_code);
  const expires =
    value.expires_at === null ? null : isStamp(value.expires_at) ? value.expires_at : fail();
  if (
    !isNonemptyString(value.id) ||
    !ID.test(value.id) ||
    !isState(value.state) ||
    !isSafeInteger(value.attempts) ||
    value.attempts < 0 ||
    !isBool(value.retry_allowed) ||
    !navigableOk(value.state, url, expires, value.retry_allowed)
  ) {
    fail();
  }
  return {
    id: value.id,
    state: value.state,
    attempts: value.attempts,
    url,
    error_code: code,
    expires_at: expires,
    retry_allowed: value.retry_allowed,
  };
}
