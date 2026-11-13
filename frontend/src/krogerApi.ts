import { apiRequest, readJson } from "./api";
import {
  HTTP_ERROR,
  KROGER_LOCATION_ID,
  SHAPE_ERROR,
  hasExactKeys,
  isKrogerSource,
  isRecord,
  isString,
  type KrogerSource,
  type KrogerMode,
} from "./apiTypes";

export type KrogerStoreOption = {
  locationId: string;
  name: string;
  addressLine: string;
  city: string;
  state: string;
};
export type KrogerStoreResult = { stores: KrogerStoreOption[]; source: KrogerSource };

export { KROGER_LOCATION_ID };
const MAX_STORES = 5;
const STORE_KEYS = ["location_id", "name", "address_line", "city", "state"];

export function isKrogerText(value: unknown): value is string {
  if (!isString(value)) {
    return false;
  }
  const length = [...value].length; // code points, like the backend's 160-character cut
  return length > 0 && length <= 160;
}

function copyStore(value: unknown): KrogerStoreOption {
  if (
    !isRecord(value) || !hasExactKeys(value, STORE_KEYS) ||
    !isString(value.location_id) || !KROGER_LOCATION_ID.test(value.location_id) ||
    !isKrogerText(value.name) || !isKrogerText(value.address_line) ||
    !isKrogerText(value.city) || !isKrogerText(value.state)
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return {
    locationId: value.location_id,
    name: value.name,
    addressLine: value.address_line,
    city: value.city,
    state: value.state,
  };
}

export function validateKrogerStartUrl(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || /[\\\s]/.test(value)) {
    throw new Error(SHAPE_ERROR);
  }
  const url = new URL(value, window.location.origin);
  if (url.origin !== window.location.origin || url.pathname !== "/api/grocery/kroger/connect/start" || url.hash !== "") {
    throw new Error(SHAPE_ERROR);
  }
  return value;
}

export async function connectKroger(mode?: KrogerMode): Promise<string> {
  const body = await readJson("/api/grocery/kroger/connect", { method: "POST" }, mode);
  if (!isRecord(body) || !hasExactKeys(body, ["authorization_url"])) throw new Error(SHAPE_ERROR);
  return validateKrogerStartUrl(body.authorization_url);
}

