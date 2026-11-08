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

function PickerHarness() {
  const kroger = useKrogerStore();
  return <KrogerStorePicker store={kroger.store} onChoose={kroger.choose} onClear={kroger.clear} />;
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
    expect(document.activeElement).toBe(input);
    expect(document.getElementById(input.getAttribute("aria-describedby") ?? "")?.textContent)
      .toBe("Enter a five-digit ZIP code.");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const find = screen.getByRole("button", { name: "Find stores" }) as HTMLButtonElement;
    for (const value of ["", "4520", "4520a", "45 02"]) {
      fireEvent.change(input, { target: { value } });
      expect(find.getAttribute("aria-disabled")).toBe("true");
      fireEvent.click(find);
      fireEvent.submit(input.closest("form") as HTMLFormElement);
    }
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "45202" } });
    expect(find.getAttribute("aria-disabled")).toBe("false");
  });

  it("lists stores, clears the ZIP, and calls onChoose when one is picked", async () => {
    reply({ stores: [raw], source: "live" });
    const onChoose = vi.fn();
    render(<KrogerStorePicker store={null} onChoose={onChoose} onClear={vi.fn()} />);
    await search();
    expect(zipInput().value).toBe("");
    expect(screen.getByRole("status").textContent).toBe("Found 1 Kroger store.");
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
    reply({ stores: [], source: "live" });
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

  it("shows the fixture label from the capability and keeps live text otherwise", () => {
    const { rerender } = render(
      <KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} krogerMode="fixture" />,
    );
    expect(screen.getByText("FIXTURE, NOT KROGER")).toBeTruthy();
    expect(screen.queryByRole("button", { name: CHOOSE })).toBeNull();
    expect(screen.getByRole("button", { name: "Choose a fixture store for fixture prices" })).toBeTruthy();
    for (const mode of ["live", "off", undefined] as const) {
      rerender(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} krogerMode={mode} />);
      expect(screen.queryByText("FIXTURE, NOT KROGER")).toBeNull();
      expect(screen.getByRole("button", { name: CHOOSE })).toBeTruthy();
    }
  });

  it("labels a fixture store list from the response source", async () => {
    reply({ stores: [raw], source: "fixture" });
    render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} krogerMode="live" />);
    await search();
    expect(screen.getByText("FIXTURE, NOT KROGER")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("Found 1 fixture store.");
  });

  it("does not label a live store list even when the capability says fixture", async () => {
    reply({ stores: [raw], source: "live" });
    render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} krogerMode="fixture" />);
    fireEvent.click(screen.getByRole("button", { name: "Choose a fixture store for fixture prices" }));
    fireEvent.change(zipInput(), { target: { value: "45202" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Find stores" }));
    });
    expect(screen.queryByText("FIXTURE, NOT KROGER")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Found 1 Kroger store.");
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

  it("returns focus after cancel, choosing, and removing a store", async () => {
    reply({ stores: [raw], source: "live" });
    render(<PickerHarness />);
    const choose = screen.getByRole("button", { name: CHOOSE });
    choose.focus();
    fireEvent.click(choose);
    expect(document.activeElement).toBe(zipInput());
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: CHOOSE }));
    await search();
    fireEvent.click(screen.getByRole("button", { name: /^Main Street, / }));
    const change = screen.getByRole("button", { name: "Change" });
    expect(document.activeElement).toBe(change);
    const remove = screen.getByRole("button", { name: "Remove" });
    for (const button of [change, remove]) {
      expect(document.getElementById(button.getAttribute("aria-describedby") ?? "")?.textContent)
        .toBe("Kroger store: Main Street");
    }
    fireEvent.click(change);
    expect(document.activeElement).toBe(zipInput());
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(change);
    remove.focus();
    fireEvent.click(remove);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: CHOOSE }));
    await search();
    fireEvent.click(screen.getByRole("button", { name: /^Main Street, / }));
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    expect(document.activeElement).toBe(zipInput());
  });

  it("retains Find focus through pending and ZIP clearing without duplicate searches", async () => {
    let finish: () => void = () => undefined;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => {
      finish = () => { resolve({ ok: true, json: async () => ({ stores: [raw, { ...raw, location_id: "01400944" }], source: "live" }) } as Response); };
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: CHOOSE }));
    fireEvent.change(zipInput(), { target: { value: "45202" } });
    const find = screen.getByRole("button", { name: "Find stores" });
    const status = screen.getByRole("status");
    find.focus();
    fireEvent.click(find);
    fireEvent.click(find);
    expect(status.textContent).toBe("Finding Kroger stores.");
    expect(find.getAttribute("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(find);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { finish(); });
    expect(status.textContent).toBe("Found 2 Kroger stores.");
    expect(status.textContent).not.toContain("45202");
    expect(zipInput().value).toBe("");
    expect(document.activeElement).toBe(find);
    expect(find.getAttribute("aria-disabled")).toBe("true");
  });

  it.each([false, true])("keeps moved focus and suppresses canceled results when cancel=%s", async (cancel) => {
    let finish: () => void = () => undefined;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => {
      finish = () => { resolve({ ok: true, json: async () => ({ stores: [raw], source: "live" }) } as Response); };
    })));
    render(<><KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} /><button>Elsewhere</button></>);
    await search();
    const cancelButton = screen.getByRole("button", { name: "Cancel" });
    cancelButton.focus();
    if (cancel) {
      fireEvent.click(cancelButton);
    } else {
      screen.getByRole("button", { name: "Elsewhere" }).focus();
    }
    const focused = document.activeElement;
    await act(async () => { finish(); });
    expect(document.activeElement).toBe(focused);
    expect(screen.getByRole("status").textContent).toBe(cancel ? "" : "Found 1 Kroger store.");
    if (cancel) expect(screen.queryByRole("list", { name: "Kroger stores" })).toBeNull();
  });

  it("aborts a pending search on unmount", () => {
    reply({ stores: [raw], source: "live" });
    const { unmount } = render(<KrogerStorePicker store={null} onChoose={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: CHOOSE }));
    fireEvent.change(zipInput(), { target: { value: "45202" } });
    fireEvent.click(screen.getByRole("button", { name: "Find stores" }));
    const signal = vi.mocked(fetch).mock.calls[0]?.[1]?.signal;
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("stores only the two chosen fields, never the ZIP or an address", async () => {
    reply({ stores: [raw], source: "live" });
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
