/** @vitest-environment node */

import { createElement } from "react";
import { act, create } from "react-test-renderer";
import type { ReactTestInstance, ReactTestRenderer } from "react-test-renderer";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SPOONACULAR_COST_NOTICE } from "./apiTypes";
import { SupermarketEstimate } from "./SupermarketEstimate";

const JOB_ID = "job-1";
const UNAVAILABLE = "The supermarket estimate is unavailable. Retry the estimate request.";
const IN_PROGRESS = "The supermarket estimate request is in progress.";
const RAW = "do-not-echo-this";
const TIMEOUT_MS = 45_000;
const EXPIRE_MS = 5 * 60 * 1000;

type FetchFn = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function childText(node: ReactTestInstance | string): string {
  if (typeof node === "string") {
    return node;
  }
  return node.children.map((child) => childText(child)).join("");
}

function buttonNamed(root: ReactTestInstance, name: string): ReactTestInstance {
  const match = root.findAllByType("button").find((node) => childText(node) === name);
  if (match === undefined) {
    throw new Error(`missing button ${name}`);
  }
  return match;
}

function overlay(totalCents: number | null = 1299): Record<string, unknown> {
  return { total_cents: totalCents, notice: SPOONACULAR_COST_NOTICE };
}

function jsonOk(payload: unknown): Response {
  return { ok: true, json: () => Promise.resolve(payload) } as Response;
}

function jsonFail(payload: unknown): Response {
  return { ok: false, json: () => Promise.resolve(payload) } as Response;
}

function hung(): Promise<Response> {
  return new Promise(() => undefined);
}

function mount(jobId = JOB_ID): ReactTestRenderer {
  let renderer: ReactTestRenderer | undefined;
  act(() => {
    renderer = create(createElement(SupermarketEstimate, { jobId }));
  });
  if (renderer === undefined) {
    throw new Error("renderer failed to mount");
  }
  return renderer;
}

