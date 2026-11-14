import { useCallback, useState } from "react";
import { currentSession, workspaceStorageKey } from "../api";
import { hasExactKeys, isRecord } from "../apiTypes";
import type { KrogerStore } from "../chatTypes";
import { KROGER_LOCATION_ID, isKrogerText, type KrogerStoreOption } from "../krogerApi";

export const KROGER_STORE_KEY = "fewia.krogerStore.v1";

// Only the user's own choice is stored. Every storage call can throw, so each is wrapped.
function readStore(): KrogerStore | null {
  try {
    const raw = window.localStorage.getItem(workspaceStorageKey(KROGER_STORE_KEY));
    if (raw === null) {
      return null;
    }
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || !hasExactKeys(value, ["locationId", "name"])) {
      return null;
    }
    const { locationId, name } = value;
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
      window.localStorage.removeItem(workspaceStorageKey(KROGER_STORE_KEY));
    } else {
      window.localStorage.setItem(workspaceStorageKey(KROGER_STORE_KEY), JSON.stringify(store));
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
  const [workspace] = useState(() => currentSession()?.workspace_id);
  const choose = useCallback((option: KrogerStoreOption): void => {
    if (workspace === undefined || currentSession()?.workspace_id !== workspace) return;
    const next = { locationId: option.locationId, name: option.name };
    writeStore(next);
    setStore(next);
  }, [workspace]);
  const clear = useCallback((): void => {
    if (workspace === undefined || currentSession()?.workspace_id !== workspace) return;
    writeStore(null);
    setStore(null);
  }, [workspace]);
  return { store, choose, clear };
}
