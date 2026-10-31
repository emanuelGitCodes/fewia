import { useCallback, useState } from "react";
import type { KrogerStore } from "../chatTypes";
import { KROGER_LOCATION_ID, isKrogerText, type KrogerStoreOption } from "../krogerApi";

export const KROGER_STORE_KEY = "fewia.krogerStore.v1";

// Only the user's own choice is stored. Every storage call can throw, so each is wrapped.
function readStore(): KrogerStore | null {
  try {
    const raw = window.localStorage.getItem(KROGER_STORE_KEY);
    if (raw === null) {
      return null;
    }
    const value: unknown = JSON.parse(raw);
    if (
      typeof value !== "object" || value === null || Array.isArray(value) ||
      Object.keys(value).sort().join() !== "locationId,name"
    ) {
      return null;
    }
    const { locationId, name } = value as Record<string, unknown>;
    return typeof locationId === "string" && KROGER_LOCATION_ID.test(locationId) && isKrogerText(name)
      ? { locationId, name }
      : null;
  } catch {
    return null;
  }
}

function writeStore(store: KrogerStore | null): void {
  try {
    if (store === null) {
      window.localStorage.removeItem(KROGER_STORE_KEY);
    } else {
      window.localStorage.setItem(KROGER_STORE_KEY, JSON.stringify(store));
    }
  } catch {
    // The page works without storage.
  }
}

export function useKrogerStore(): {
  store: KrogerStore | null;
  choose: (option: KrogerStoreOption) => void;
  clear: () => void;
} {
  const [store, setStore] = useState<KrogerStore | null>(readStore);
  const choose = useCallback((option: KrogerStoreOption): void => {
    const next = { locationId: option.locationId, name: option.name };
    writeStore(next);
    setStore(next);
  }, []);
  const clear = useCallback((): void => {
    writeStore(null);
    setStore(null);
  }, []);
  return { store, choose, clear };
}
