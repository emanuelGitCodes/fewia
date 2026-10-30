// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  KROGER_NO_STORES_LINE,
  KROGER_UNAVAILABLE_LINE,
  KrogerStorePicker,
} from "./KrogerStorePicker";
import { useKrogerStore } from "./useKrogerStore";

const raw = {
  location_id: "01400943",
  name: "Main Street",
  address_line: "1 Test Way",
  city: "Springfield",
  state: "OH",
};
const CHOOSE = "Choose a Kroger store for live prices";

function reply(body: unknown, ok = true): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, json: async () => body }) as Response),
  );
}

function zipInput(): HTMLInputElement {
  return screen.getByLabelText("ZIP code") as HTMLInputElement;
}

async function search(zip = "45202"): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: CHOOSE }));
  fireEvent.change(zipInput(), { target: { value: zip } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Find stores" }));
  });
}

const originalStorage = {
  localStorage: Object.getOwnPropertyDescriptor(window, "localStorage"),
  sessionStorage: Object.getOwnPropertyDescriptor(window, "sessionStorage"),
};

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

beforeEach(() => {
  for (const name of ["localStorage", "sessionStorage"] as const) {
    Object.defineProperty(window, name, { configurable: true, writable: true, value: memoryStorage() });
  }
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  for (const name of ["localStorage", "sessionStorage"] as const) {
    const original = originalStorage[name];
    if (original === undefined) {
      Reflect.deleteProperty(window, name);
    } else {
      Object.defineProperty(window, name, original);
    }
  }
});

describe("KrogerStorePicker", () => {
  it("opens a form with a ZIP input and enables the search only for 5 digits", () => {
    render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: CHOOSE }));
    const input = zipInput();
    expect(input.getAttribute("inputmode")).toBe("numeric");
    expect(input.maxLength).toBe(5);
    expect(input.getAttribute("autocomplete")).toBe("off");
    const find = screen.getByRole("button", { name: "Find stores" }) as HTMLButtonElement;
    for (const value of ["", "4520", "4520a", "45 02"]) {
      fireEvent.change(input, { target: { value } });
      expect(find.disabled).toBe(true);
    }
    fireEvent.change(input, { target: { value: "45202" } });
    expect(find.disabled).toBe(false);
  });

  it("lists stores, clears the ZIP, and calls onChoose when one is picked", async () => {
    reply({ stores: [raw] });
    const onChoose = vi.fn();
    render(<KrogerStorePicker store={null} onChoose={onChoose} onClear={vi.fn()} />);
    await search();
    expect(zipInput().value).toBe("");
    const pick = screen.getByRole("button", { name: "Main Street, 1 Test Way, Springfield, OH" });
    expect(pick.closest("ul")).not.toBeNull();
    fireEvent.click(pick);
    expect(onChoose).toHaveBeenCalledWith({
      locationId: "01400943",
      name: "Main Street",
      addressLine: "1 Test Way",
      city: "Springfield",
      state: "OH",
    });
    expect(screen.queryByLabelText("ZIP code")).toBeNull();
  });

  it("shows the empty and error texts in a polite status region", async () => {
    reply({ stores: [] });
    const { container } = render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} />);
    await search();
    const region = container.querySelector('[aria-live="polite"]');
    expect(region?.textContent).toBe(KROGER_NO_STORES_LINE);
    reply({ stores: "bad" });
    fireEvent.change(zipInput(), { target: { value: "45202" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Find stores" }));
    });
    expect(region?.textContent).toBe(KROGER_UNAVAILABLE_LINE);
  });

  it("shows a fixed error without the ZIP when the request fails", async () => {
    reply({ detail: "ZIP 45202 failed" }, false);
    const { container } = render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} />);
    await search();
    expect(container.querySelector('[aria-live="polite"]')?.textContent).toBe(KROGER_UNAVAILABLE_LINE);
    expect(container.textContent).not.toContain("45202");
  });

  it("shows the chosen store with Change and Remove", () => {
    const onClear = vi.fn();
    render(
      <KrogerStorePicker
        store={{ locationId: "01400943", name: "Main Street" }}
        onChoose={vi.fn()}
        onClear={onClear}
      />,
    );
    expect(screen.getByText("Kroger store: Main Street")).toBeTruthy();
    expect(screen.queryByRole("button", { name: CHOOSE })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    expect(zipInput()).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("aborts a pending search on unmount", () => {
    reply({ stores: [raw] });
    const { unmount } = render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: CHOOSE }));
    fireEvent.change(zipInput(), { target: { value: "45202" } });
    fireEvent.click(screen.getByRole("button", { name: "Find stores" }));
    const signal = vi.mocked(fetch).mock.calls[0]?.[1]?.signal;
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("stores only the two chosen fields, never the ZIP or an address", async () => {
    reply({ stores: [raw] });
    function Harness() {
      const kroger = useKrogerStore();
      return <KrogerStorePicker store={kroger.store} onChoose={kroger.choose} onClear={kroger.clear} />;
    }
    render(<Harness />);
    await search("45202");
    fireEvent.click(screen.getByRole("button", { name: /^Main Street, / }));
    expect(screen.getByText("Kroger store: Main Street")).toBeTruthy();
    expect(window.localStorage.length).toBe(1);
    const key = window.localStorage.key(0) ?? "";
    expect(key).toBe("fewia.krogerStore.v1");
    const value = window.localStorage.getItem(key) ?? "";
    expect(JSON.parse(value)).toEqual({ locationId: "01400943", name: "Main Street" });
    expect(value).not.toContain("45202");
    expect(value).not.toContain("1 Test Way");
    expect(window.sessionStorage.length).toBe(0);
  });
});
