import { readJson } from "./api";
import { HTTP_ERROR, SHAPE_ERROR, isRecord, isString } from "./apiTypes";

export type KrogerStoreOption = {
  locationId: string;
  name: string;
  addressLine: string;
  city: string;
  state: string;
};

export const KROGER_LOCATION_ID = /^[0-9A-Za-z]{8}$/;
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
    !isRecord(value) || Object.keys(value).length !== STORE_KEYS.length ||
    !STORE_KEYS.every((key) => Object.prototype.hasOwnProperty.call(value, key)) ||
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

export async function readKrogerConnection(signal?: AbortSignal): Promise<boolean> {
  const body = await readJson("/api/grocery/kroger/connection", { method: "GET", signal });
  if (
    !isRecord(body) || Object.keys(body).length !== 1 ||
    !Object.prototype.hasOwnProperty.call(body, "connected") || typeof body.connected !== "boolean"
  ) {
    throw new Error(SHAPE_ERROR);
  }
  return body.connected;
}

export async function disconnectKroger(): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/grocery/kroger/connection", { method: "DELETE" });
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
};
export type KrogerAddResult = "added" | "not_connected" | "unavailable" | "unknown";

const MAX_CART_LINES = 30;
const ITEM_KEYS = ["ingredient_id", "name", "upc", "description", "size", "quantity"];
const UNMATCHED_KEYS = ["ingredient_id", "name"];

function hasExactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return (
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

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
): Promise<KrogerCartPreview> {
  const body = await readJson("/api/grocery/kroger/cart/preview", {
    method: "POST",
    signal,
    body: JSON.stringify({ plan_revision_id: planRevisionId, location_id: locationId }),
    headers: { "Content-Type": "application/json" },
  });
  if (
    !isRecord(body) || !hasExactKeys(body, ["items", "unmatched"]) ||
    !Array.isArray(body.items) || body.items.length > MAX_CART_LINES ||
    !Array.isArray(body.unmatched) || body.unmatched.length > MAX_CART_LINES
  ) {
    throw new Error(SHAPE_ERROR);
  }
  const items = body.items.map(copyCartItem);
  if (new Set(items.map((item) => item.upc)).size !== items.length) {
    throw new Error(SHAPE_ERROR);
  }
  return { items, unmatched: body.unmatched.map(copyUnmatched) };
}

// Any outcome that is not a clear answer reads as "unknown", because the items may be in the cart.
export async function addToKrogerCart(
  items: { upc: string; quantity: number }[],
): Promise<KrogerAddResult> {
  let response: Response;
  try {
    response = await fetch("/api/grocery/kroger/cart/add", {
      method: "POST",
      body: JSON.stringify({ items: items.map(({ upc, quantity }) => ({ upc, quantity })) }),
      headers: { "Content-Type": "application/json" },
    });
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
  return [400, 422, 503].includes(response.status) ? "unavailable" : "unknown";
}

// The ZIP goes only in the POST body, never in a URL.
export async function findKrogerStores(
  zip: string,
  signal?: AbortSignal,
): Promise<KrogerStoreOption[]> {
  const body = await readJson("/api/grocery/kroger/stores", {
    method: "POST",
    signal,
    body: JSON.stringify({ zip_code: zip }),
    headers: { "Content-Type": "application/json" },
  });
  if (!isRecord(body) || !Array.isArray(body.stores) || body.stores.length > MAX_STORES) {
    throw new Error(SHAPE_ERROR);
  }
  return body.stores.map(copyStore);
}
