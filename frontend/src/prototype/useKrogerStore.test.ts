// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { acceptSession, loseSession } from "../api";
import { KROGER_STORE_KEY as LEGACY_STORE_KEY, useKrogerStore } from "./useKrogerStore";

const WORKSPACE = "12345678-1234-4234-8234-123456789abc";
const KROGER_STORE_KEY = `${LEGACY_STORE_KEY}:${WORKSPACE}`;

const option = {
  locationId: "01400943",
  name: "Main Street",
  addressLine: "1 Test Way",
  city: "Springfield",
  state: "OH",
};

const originalStorage = Object.getOwnPropertyDescriptor(window, "localStorage");

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => {
      data.clear();
    },
    getItem: (key: string) => data.get(key) ?? null,
    key: (index: number) => [...data.keys()][index] ?? null,
    removeItem: (key: string) => {
      data.delete(key);
    },
    setItem: (key: string, value: string) => {
      data.set(key, String(value));
    },
  };
}

function setStorage(value: unknown): void {
  Object.defineProperty(window, "localStorage", { configurable: true, writable: true, value });
}

beforeEach(() => {
  setStorage(memoryStorage());
  acceptSession({ auth_mode: "local_demo", workspace_id: WORKSPACE });
});

afterEach(() => {
  cleanup();
  loseSession();
  if (originalStorage === undefined) {
    Reflect.deleteProperty(window, "localStorage");
  } else {
    Object.defineProperty(window, "localStorage", originalStorage);
  }
});

describe("useKrogerStore", () => {
  it.each(["local_demo", "alb"])("restores a legacy store only in local demo: %s", (auth_mode) => {
    window.localStorage.setItem(LEGACY_STORE_KEY, JSON.stringify({ locationId: option.locationId, name: option.name }));
    acceptSession({ auth_mode, workspace_id: WORKSPACE });
    const view = renderHook(() => useKrogerStore());
    expect(view.result.current.store).toEqual(auth_mode === "local_demo" ? { locationId: option.locationId, name: option.name } : null);
    expect(window.localStorage.getItem(LEGACY_STORE_KEY)).toBeNull();
  });

  it("ignores a store callback retained from the previous workspace", () => {
    const view = renderHook(() => useKrogerStore());
    const choose = view.result.current.choose;
    const other = "87654321-4321-4321-8321-cba987654321";
    acceptSession({ auth_mode: "local_demo", workspace_id: other });
    act(() => { choose(option); });
    expect(window.localStorage.getItem(`${LEGACY_STORE_KEY}:${other}`)).toBeNull();
    expect(window.localStorage.getItem(KROGER_STORE_KEY)).toBeNull();
  });

  it("starts with no store, round trips a choice, and clears it", () => {
    const first = renderHook(() => useKrogerStore());
    expect(first.result.current.store).toBeNull();
    act(() => {
      first.result.current.choose(option);
    });
    expect(first.result.current.store).toEqual({ locationId: "01400943", name: "Main Street" });
    expect(JSON.parse(window.localStorage.getItem(KROGER_STORE_KEY) ?? "null")).toEqual({
      locationId: "01400943",
      name: "Main Street",
    });
    first.unmount();
    const second = renderHook(() => useKrogerStore());
    expect(second.result.current.store).toEqual({ locationId: "01400943", name: "Main Street" });
    act(() => {
      second.result.current.clear();
    });
    expect(second.result.current.store).toBeNull();
    expect(window.localStorage.getItem(KROGER_STORE_KEY)).toBeNull();
  });

  it("reads malformed stored values as no store", () => {
    const bad = [
      "{not json",
      "null",
      "[]",
      '"x"',
      JSON.stringify({ locationId: "01400943" }),
      JSON.stringify({ locationId: "01400943", name: "A", extra: 1 }),
      JSON.stringify({ locationId: "0140094", name: "A" }),
      JSON.stringify({ locationId: "01400943", name: "" }),
      JSON.stringify({ locationId: "01400943", name: "x".repeat(161) }),
      JSON.stringify({ locationId: 1, name: "A" }),
    ];
    for (const value of bad) {
      window.localStorage.setItem(KROGER_STORE_KEY, value);
      const view = renderHook(() => useKrogerStore());
      expect(view.result.current.store).toBeNull();
      view.unmount();
    }
  });

  it("works when localStorage is undefined", () => {
    setStorage(undefined);
    const view = renderHook(() => useKrogerStore());
    expect(view.result.current.store).toBeNull();
    act(() => {
      view.result.current.choose(option);
    });
    expect(view.result.current.store?.name).toBe("Main Street");
    act(() => {
      view.result.current.clear();
    });
    expect(view.result.current.store).toBeNull();
  });

  it("works when localStorage throws", () => {
    const denied = (): never => {
      throw new Error("denied");
    };
    setStorage({ getItem: denied, setItem: denied, removeItem: denied });
    const view = renderHook(() => useKrogerStore());
    expect(view.result.current.store).toBeNull();
    act(() => {
      view.result.current.choose(option);
    });
    expect(view.result.current.store?.name).toBe("Main Street");
    act(() => {
      view.result.current.clear();
    });
    expect(view.result.current.store).toBeNull();
  });
});