export async function readKrogerConnection(signal?: AbortSignal, mode?: KrogerMode): Promise<boolean> {
  const body = await readJson("/api/grocery/kroger/connection", { method: "GET", signal }, mode);
  if (
    !isRecord(body) || !hasExactKeys(body, ["connected"]) || typeof body.connected !== "boolean"
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return body.connected;
}

export async function disconnectKroger(mode?: KrogerMode): Promise<void> {
  let response: Response;
  try {
    response = await apiRequest("/api/grocery/kroger/connection", { method: "DELETE" }, mode);
  } catch (error) {
    throw new Error(HTTP_ERROR, { cause: error });
  }
  if (response.status !== 204) {
    throw new Error(HTTP_ERROR);
  }
}

export type KrogerCartItem = {
  ingredientId: string;
  name: string;
  upc: string;
  description: string;
  size: string | null;
  quantity: number;
};
export type KrogerCartPreview = {
  items: KrogerCartItem[];
  unmatched: { ingredientId: string; name: string }[];
  source: KrogerSource;
  confirmationToken: string | null;
  expiresInSeconds: 300;
};
export type KrogerAddResult = "added" | "not_connected" | "unavailable" | "rejected" | "unknown";

const MAX_CART_LINES = 30;
const ITEM_KEYS = ["ingredient_id", "name", "upc", "description", "size", "quantity"];
const UNMATCHED_KEYS = ["ingredient_id", "name"];

function copyCartItem(value: unknown): KrogerCartItem {
  if (
    !isRecord(value) || !hasExactKeys(value, ITEM_KEYS) ||
    !isKrogerText(value.ingredient_id) || !isKrogerText(value.name) ||
    !isString(value.upc) || !/^[0-9]{8,14}$/.test(value.upc) ||
    !isKrogerText(value.description) ||
    (value.size !== null && !isKrogerText(value.size)) ||
    typeof value.quantity !== "number" || !Number.isInteger(value.quantity) ||
    value.quantity < 1 || value.quantity > 10
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return {
    ingredientId: value.ingredient_id,
    name: value.name,
    upc: value.upc,
    description: value.description,
    size: value.size,
    quantity: value.quantity,
  };
}

function copyUnmatched(value: unknown): { ingredientId: string; name: string } {
  if (
    !isRecord(value) || !hasExactKeys(value, UNMATCHED_KEYS) ||
    !isKrogerText(value.ingredient_id) || !isKrogerText(value.name)
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return { ingredientId: value.ingredient_id, name: value.name };
}

export async function previewKrogerCart(
  planRevisionId: string,
  locationId: string,
  signal?: AbortSignal,
  mode?: KrogerMode,
): Promise<KrogerCartPreview> {
  const body = await readJson("/api/grocery/kroger/cart/preview", {
    method: "POST",
    signal,
    body: JSON.stringify({ plan_revision_id: planRevisionId, location_id: locationId }),
    headers: { "Content-Type": "application/json" },
  }, mode);
  if (
    !isRecord(body) || !hasExactKeys(body, ["items", "unmatched", "source", "confirmation_token", "expires_in_seconds"]) ||
    !Array.isArray(body.items) || body.items.length > MAX_CART_LINES ||
    !Array.isArray(body.unmatched) || body.unmatched.length > MAX_CART_LINES ||
    !isKrogerSource(body.source) ||
    (body.confirmation_token !== null && (
      typeof body.confirmation_token !== "string" ||
      body.confirmation_token.length === 0 || body.confirmation_token.length > 8192
    )) || body.expires_in_seconds !== 300
  ) {
    throw new Error(SHAPE_ERROR);
  }
  const items = body.items.map(copyCartItem);
  if (
    (items.length === 0) !== (body.confirmation_token === null) ||
    new Set(items.map((item) => item.upc)).size !== items.length
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return {
    items, unmatched: body.unmatched.map(copyUnmatched), source: body.source,
    confirmationToken: body.confirmation_token, expiresInSeconds: body.expires_in_seconds,
  };
}

// Any outcome that is not a clear answer reads as "unknown", because the items may be in the cart.
export async function addToKrogerCart(
  confirmationToken: string,
  mode?: KrogerMode,
): Promise<KrogerAddResult> {
  let response: Response;
  try {
    response = await apiRequest("/api/grocery/kroger/cart/add", {
      method: "POST",
      body: JSON.stringify({ confirmation_token: confirmationToken }),
      headers: { "Content-Type": "application/json" },
    }, mode);
  } catch {
    return "unknown";
  }
  if (response.status === 204) {
    return "added";
  }
  if (response.status === 409) {
    return "not_connected";
  }
  // 400 and 422 mean the request was rejected before anything was sent.
  if (response.status === 400 || response.status === 422) {
    return "rejected";
  }
  return response.status === 503 ? "unavailable" : "unknown";
}

// The ZIP goes only in the POST body, never in a URL.
export async function findKrogerStores(
  zip: string,
  signal?: AbortSignal,
): Promise<KrogerStoreResult> {
  const body = await readJson("/api/grocery/kroger/stores", {
    method: "POST",
    signal,
    body: JSON.stringify({ zip_code: zip }),
    headers: { "Content-Type": "application/json" },
  });
  if (
    !isRecord(body) || !hasExactKeys(body, ["stores", "source"]) ||
    !Array.isArray(body.stores) || body.stores.length > MAX_STORES ||
    !isKrogerSource(body.source)
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return { stores: body.stores.map(copyStore), source: body.source };
}
