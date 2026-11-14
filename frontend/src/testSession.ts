import {
  acceptSession,
  loseSession,
  OWNER_PROOF_STORAGE,
  setKrogerMode,
  workspaceStorageKey,
} from "./api";

export const TEST_SESSION = {
  auth_mode: "local_demo",
  workspace_id: "12345678-1234-4234-8234-123456789abc",
} as const;

class TestStorage implements Storage {
  #items = new Map<string, string>();

  get length(): number {
    return this.#items.size;
  }

  clear(): void {
    this.#items.clear();
  }

  getItem(key: string): string | null {
    return this.#items.get(String(key)) ?? null;
  }

  key(index: number): string | null {
    return [...this.#items.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.#items.delete(String(key));
  }

  setItem(key: string, value: string): void {
    this.#items.set(String(key), String(value));
  }

  toJSON(): Record<string, string> {
    return Object.fromEntries(this.#items);
  }
}

let restoreStorage: (() => void) | null = null;

export function installTestStorage(): void {
  if (restoreStorage !== null) return;
  const restores: (() => void)[] = [];
  for (const name of ["localStorage", "sessionStorage"] as const) {
    const storage = new TestStorage();
    for (const target of new Set<object>([window, globalThis])) {
      const original = Object.getOwnPropertyDescriptor(target, name);
      Object.defineProperty(target, name, { configurable: true, writable: true, value: storage });
      restores.push(() => {
        if (original === undefined) Reflect.deleteProperty(target, name);
        else Object.defineProperty(target, name, original);
      });
    }
  }
  restoreStorage = () => {
    for (const restore of restores.reverse()) restore();
  };
}

export function clearTestSession(): void {
  loseSession();
  if (restoreStorage !== null) {
    window.sessionStorage.clear();
    window.localStorage.clear();
    restoreStorage();
    restoreStorage = null;
  }
}

export function seedTestSession(): void {
  clearTestSession();
  installTestStorage();
  acceptSession(TEST_SESSION);
  setKrogerMode("fixture");
}

export function seedKrogerOwnerProof(): void {
  window.sessionStorage.setItem(workspaceStorageKey(OWNER_PROOF_STORAGE), JSON.stringify({
    proof: "synthetic-test-owner-proof",
    expiresAt: Date.now() + 28_800_000,
  }));
  setKrogerMode("live");
}
