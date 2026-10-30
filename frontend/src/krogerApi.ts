import { readJson } from "./api";
import { SHAPE_ERROR, isRecord, isString } from "./apiTypes";

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