async function clickLookup(renderer: ReactTestRenderer): Promise<void> {
  await act(async () => {
    (buttonNamed(renderer.root, "Check supermarket estimate").props.onClick as () => void)();
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("SupermarketEstimate", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(() => {
        throw new Error("fetch must not run");
      }),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("does not fetch on mount", () => {
    const fetchMock = vi.fn<FetchFn>(() => hung());
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(childText(renderer.root)).toContain("Spoonacular estimate");
    expect(childText(renderer.root)).toContain("Check supermarket estimate");
    expect(childText(renderer.root)).not.toContain("$12.99");
    renderer.unmount();
  });

  it("fetches only after an explicit lookup and sends cache no-store", async () => {
    const fetchMock = vi.fn<FetchFn>(async () => jsonOk(overlay()));
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount("aa/bb?cc");
    expect(fetchMock).not.toHaveBeenCalled();
    await clickLookup(renderer);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/grocery/jobs/${encodeURIComponent("aa/bb?cc")}/supermarket-estimate`,
    );
    expect(fetchMock.mock.calls[0]?.[1]?.cache).toBe("no-store");
    expect(childText(renderer.root)).toContain("$12.99");
    expect(childText(renderer.root)).toContain(SPOONACULAR_COST_NOTICE);
    expect(childText(renderer.root).toLowerCase()).not.toMatch(/checkout|nationwide|local store/);
    renderer.unmount();
  });

  it("shows unavailable for a malformed payload and allows retry", async () => {
    const fetchMock = vi.fn<FetchFn>(async () => jsonOk({ total_cents: 1299, notice: RAW }));
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount();
    await clickLookup(renderer);
    expect(childText(renderer.root)).toContain(UNAVAILABLE);
    expect(childText(renderer.root)).not.toContain(RAW);
    expect(childText(renderer.root)).not.toContain("$12.99");
    expect(buttonNamed(renderer.root, "Check supermarket estimate").props.disabled).toBe(false);
    fetchMock.mockImplementation(async () => jsonOk(overlay()));
    await clickLookup(renderer);
    expect(childText(renderer.root)).toContain("$12.99");
    expect(childText(renderer.root)).not.toContain(UNAVAILABLE);
    renderer.unmount();
  });

  it("ignores a second click while a lookup is pending", async () => {
    const fetchMock = vi.fn<FetchFn>(() => hung());
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount();
    await act(async () => {
      const button = buttonNamed(renderer.root, "Check supermarket estimate");
      const onClick = button.props.onClick as () => void;
      onClick();
      onClick();
      await Promise.resolve();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(buttonNamed(renderer.root, "Check supermarket estimate").props.disabled).toBe(true);
    expect(childText(renderer.root)).toContain(IN_PROGRESS);
    renderer.unmount();
  });

  it("maps a failed lookup including 503 to unavailable and retries", async () => {
    const fetchMock = vi.fn<FetchFn>(async () => jsonFail({ detail: RAW }));
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount();
    await clickLookup(renderer);
    expect(childText(renderer.root)).toContain(UNAVAILABLE);
    expect(childText(renderer.root)).not.toContain(RAW);
    fetchMock.mockImplementation(async () => jsonOk(overlay(500)));
    await clickLookup(renderer);
    expect(childText(renderer.root)).toContain("$5.00");
    expect(childText(renderer.root)).not.toContain(UNAVAILABLE);
    renderer.unmount();
  });

  it("clears the previous value as soon as a new lookup starts", async () => {
    const fetchMock = vi.fn<FetchFn>(async () => jsonOk(overlay()));
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount();
    await clickLookup(renderer);
    expect(childText(renderer.root)).toContain("$12.99");
    fetchMock.mockImplementation(() => hung());
    await clickLookup(renderer);
    expect(childText(renderer.root)).not.toContain("$12.99");
    expect(childText(renderer.root)).toContain(IN_PROGRESS);
    renderer.unmount();
  });

  it("times out a hung lookup and ignores a late success", async () => {
    vi.useFakeTimers();
    let resolveLate: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn<FetchFn>(
      () =>
        new Promise<Response>((resolve) => {
          resolveLate = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount();
    await clickLookup(renderer);
    await act(async () => {
      vi.advanceTimersByTime(TIMEOUT_MS);
      await Promise.resolve();
    });
    expect(childText(renderer.root)).toContain(UNAVAILABLE);
    expect(buttonNamed(renderer.root, "Check supermarket estimate").props.disabled).toBe(false);
    await act(async () => {
      resolveLate?.(jsonOk(overlay()));
      await Promise.resolve();
    });
    expect(childText(renderer.root)).not.toContain("$12.99");
    expect(childText(renderer.root)).toContain(UNAVAILABLE);
    renderer.unmount();
  });

  it("clears a loaded estimate after five minutes", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn<FetchFn>(async () => jsonOk(overlay())));
    const renderer = mount();
    await clickLookup(renderer);
    expect(childText(renderer.root)).toContain("$12.99");
    await act(async () => {
      vi.advanceTimersByTime(EXPIRE_MS);
      await Promise.resolve();
    });
    expect(childText(renderer.root)).not.toContain("$12.99");
    expect(buttonNamed(renderer.root, "Check supermarket estimate").props.disabled).toBe(false);
    renderer.unmount();
  });

  it("ignores a late response after unmount", async () => {
    let resolveLate: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(
        () =>
          new Promise<Response>((resolve) => {
            resolveLate = resolve;
          }),
      ),
    );
    const renderer = mount();
    await clickLookup(renderer);
    renderer.unmount();
    await act(async () => {
      resolveLate?.(jsonOk(overlay()));
      await Promise.resolve();
    });
  });

  it("clears state when the document is hidden and ignores a late response", async () => {
    const listeners = new Set<EventListener>();
    const root = {
      hidden: false,
      addEventListener: (type: string, listener: EventListener): void => {
        if (type === "visibilitychange") {
          listeners.add(listener);
        }
      },
      removeEventListener: (type: string, listener: EventListener): void => {
        listeners.delete(listener);
      },
    };
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      writable: true,
      value: root,
    });
    let resolveLate: ((response: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn<FetchFn>(
        () =>
          new Promise<Response>((resolve) => {
            resolveLate = resolve;
          }),
      ),
    );
    const renderer = mount();
    await clickLookup(renderer);
    await act(async () => {
      root.hidden = true;
      for (const listener of listeners) {
        listener({} as Event);
      }
      await Promise.resolve();
    });
    expect(childText(renderer.root)).not.toContain(IN_PROGRESS);
    expect(buttonNamed(renderer.root, "Check supermarket estimate").props.disabled).toBe(false);
    await act(async () => {
      resolveLate?.(jsonOk(overlay()));
      await Promise.resolve();
    });
    expect(childText(renderer.root)).not.toContain("$12.99");
    renderer.unmount();
    Reflect.deleteProperty(globalThis, "document");
  });

  it("resets and ignores a late response when jobId changes without remount", async () => {
    let resolveLate: ((response: Response) => void) | undefined;
    const fetchMock = vi.fn<FetchFn>(
      () =>
        new Promise<Response>((resolve) => {
          resolveLate = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const renderer = mount("job-1");
    await clickLookup(renderer);
    expect(childText(renderer.root)).toContain(IN_PROGRESS);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `/api/grocery/jobs/${encodeURIComponent("job-1")}/supermarket-estimate`,
    );
    await act(async () => {
      renderer.update(createElement(SupermarketEstimate, { jobId: "job-2" }));
      await Promise.resolve();
    });
    expect(childText(renderer.root)).not.toContain(IN_PROGRESS);
    expect(buttonNamed(renderer.root, "Check supermarket estimate").props.disabled).toBe(false);
    await act(async () => {
      resolveLate?.(jsonOk(overlay()));
      await Promise.resolve();
    });
    expect(childText(renderer.root)).not.toContain("$12.99");
    fetchMock.mockImplementation(async () => jsonOk(overlay(500)));
    await clickLookup(renderer);
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      `/api/grocery/jobs/${encodeURIComponent("job-2")}/supermarket-estimate`,
    );
    expect(childText(renderer.root)).toContain("$5.00");
    expect(childText(renderer.root)).not.toContain("$12.99");
    renderer.unmount();
  });
});
