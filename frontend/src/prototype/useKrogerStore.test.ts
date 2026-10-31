// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { KROGER_STORE_KEY, useKrogerStore } from "./useKrogerStore";

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
});

afterEach(() => {
  cleanup();
  if (originalStorage === undefined) {
    Reflect.deleteProperty(window, "localStorage");
  } else {
    Object.defineProperty(window, "localStorage", originalStorage);
  }
});

describe("useKrogerStore", () => {
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
